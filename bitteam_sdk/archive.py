"""Website archive contract. Availability is independent of the spot API.

The official site uses this host for old trades/orders. Public archive probes
timed out during discovery; callers receive real errors, never fake history.
"""
import aiohttp
import asyncio
import ssl
from .auth import SessionAuth, AuthState, AuthenticationError, BitTeamAPIError
from .endpoints import query_params


class BitTeamArchive:
    BASE_URL = "https://archive.bit.team/api"

    def __init__(self, auth, *, timeout=15):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise ValueError("Archive timeout must be between 0 and 60 seconds")
        self.auth, self.timeout, self._session = auth, timeout, None
        self._closed = False

    async def _get_session(self):
        if self._closed:
            raise RuntimeError("Archive client is closed")
        if self._session is None:
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context = ssl.create_default_context()
            self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context),
                timeout=aiohttp.ClientTimeout(total=self.timeout), cookie_jar=aiohttp.DummyCookieJar(), trust_env=False)
        return self._session

    async def _request(self, endpoint, *, params=None, private=False):
        if self._closed:
            raise RuntimeError("Archive client is closed")
        if endpoint not in ("/trades", "/ordersByUser", "/tradesByUser"):
            raise ValueError("Unsupported archive endpoint")
        if params is not None and not isinstance(params, dict):
            raise ValueError("Archive query parameters must be a dictionary")
        for key in ("limit", "page", "offset"):
            if params is not None and key in params:
                value = params[key]
                low, high = (0, 1000000) if key == "offset" else (1, 1000 if key == "limit" else 1000000)
                if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                    raise ValueError("Invalid archive " + key)
        headers = {}
        lifecycle = None
        auth = self.auth
        if private:
            if not isinstance(self.auth, SessionAuth) or self.auth.state != AuthState.READY:
                raise AuthenticationError(401)
            transport = self.auth._transport
            if transport is None:
                raise AuthenticationError(401)
            if transport._closed:
                raise RuntimeError("The owning BitTeam client is closed")
            if (transport.base_url.rstrip("/") != "https://bit.team/trade/api" or
                    self.auth.auth_url.rstrip("/") != "https://auth2.bit.team/v1"):
                raise ValueError("Production archive cannot receive credentials from a different API configuration")
            headers = self.auth.headers()
            lifecycle = self.auth._lifecycle

        def assert_current():
            if self._closed:
                raise RuntimeError("Archive client is closed")
            if private:
                if self.auth is not auth:
                    raise asyncio.CancelledError("Authentication operation was invalidated")
                auth._assert_lifecycle(lifecycle)
                if transport._closed:
                    raise RuntimeError("The owning BitTeam client is closed")

        session = await self._get_session()
        assert_current()
        try:
            async with session.get(self.BASE_URL + endpoint, params=query_params(params), headers=headers, allow_redirects=False) as response:
                try:
                    result = await response.json()
                except (ValueError, aiohttp.ContentTypeError):
                    raise BitTeamAPIError(response.status if response.status >= 300 else 502) from None
                assert_current()
                if (not 200 <= response.status < 300 or (isinstance(result, dict) and
                        (result.get("ok") is False or result.get("status") is False or result.get("errors")))):
                    raise BitTeamAPIError(response.status, result.get("code") if isinstance(result, dict) else None)
                if not isinstance(result, (dict, list)):
                    raise BitTeamAPIError(502)
                return result
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Archive request timed out; operation was not retried") from None
        except aiohttp.ClientError:
            raise BitTeamAPIError(0) from None

    async def get_trades(self, *, params=None):
        return await self._request("/trades", params=params)

    async def get_user_orders(self, *, params=None):
        return await self._request("/ordersByUser", params=params, private=True)

    async def get_user_trades(self, *, params=None):
        return await self._request("/tradesByUser", params=params, private=True)

    async def close(self):
        if not self._closed:
            self._closed = True
            if self._session is not None:
                await self._session.close()
