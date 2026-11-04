"""Authentication strategies. No passwords or tokens are included in repr/errors."""
import asyncio
import base64
import math
import time
from email.utils import formatdate
from http.cookies import SimpleCookie
from yarl import URL
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BitTeamAPIError(Exception):
    def __init__(self, status: int, code: Any = None, *, retry_after=None):
        self.status = status
        self.retry_after = retry_after
        self.code = code if isinstance(code, (str, int)) else None
        # Do not echo server messages, request bodies, URLs or credentials.
        super().__init__(f"BitTeam request failed (HTTP {status}, code {self.code if isinstance(self.code, int) else 'unavailable'})")


class AuthenticationError(BitTeamAPIError):
    pass


def is_authentication_failure(error, *, expired=False):
    """BitTeam can encode an authentication error in an HTTP 200 response."""
    if error.code == 401000:
        return expired
    if error.code == 401008:  # Documented internal server error, not invalid credentials.
        return False
    return error.status == 401 or error.code in {401001, 401002, 401003, 401005, 401006, 401007, 401009, 401010}


class AuthState(str, Enum):
    NEW = "new"
    EMAIL_CONFIRMATION_REQUIRED = "email_confirmation_required"
    TWO_FACTOR_REQUIRED = "two_factor_required"
    DEVICE_CONFIRMATION_REQUIRED = "device_confirmation_required"
    GENERAL_SESSION_READY = "general_session_ready"
    READY = "ready"
    EXPIRED = "expired"


class PublicAuth:
    """Public market data without account credentials."""

    def headers(self):
        raise AuthenticationError(401)


@dataclass(frozen=True)
class LoginResult:
    state: AuthState
    # Delivery is server controlled. None means that the channel is unknown.
    delivery_channel: str | None = None
    lifecycle: int | None = field(default=None, repr=False)


@dataclass(repr=False)
class ApiKeyAuth:
    api_key: str = field(repr=False)
    api_secret: str = field(repr=False)

    def __post_init__(self):
        if not self.api_key or not self.api_secret:
            raise ValueError("Both API key and secret are required")

    def headers(self):
        token = base64.b64encode(f"{self.api_key}:{self.api_secret}".encode()).decode("ascii")
        return {"Authorization": f"Basic {token}"}


