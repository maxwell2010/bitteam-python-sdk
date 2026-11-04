"""Async BitTeam transport with isolated key and session authentication."""
import ssl
import asyncio
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
import aiohttp
from yarl import URL
from .auth import ApiKeyAuth, SessionAuth, PublicAuth, BitTeamAPIError, AuthenticationError
from .utils import RateLimiter, format_number


class BitTeamRestAPI:
    @property
    def auth(self):
        return self._auth

    @auth.setter
    def auth(self, value):
        if not isinstance(value, (ApiKeyAuth, SessionAuth, PublicAuth)):
            raise TypeError("Expected an SDK authentication strategy")
        previous = getattr(self, "_auth", None)
        if previous is value:
            return
        if hasattr(self, "base_url"):
            origins = {URL(self.base_url).origin()}
            if isinstance(value, SessionAuth):
                origins.add(URL(value.auth_url).origin())
            if any(origin.scheme != "https" for origin in origins):
                raise ValueError("Authentication requires HTTPS")
            if isinstance(value, SessionAuth):
                value.bind(self)
            self._allowed_origins = origins
        if previous is not None:
            if isinstance(previous, SessionAuth):
                # Identity alone can become equal again after A -> B -> A.
                # Retire the old epoch without clearing tokens or cache so
                # newly issued work can use an explicitly returned auth A.
                previous._lifecycle += 1
            try:
                current = asyncio.current_task()
            except RuntimeError:
                current = None
            for task in tuple(getattr(previous, "_pending_requests", ())):
                if task is not current and not task.done():
                    task.cancel()
            # A late Set-Cookie belongs to the old session, never to the new
            # owner. Do not reuse or copy the old cookie jar across identities.
            session = getattr(self, "_session", None)
            if session is not None:
                if not hasattr(self, "_retired_sessions"):
                    self._retired_sessions = []
                self._retired_sessions.append(session)
                self._session = None
        self._auth = value

    @auth.deleter
    def auth(self):
        # Missing auth also invalidates pending work and detaches cookies.
        self.auth = PublicAuth()
        del self._auth

    def __init__(self, api_key=None, api_secret=None, *, auth=None,
                 base_url="https://bit.team/trade/api", timeout=30, max_read_retries=2, max_retry_wait=30):
        if auth is not None and (api_key is not None or api_secret is not None):
            raise ValueError("Choose API keys or an auth strategy")
        self.auth = auth if auth is not None else (PublicAuth() if api_key is None and api_secret is None else ApiKeyAuth(api_key, api_secret))
        if not isinstance(self.auth, (ApiKeyAuth, SessionAuth, PublicAuth)):
            raise TypeError("Expected ApiKeyAuth or SessionAuth")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_read_retries = max_read_retries
        if isinstance(max_retry_wait, bool) or not isinstance(max_retry_wait, (int, float)) or not math.isfinite(max_retry_wait) or max_retry_wait < 0:
            raise ValueError("max_retry_wait must be a finite non-negative number")
        self.max_retry_wait = max_retry_wait
        if not isinstance(max_read_retries, int) or not 0 <= max_read_retries <= 5:
            raise ValueError("max_read_retries must be between 0 and 5")
        from .api import BitTeamAPI
        self.api = BitTeamAPI(self)
        self._precisions = None
        self._session = None
        self._retired_sessions = []
        self._retired_close_tasks = set()
        self._closed = False
        self._limiter = RateLimiter(max_calls=5, period=1)
        self._pairs = None
        self._allowed_origins = {URL(self.base_url).origin()}
        if isinstance(self.auth, SessionAuth):
            self._allowed_origins.add(URL(self.auth.auth_url).origin())
            self.auth.bind(self)
        if any(origin.scheme != "https" for origin in self._allowed_origins):
            raise ValueError("Authentication requires HTTPS")

    async def _get_session(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        await self._close_retired_sessions()
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._session is None:
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context = ssl.create_default_context()
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                connector=aiohttp.TCPConnector(ssl=context),
                cookie_jar=aiohttp.CookieJar() if self._session_mode else aiohttp.DummyCookieJar())
        return self._session

    async def _close_retired_sessions(self):
        sessions, self._retired_sessions = self._retired_sessions, []
        if sessions:
            async def close_batch():
                results = await asyncio.gather(*(session.close() for session in sessions), return_exceptions=True)
                for result in results:
                    if isinstance(result, BaseException):
                        raise result
            task = asyncio.create_task(close_batch())
            # Retain work across caller cancellation and share it with close().
            self._retired_close_tasks.add(task)
            task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        tasks = tuple(self._retired_close_tasks)
        if tasks:
            results = await asyncio.gather(*(asyncio.shield(task) for task in tasks), return_exceptions=True)
            # A failed close must remain observable to later close() callers;
            # forgetting it would turn an unclosed retired session into success.
            self._retired_close_tasks.difference_update(
                task for task in tasks
                if task.done() and not task.cancelled() and task.exception() is None)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    async def clear_cookies(self):
        if self._session is not None:
            self._session.cookie_jar.clear()

    def set_spot_cookies(self, access, refresh):
        if self._session is None:
            raise RuntimeError("HTTP session has not been initialized")
        cookies = SimpleCookie()
        for key, value in (("access", access), ("refresh", refresh)):
            cookies[key] = value
            cookies[key]["path"] = URL(self.base_url).path
            cookies[key]["secure"] = True
        self._session.cookie_jar.update_cookies(cookies, response_url=URL(self.base_url))

    async def _send(self, method, url, *, params=None, data=None, headers=None):
        auth = self.auth
        lifecycle = auth._lifecycle if isinstance(auth, SessionAuth) else None
        def assert_current():
            self._assert_request_auth(auth, lifecycle)
        target = URL(url)
        if target.origin() not in self._allowed_origins or target.user is not None:
            raise ValueError("Request origin is not configured for this client")
        await self._limiter.acquire()
        assert_current()
        session = await self._get_session()
        assert_current()
        async with session.request(method, target, params=params, json=data,
                                   headers=headers or {}, allow_redirects=False) as response:
            try:
                result = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                assert_current()
                raise BitTeamAPIError(response.status) from None
            assert_current()
            if response.status >= 300 or (isinstance(result, dict) and result.get("ok") is False):
                error = AuthenticationError if response.status == 401 else BitTeamAPIError
                retry_after = None
                raw_retry = response.headers.get("Retry-After")
                if raw_retry is not None:
                    try:
                        delay = float(raw_retry)
                        if math.isfinite(delay):
                            retry_after = max(0, delay)
                    except ValueError:
                        try:
                            when = parsedate_to_datetime(raw_retry)
                            if when.tzinfo is None:
                                when = when.replace(tzinfo=timezone.utc)
                            retry_after = max(0, (when - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError, OverflowError):
                            pass
                raise error(response.status, result.get("code") if isinstance(result, dict) else None, retry_after=retry_after)
            return result

    def _get_auth_header(self):
        return self.auth.headers()

    def _assert_request_auth(self, auth, lifecycle):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self.auth is not auth:
            raise asyncio.CancelledError("Authentication operation was invalidated")
        if isinstance(auth, SessionAuth):
            auth._assert_lifecycle(lifecycle)

    async def _request(self, method, endpoint, params=None, data=None, *, public=False):
        if not endpoint.startswith("/") or endpoint.startswith("//"):
            raise ValueError("Expected a relative API endpoint")
        auth = self.auth
        session_mode = isinstance(auth, SessionAuth)
        generation = auth.generation if session_mode else None
        headers = {} if public else auth.headers()
        # Public responses share the session cookie jar too. Cancel every HTTP
        # exchange on an account boundary, including anonymous market reads.
        lifecycle = auth._lifecycle if session_mode else None
        async def exchange(request_headers):
            async def dispatch():
                self._assert_request_auth(auth, lifecycle)
                result = await self._send(method, self.base_url + endpoint,
                    params=params, data=data, headers=request_headers)
                self._assert_request_auth(auth, lifecycle)
                return result
            self._assert_request_auth(auth, lifecycle)
            if session_mode:
                return await auth._tracked_operation(dispatch())
            return await dispatch()
        safe_read = (method.upper() == "GET" and not endpoint.endswith("/create")
            and not endpoint.startswith(("/login-confirmation", "/phone/checkValidation", "/sumsub/obtain", "/forgot-2fa")))
        async def send():
            for attempt in range(self.max_read_retries + 1):
                try:
                    return await exchange(headers)
                except BitTeamAPIError as error:
                    if not safe_read or error.status not in (429, 503) or attempt == self.max_read_retries:
                        raise
                    delay = error.retry_after if error.retry_after is not None else min(2 ** attempt, 5)
                    if delay > self.max_retry_wait:
                        raise
                    await asyncio.sleep(delay)
        try:
            return await send()
        except BitTeamAPIError as exc:
            # Retry one read on an explicit expired-token response. Never replay
            # mutations, network timeouts, or arbitrary 401/403 failures.
            if (not public and session_mode and safe_read
                    and exc.code == 401000 and exc.status in (200, 401)):
                self._assert_request_auth(auth, lifecycle)
                await auth.refresh(expected_generation=generation)
                self._assert_request_auth(auth, lifecycle)
                return await exchange(auth.headers())
            raise

    @property
    def _session_mode(self):
        return isinstance(self.auth, SessionAuth)

    async def get_balance(self):
        # The web account uses wallets. /stock/balance is a different stock/P2P
        # integration and rejects a valid user access token (verified live).
        params = {"limit": 1000, "offset": 0} if self._session_mode else None
        return await self._request("GET", "/address/wallets" if self._session_mode else "/ccxt/balance", params=params)

    async def _pair_id(self, symbol):
        if self._pairs is None:
            response = await self._request("GET", "/pairs", public=True)
            result = response.get("result", {})
            self._pairs = result.get("pairs", []) if isinstance(result, dict) else result
            if not isinstance(self._pairs, list):
                raise BitTeamAPIError(502)
        wanted = symbol.replace("/", "_").lower()
        for pair in self._pairs:
            if str(pair.get("name", pair.get("symbol", ""))).replace("/", "_").lower() == wanted:
                return pair["id"]
        raise ValueError("Unknown trading pair")

    async def create_order(self, symbol, side, type_, price, amount):
        from decimal import Decimal, InvalidOperation
        from .services import symbol_name
        symbol = symbol_name(symbol)
        if side not in ("buy", "sell") or type_ not in ("limit", "market"):
            raise ValueError("Invalid order side or type")
        for value in [amount] + ([price] if price is not None else []):
            try:
                number = Decimal(str(value))
                if not number.is_finite() or number <= 0:
                    raise ValueError("Order values must be finite and positive")
            except InvalidOperation:
                raise ValueError("Invalid decimal order value") from None
        if type_ == "limit" and price is None:
            raise ValueError("Limit orders require a price")
        if self._session_mode and price is None:
            raise ValueError("The documented session order endpoint requires price")
        pair_id = await self._pair_id(symbol)
        if self._precisions is None:
            await self._load_precisions()
        precision = self._precisions.get(symbol.replace("/", "_").lower())
        if precision:
            price = format_number(price, precision["price"]) if price is not None else None
            amount = format_number(amount, precision["amount"])
        if Decimal(str(amount)) <= 0 or (price is not None and Decimal(str(price)) <= 0):
            raise ValueError("Order values are zero after precision rounding")
        payload = {"pairId": pair_id if self._session_mode else str(pair_id), "side": side, "type": type_, "amount": str(amount)}
        if price is not None:
            payload["price"] = str(price)
        return await self._request("POST", "/order/create" if self._session_mode else "/ccxt/ordercreate", data=payload)

    async def cancel_order(self, order_id):
        return await self._request("POST", "/order/cancel" if self._session_mode else "/ccxt/cancelorder",
                                   data={"id": int(order_id) if self._session_mode else str(order_id)})

    async def get_orders(self, symbol=None):
        from .services import symbol_name
        params = {"type": "active"}
        if symbol:
            name = symbol_name(symbol)
            if self._session_mode:
                params["where[pairId]"] = await self._pair_id(name)
            else:
                params["pair"] = name
        return await self._request("GET", "/ordersByUser" if self._session_mode else "/ccxt/ordersOfUser", params=params)

    async def create_withdrawal(self, currency, address, amount, network=None, memo=None, *, currency_id=None):
        if memo is not None:
            raise ValueError("Memo is not documented for this withdrawal endpoint")
        from .withdrawal import decimal_value
        quantity = decimal_value(amount)
        if quantity is None or quantity <= 0:
            raise ValueError("Withdrawal amount must be positive and finite")
        if currency_id is not None and (isinstance(currency_id, bool) or not isinstance(currency_id, int) or currency_id <= 0):
            raise ValueError("currency_id must be a positive integer")
        if not isinstance(currency, str) or not currency.strip():
            raise ValueError("Currency must be a nonempty string")
        if not isinstance(address, str) or not address.strip() or any(c.isspace() for c in address.strip()):
            raise ValueError("Withdrawal address must be a nonempty string without internal whitespace")
        amount, address = format(quantity, "f"), address.strip()
        if network is not None or str(currency).lower() == "usdt":
            from .withdrawal import prepare_withdrawal
            response = await self._request("GET", "/currencies", params={"limit": 1000, "offset": 0}, public=True)
            catalog = response.get("result", {}).get("currencies")
            if not isinstance(catalog, list):
                raise BitTeamAPIError(502)
            plan = prepare_withdrawal(catalog, currency, amount=amount, address=address, network=network, currency_id=currency_id)
            return await self._request("POST", "/withdraw/create" if self._session_mode else "/ccxt/withdraw", data=plan["payload"])
        if currency_id is None:
            raise ValueError("currency_id is required by the current BitTeam API")
        return await self._request("POST", "/withdraw/create" if self._session_mode else "/ccxt/withdraw", data={
            "currencyId": currency_id, "currency": currency, "to": address, "amount": amount})

    async def get_precisions(self):
        response = await self._request("GET", "/pairs/precisions", public=True)
        result = response.get("result", {})
        if isinstance(result, dict):
            result = result.get("pairs", result)
        if not isinstance(result, dict):
            return {}
        def decimals(value):
            return int(value["decimals"] if isinstance(value, dict) else value)
        return {symbol.replace("/", "_").lower(): {"price": decimals(values["price"]), "amount": decimals(values["amount"])}
                for symbol, values in result.items() if isinstance(values, dict) and "price" in values and "amount" in values}

    async def validate_keys(self):
        if self._session_mode:
            raise RuntimeError("Key validation is only available for ApiKeyAuth")
        try:
            response = await self.get_balance()
            return response.get("ok") is not False and "error" not in response
        except BitTeamAPIError:
            return False

    async def _load_precisions(self):
        self._precisions = await self.get_precisions()

    async def close(self):
        self._closed = True
        try:
            if self._session is not None:
                await self._session.close()
        finally:
            await self._close_retired_sessions()

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, *exc):
        await self.close()
