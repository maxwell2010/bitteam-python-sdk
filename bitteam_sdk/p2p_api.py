"""P2P/API-v2 helper catalog extracted from the official public site JS.

Private methods require the general SessionAuth access_token cookie, never
the spot access token or an API key. All requests, including mutating GETs,
are explicit and single-attempt. P2P currency IDs are not spot currency IDs.
"""
import asyncio
import json
from importlib.resources import files
import re
import ssl
from urllib.parse import quote

import aiohttp
from yarl import URL

from .auth import SessionAuth, AuthState, AuthenticationError, BitTeamAPIError
from .utils import RateLimiter


P2P_SCHEMA = json.loads(files("bitteam_sdk").joinpath("schemas/p2p_site.json").read_text(encoding="utf-8"))
P2P_CATALOG = P2P_SCHEMA["operations"]


def _validate_ram_response(payload, shape):
    """Check only reported access paths; return full raw JSON without inference."""
    if shape == "raw_json":
        return
    if not isinstance(payload, dict):
        raise BitTeamAPIError(502)
    if shape == "ram_tokens":
        if "tokens" not in payload:
            raise BitTeamAPIError(502)
        return
    if "data" not in payload:
        raise BitTeamAPIError(502)
    if shape == "ram_status_data" and "status" not in payload:
        raise BitTeamAPIError(502)
    if shape == "ram_subscription_list" and not isinstance(payload["data"], list):
        raise BitTeamAPIError(502)
    if shape == "ram_data_is_auto" and (
            not isinstance(payload["data"], dict) or "is_auto" not in payload["data"]):
        raise BitTeamAPIError(502)
    if shape in ("ram_notifications", "ram_active_notifications"):
        meta = payload.get("meta")
        keys = ("count", "total") if shape == "ram_notifications" else ("count",)
        if not isinstance(meta, dict) or not any(key in meta for key in keys):
            raise BitTeamAPIError(502)