class SessionAuth:
    """Stepwise email/password login; use the same transport for all steps.

    Device codes received by email or Telegram use confirm_device(). The server
    chooses delivery; the observed API has no documented channel selector.
    """

    def __init__(self, *, auth_url="https://auth2.bit.team/v1", language="ru", cache=None):
        self.auth_url = auth_url.rstrip("/")
        self.language = language
        self.state = AuthState.NEW
        self._uid = None
        self._access = None
        self._refresh = None
        self._generation = 0
        self._lifecycle = 0
        self._pending_requests = set()
        self._refresh_lock = asyncio.Lock()
        self._login_lock = asyncio.Lock()
        self._transport = None
        self._delivery_channel = None
        self.email = None
        self.cache = cache

    def bind(self, transport):
        if self._transport is not None and self._transport is not transport:
            raise ValueError("SessionAuth belongs to one client only")
        self._transport = transport

    @property
    def generation(self):
        return self._generation

    def headers(self):
        if self.state != AuthState.READY or not self._access:
            raise AuthenticationError(401)
        return {"Authorization": f"Bearer {self._access}"}

    async def _auth_request(self, endpoint, data):
        return await self._tracked_send(
            "POST", self.auth_url + endpoint, data=data,
            params={"lang": self.language}, headers={})

    def _assert_lifecycle(self, expected):
        if expected != self._lifecycle:
            raise asyncio.CancelledError("Authentication operation was invalidated")

    async def _tracked_send(self, *args, **kwargs):
        return await self._tracked_operation(self._transport._send(*args, **kwargs))

    async def _tracked_operation(self, operation):
        lifecycle = self._lifecycle
        task = asyncio.create_task(operation)
        self._pending_requests.add(task)
        try:
            result = await task
            self._assert_lifecycle(lifecycle)
            return result
        finally:
            self._pending_requests.discard(task)

    @staticmethod
    def _data(response):
        if not isinstance(response, dict):
            raise AuthenticationError(502)
        data = response.get("data")
        if not isinstance(data, dict):
            raise AuthenticationError(502)
        return data

    def _transition(self, data, *, after_totp=False):
        if data.get("uid"):
            self._uid = data["uid"]
        if "email_confirm" in data and not data["email_confirm"]:
            self.state = AuthState.EMAIL_CONFIRMATION_REQUIRED
        elif data.get("double_auth_google") and not after_totp:
            self.state = AuthState.TWO_FACTOR_REQUIRED
        elif data.get("is_authorize") is False or data.get("is_authorize") == 0:
            self.state = AuthState.DEVICE_CONFIRMATION_REQUIRED
        elif data.get("is_authorize") is True or data.get("is_authorize") == 1:
            self.state = AuthState.GENERAL_SESSION_READY
        else:
            # Missing authorization fields are not evidence of a successful login.
            raise AuthenticationError(502)
        return LoginResult(self.state, self._delivery_channel, self._lifecycle)

    async def login(self, email: str, password: str):
        if not email or not password:
            raise ValueError("Email and password are required")
        lifecycle = self._lifecycle
        async with self._login_lock:
            self._assert_lifecycle(lifecycle)
            self.clear()
            lifecycle = self._lifecycle
            self.email = email
            await self._transport.clear_cookies()
            self._assert_lifecycle(lifecycle)
            response = await self._auth_request("/clients/web/login", {"email": email, "password": password})
            return self._transition(self._data(response))

    def _require(self, state):
        if self.state != state or not self._uid:
            raise RuntimeError(f"Authentication step requires {state.value}")

    async def submit_totp(self, code: str):
        self._require(AuthState.TWO_FACTOR_REQUIRED)
        if not isinstance(code, str) or len(code) != 6 or not code.isascii() or not code.isdigit():
            raise ValueError("TOTP code must contain six ASCII digits")
        response = await self._auth_request("/clients/web/login-2fa", {"uid": self._uid, "google2fa_secret": code})
        return self._transition(self._data(response), after_totp=True)

    async def send_device_code(self):
        self._require(AuthState.DEVICE_CONFIRMATION_REQUIRED)
        response = await self._auth_request("/authorize/send-code", {"uid": self._uid})
        if not isinstance(response, dict):
            raise AuthenticationError(502)
        data = response.get("data")
        # Only expose a channel if the server actually supplies one.
        if isinstance(data, dict) and data.get("delivery_channel") in ("email", "telegram"):
            self._delivery_channel = data["delivery_channel"]
        return LoginResult(self.state, self._delivery_channel, self._lifecycle)

    async def confirm_device(self, code: str, *, remember=False):
        self._require(AuthState.DEVICE_CONFIRMATION_REQUIRED)
        if not isinstance(code, str) or len(code) != 4 or not code.isascii() or not code.isdigit():
            raise ValueError("Device code must contain four ASCII digits")
        response = await self._auth_request("/authorize/check-code", {
            "uid": self._uid, "code": int(code), "is_remember": bool(remember)})
        if not isinstance(response, dict):
            raise AuthenticationError(502)
        # The web app treats a truthy data response as confirmation success.
        data = response.get("data")
        if not data or (isinstance(data, dict) and (data.get("ok") is False or data.get("is_authorize") is False)):
            raise AuthenticationError(401)
        self.state = AuthState.GENERAL_SESSION_READY
        return LoginResult(self.state, self._delivery_channel, self._lifecycle)

    def _install_tokens(self, response):
        if not isinstance(response, dict):
            raise AuthenticationError(502)
        data = response.get("result")
        if not isinstance(data, dict) or not all(isinstance(data.get(k), str) and data[k] for k in ("access", "refresh")):
            raise AuthenticationError(502)
        self._transport.set_spot_cookies(data["access"], data["refresh"])
        self._access, self._refresh = data["access"], data["refresh"]
        self._generation += 1
        self.state = AuthState.READY
        self.save_session()

    def save_session(self):
        if self.cache is None or self.state != AuthState.READY:
            return
        session = self._transport._session
        cookies = []
        if session is not None:
            jar = session.cookie_jar
            for cookie in jar:
                domain, path, name = cookie["domain"], cookie["path"], cookie.key
                cookies.append({"name": name, "value": cookie.value, "domain": domain, "path": path,
                    "secure": bool(cookie["secure"]), "httponly": bool(cookie["httponly"]),
                    "samesite": cookie["samesite"],
                    "expires_at": getattr(jar, "_expirations", {}).get((domain, path, name)),
                    "host_only": (domain, name) in getattr(jar, "_host_only_cookies", set())})
        self.cache.save({"version": 1, "base_url": self._transport.base_url, "auth_url": self.auth_url,
                         "email": self.email, "access": self._access, "refresh": self._refresh, "cookies": cookies})

    async def resume(self, *, validate=True):
        from .session_cache import SessionCacheError
        lifecycle = self._lifecycle
        if self.cache is None:
            return False
        data = self.cache.load()
        if data is None:
            return False
        if data["base_url"] != self._transport.base_url or data["auth_url"] != self.auth_url:
            raise SessionCacheError("Session cache belongs to another API configuration")
        if not all(isinstance(data.get(k), str) and data[k] for k in ("access", "refresh")):
            raise SessionCacheError("Cached token pair is invalid")
        if not isinstance(data["cookies"], list) or len(data["cookies"]) > 256:
            raise SessionCacheError("Cached cookies are invalid")
        session = await self._transport._get_session()
        self._assert_lifecycle(lifecycle)
        prepared = []
        hosts = {origin.host for origin in self._transport._allowed_origins}
        for item in data["cookies"]:
            if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ("name", "value", "domain", "path")):
                raise SessionCacheError("Cached cookie is invalid")
            domain = item["domain"].lstrip(".")
            if not domain or not any(host == domain or ("." in domain and host.endswith("." + domain)) for host in hosts):
                raise SessionCacheError("Cached cookie domain does not belong to this API")
            expires = item.get("expires_at")
            if expires is not None:
                if not isinstance(expires, (int, float)) or not math.isfinite(expires):
                    raise SessionCacheError("Cached cookie expiry is invalid")
                if expires <= time.time():
                    continue
            cookie = SimpleCookie()
            cookie[item["name"]] = item["value"]
            morsel = cookie[item["name"]]
            morsel["path"] = item["path"] or "/"
            morsel["secure"] = bool(item.get("secure"))
            morsel["httponly"] = bool(item.get("httponly"))
            morsel["samesite"] = item.get("samesite", "")
            if not item.get("host_only"):
                morsel["domain"] = domain
            if expires is not None:
                morsel["expires"] = formatdate(expires, usegmt=True)
            prepared.append((cookie, URL.build(scheme="https", host=domain).with_path(item["path"] or "/")))
        self.clear(delete_cache=False)
        lifecycle = self._lifecycle
        session.cookie_jar.clear()
        for cookie, origin in prepared:
            session.cookie_jar.update_cookies(cookie, response_url=origin)
        self.email = data.get("email")
        self._install_tokens({"result": {"access": data["access"], "refresh": data["refresh"]}})
        if validate:
            try:
                await self._tracked_operation(self._transport.get_balance())
            except BitTeamAPIError as error:
                if is_authentication_failure(error, expired=True):
                    self.clear(expired=True)
                    await self._transport.clear_cookies()
                    return False
                raise
        self._assert_lifecycle(lifecycle)
        return True

    async def open_spot_session(self):
        if self.state != AuthState.GENERAL_SESSION_READY:
            raise RuntimeError("Complete login confirmations before opening spot session")
        generation = self._generation
        response = await self._tracked_send("POST", self._transport.base_url + "/login-auth", headers={})
        if generation != self._generation:
            raise AuthenticationError(401)
        self._install_tokens(response)
        return LoginResult(self.state)

    async def refresh(self, *, expected_generation=None):
        async with self._refresh_lock:
            if expected_generation is not None and self._generation != expected_generation and self.state == AuthState.READY:
                return LoginResult(self.state)
            if self.state != AuthState.READY or not self._refresh:
                raise AuthenticationError(401)
            try:
                generation = self._generation
                response = await self._tracked_send("POST", self._transport.base_url + "/refresh-token",
                    data={}, headers={"Authorization": f"Bearer {self._refresh}"})
                if generation != self._generation:
                    raise AuthenticationError(401)
                self._install_tokens(response)
            except BitTeamAPIError as exc:
                if is_authentication_failure(exc, expired=True):
                    try:
                        self.clear(expired=True)
                    finally:
                        await self._transport.clear_cookies()
                raise
            return LoginResult(self.state)

    async def logout(self, *, use_refresh=False):
        lifecycle = self._lifecycle
        async with self._refresh_lock:
            self._assert_lifecycle(lifecycle)
            try:
                if self.state == AuthState.READY:
                    headers = {"Authorization": f"Bearer {self._refresh}"} if use_refresh else self.headers()
                    await self._tracked_send("POST", self._transport.base_url + ("/refresh-logout" if use_refresh else "/logout"), headers=headers)
            finally:
                # A concurrent explicit login may already own a new session.
                if lifecycle == self._lifecycle:
                    await self.clear_session()

    def clear(self, *, expired=False, delete_cache=True):
        self._lifecycle += 1
        try:
            current = asyncio.current_task()
        except RuntimeError:
            current = None
        for task in tuple(self._pending_requests):
            if task is not current and not task.done():
                task.cancel()
        self._uid = self._access = self._refresh = self._delivery_channel = None
        self.email = None
        self.state = AuthState.EXPIRED if expired else AuthState.NEW
        self._generation += 1
        if delete_cache and self.cache is not None:
            self.cache.delete()

    async def clear_session(self):
        """Local-only removal; use logout() to revoke the server session too."""
        pending = tuple(task for task in self._pending_requests if task is not asyncio.current_task())
        cleanup_lifecycle = self._lifecycle + 1
        try:
            self.clear()
        finally:
            try:
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            finally:
                # Draining canceled requests can yield to a new login. Never
                # remove cookies belonging to that newer authentication life.
                if self._lifecycle == cleanup_lifecycle:
                    await self._transport.clear_cookies()