class BitTeamP2PAPI:
    BASE_URL = "https://api-v2.bit.team/api/v2"

    def __init__(self, auth=None, *, timeout=20, locale="en"):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 60:
            raise ValueError("timeout must be between 1 and 60 seconds")
        if locale not in ("en", "ru"):
            raise ValueError("locale must be en or ru")
        self.auth, self.timeout, self.locale = auth, timeout, locale
        self._session = None
        self._closed = False
        self._limiter = RateLimiter(5, 1)

    async def _get_session(self):
        if self._closed:
            raise RuntimeError("P2P client is closed")
        if self._session is None:
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context = ssl.create_default_context()
            self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context),
                timeout=aiohttp.ClientTimeout(total=self.timeout), cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False)
        return self._session

    def _general_token(self):
        if not isinstance(self.auth, SessionAuth) or self.auth.state not in (AuthState.READY, AuthState.GENERAL_SESSION_READY):
            raise AuthenticationError(401)
        self.auth._assert_owner()
        transport = self.auth._transport
        if (transport is None or getattr(transport, "_closed", False)
                or getattr(transport, "base_url", "").rstrip("/") != "https://bit.team/trade/api"
                or self.auth.auth_url.rstrip("/") != "https://auth2.bit.team/v1"):
            raise AuthenticationError(401)
        session = getattr(transport, "_session", None)
        if session is None:
            raise AuthenticationError(401)
        cookie = session.cookie_jar.filter_cookies(URL(self.BASE_URL)).get("access_token")
        if cookie is None or not cookie.value:
            raise AuthenticationError(401)
        return cookie.value

    async def call(self, operation, *, path=None, params=None, data=None):
        if operation not in P2P_CATALOG:
            raise ValueError("Unknown P2P operation; arbitrary URLs are not supported")
        entry = P2P_CATALOG[operation]
        if path is not None and not isinstance(path, dict):
            raise ValueError("Path parameters must be a dictionary")
        if params is not None and not isinstance(params, dict):
            raise ValueError("Query parameters must be a dictionary")
        if data is not None and not isinstance(data, dict):
            raise ValueError("Explicit JSON data must be a dictionary")
        path, params = dict(path or {}), dict(params or {})
        if entry.get("query_policy") == "declared" and set(params) - set(entry.get("query", {})):
            raise ValueError("Query parameters do not match this fixed callsite")
        if entry.get("query_policy") == "none" and params:
            raise ValueError("This fixed frontend body callsite does not accept query parameters")
        if set(path) != set(entry["path_params"]):
            raise ValueError("Path parameters do not match this operation")
        route = entry["path"]
        for key, value in path.items():
            if isinstance(value, bool) or not isinstance(value, (str, int)):
                raise ValueError("Invalid P2P path parameter")
            value = str(value)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}", value):
                raise ValueError("Invalid P2P path parameter")
            route = route.replace("{" + key + "}", quote(value, safe=""))
        for key, rule in entry.get("query", {}).items():
            if "fixed" in rule:
                if key in params and str(params[key]) != str(rule["fixed"]):
                    raise ValueError("Cannot override a fixed helper parameter")
                params[key] = rule["fixed"]
            elif "default" in rule:
                params.setdefault(key, rule["default"])
            elif rule.get("required") and (key not in params or params[key] is None):
                raise ValueError(f"Required query parameter: {key}")
            if "enum" in rule and params.get(key) not in rule["enum"]:
                raise ValueError(f"Unsupported fixed callsite query value: {key}")
        currency_policy = entry.get("body_currency_id_policy")
        def validate_body():
            if entry.get("body_policy") == "null" and data is not None:
                raise ValueError("This callsite requires an explicit null body")
            for key in entry.get("known_body_keys", []):
                if data is None or key not in data:
                    raise ValueError(f"Required body field from site helper: {key}")
            if entry.get("body_required") and data is None:
                raise ValueError("Explicit JSON body is required")
            currency_id = data.get("currency_id") if currency_policy else None
            stock_selected = (not isinstance(currency_id, bool)
                              and isinstance(currency_id, (int, float)) and currency_id == 95)
            if currency_policy == "stock_95":
                if not stock_selected:
                    raise ValueError("Stock withdrawal body requires numeric currency_id 95")
            elif currency_policy == "internal_stock":
                if (isinstance(currency_id, bool) or not isinstance(currency_id, int)
                        or currency_id <= 0 or data["internal_request"] is not True):
                    raise ValueError("Internal transfer requires a positive integer currency_id and internal_request true")
            elif currency_policy == "standard_not_95" and stock_selected:
                raise ValueError("Currency 95 uses the separate stock body callsite")
        validate_body()
        if entry["method"] == "GET" and data is not None:
            raise ValueError("GET helper does not accept a JSON body")
        if any(not isinstance(key, str) or len(key) > 200 for key in params):
            raise ValueError("Invalid query parameter name")
        # Preserve explicit callers' unknown query/body fields without inventing
        # schemas. Bound pagination when it is supplied and has known semantics.
        for key in ("limit", "page", "offset"):
            if key in params:
                value = params[key]
                low, high = (0, 1000000) if key == "offset" else (1, 1000 if key == "limit" else 1000000)
                if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                    raise ValueError(f"Invalid {key}")
        headers = {"Accept": "application/json", "Accept-Language": self.locale}
        auth, lifecycle, token = self.auth, None, None
        if entry["private"]:
            token = self._general_token()
            lifecycle = auth._lifecycle
            headers["Authorization"] = "Bearer " + token

        def assert_current():
            if self._closed:
                raise RuntimeError("P2P client is closed")
            if entry["private"]:
                if self.auth is not auth:
                    raise asyncio.CancelledError("Authentication operation was invalidated")
                auth._assert_lifecycle(lifecycle)
                auth._assert_owner()
                if auth._transport is None or getattr(auth._transport, "_closed", False):
                    raise AuthenticationError(401)

        session = await self._get_session()
        await self._limiter.acquire()
        assert_current()
        if entry["private"]:
            # A queued request must not retain a token across logout/close.
            token = self._general_token()
            headers["Authorization"] = "Bearer " + token
        async def send_once():
            nonlocal token
            # Tracking schedules a task; account replacement may happen before
            # that task starts, so guard the actual dispatch as well.
            assert_current()
            if currency_policy or entry.get("known_body_keys") or entry.get("body_required"):
                # The caller's dictionary may change while queued or scheduled.
                # Validate the fixed route against the body actually dispatched.
                validate_body()
            if entry["private"]:
                token = self._general_token()
                headers["Authorization"] = "Bearer " + token
            try:
                # No retries and no redirects, even for GET: several GET routes
                # accept trades, send coins, cancel withdrawals or alter settings.
                async with session.request(entry["method"], self.BASE_URL + route,
                                           params=params or None, json=data, headers=headers,
                                           allow_redirects=False) as response:
                    try:
                        payload = await response.json()
                    except (ValueError, aiohttp.ContentTypeError):
                        assert_current()
                        if entry["private"] and response.status == 401:
                            raise AuthenticationError(401) from None
                        raise BitTeamAPIError(response.status if response.status >= 300 else 502) from None
                    assert_current()
                    if entry["private"] and response.status == 401:
                        # A request-level HTTP401 does not establish global token
                        # expiry. Never clear cookies, refresh or replay a mutation.
                        raise AuthenticationError(401)
                    if (not 200 <= response.status < 300 or isinstance(payload, dict) and (
                            payload.get("status") is False or payload.get("ok") is False or payload.get("errors"))):
                        raise BitTeamAPIError(response.status, payload.get("code") if isinstance(payload, dict) else None)
                    if isinstance(payload, dict) and payload.get("code", 200) != 200:
                        raise BitTeamAPIError(502)
                    shape = entry.get("response_shape", "")
                    if shape == "raw_json" or shape.startswith("ram_"):
                        _validate_ram_response(payload, shape)
                        return payload
                    if not isinstance(payload, dict):
                        raise BitTeamAPIError(502)
                    if entry.get("response_shape") == "auth_user":
                        if not isinstance(payload.get("account"), list):
                            raise BitTeamAPIError(502)
                        if "user" in payload and not isinstance(payload["user"], dict):
                            raise BitTeamAPIError(502)
                    elif entry.get("response_shape") == "withdrawal_create":
                        # The direct Axios call site reads response.data.data.id.
                        # Preserve the raw id and envelope; no success/finality
                        # or spot/order identifier relationship is inferred.
                        if not isinstance(payload.get("data"), dict) or "id" not in payload["data"]:
                            raise BitTeamAPIError(502)
                    elif payload.get("status") is not True or "data" not in payload:
                        raise BitTeamAPIError(502)
                    return payload
            except asyncio.TimeoutError:
                raise asyncio.TimeoutError("P2P request timed out; operation was not retried") from None
            except aiohttp.ClientError:
                raise BitTeamAPIError(0) from None

        if entry["private"]:
            return await auth._tracked_operation(send_once())
        return await send_once()

    async def close(self):
        if not self._closed:
            self._closed = True
            if self._session is not None:
                await self._session.close()

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, *exc):
        await self.close()


def _wrapper(name, entry):
    async def method(self, *, path=None, params=None, data=None):
        return await self.call(name, path=path, params=params, data=data)
    method.__name__ = name
    method.__qualname__ = "BitTeamP2PAPI." + name
    method.__doc__ = (f"{entry['method']} {entry['path']}. "
                      f"Private={entry['private']}; mutating GET={entry['get_mutation']}. "
                      "See schemas/p2p_site.json for confirmed helper parameters; raw JSON is explicit.")
    return method


for _name, _entry in P2P_CATALOG.items():
    setattr(BitTeamP2PAPI, _name, _wrapper(_name, _entry))
