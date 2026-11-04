"""High-level BitTeam client with API-key and interactive session login."""
from .rest import BitTeamRestAPI
from .auth import SessionAuth, PublicAuth, AuthState, LoginResult
from .services import ServiceMethods


class BitTeamClient(ServiceMethods):
    def __init__(self, api_key=None, api_secret=None, *, auth=None, private_key=None, **transport_options):
        if private_key is not None:
            if api_secret is not None:
                raise ValueError("Choose api_secret or private_key")
            api_secret = private_key
        self.rest = BitTeamRestAPI(api_key, api_secret, auth=auth, **transport_options)
        self._keys_validated = False
        self.api = self.rest.api
        self._history = None
        self._market = None
        self._account_streams = None
        self._site = None
        self._archive = None
        self._p2p = None
        self._closed = False
        self._close_task = None

    @property
    def auth(self):
        return self.rest.auth

    def _session_auth(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if not isinstance(self.auth, SessionAuth):
            raise RuntimeError("This operation requires SessionAuth")
        return self.auth

    async def init(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if isinstance(self.auth, PublicAuth):
            await self.rest._load_precisions()
            return LoginResult(AuthState.NEW)
        if isinstance(self.auth, SessionAuth):
            if self.auth.state == AuthState.NEW and self.auth.cache is not None:
                await self.auth.resume()
            if self.auth.state == AuthState.GENERAL_SESSION_READY:
                await self.auth.open_spot_session()
            if self.auth.state != AuthState.READY:
                return LoginResult(self.auth.state)
        else:
            if not await self.rest.validate_keys():
                raise ValueError("Invalid API key or secret")
            self._keys_validated = True
        await self.rest._load_precisions()
        return LoginResult(AuthState.READY)

    async def _finish_login_step(self, result):
        if result.lifecycle is not None:
            self.auth._assert_lifecycle(result.lifecycle)
        if result.state == AuthState.GENERAL_SESSION_READY:
            return await self.auth.open_spot_session()
        return result

    async def login(self, email, password):
        return await self._finish_login_step(await self._session_auth().login(email, password))

    async def submit_totp(self, code):
        return await self._finish_login_step(await self._session_auth().submit_totp(code))

    async def send_device_code(self):
        return await self._session_auth().send_device_code()

    async def confirm_device(self, code, *, remember=False):
        return await self._finish_login_step(await self._session_auth().confirm_device(code, remember=remember))

    async def open_spot_session(self):
        return await self._session_auth().open_spot_session()

    async def refresh(self):
        result = await self._session_auth().refresh()
        if self._account_streams is not None and self._account_streams.ws is not None and not self._account_streams.ws.closed:
            await self._account_streams.reauthenticate()
        return result

    async def logout(self):
        try:
            if self._account_streams is not None:
                await self._account_streams.close()
        finally:
            await self._session_auth().logout()

    async def resume_session(self, *, validate=True):
        return await self._session_auth().resume(validate=validate)

    async def clear_session(self):
        try:
            if self._account_streams is not None:
                await self._account_streams.close()
        finally:
            await self._session_auth().clear_session()

    def _require_ready(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if isinstance(self.auth, SessionAuth):
            if self.auth.state != AuthState.READY:
                raise RuntimeError("Complete session login before using private methods")
        elif not self._keys_validated:
            raise RuntimeError("Call init() first")

    async def get_balance(self):
        self._require_ready()
        return await self.rest.get_balance()

    async def create_order(self, symbol, side, type_="limit", price=None, amount=None):
        self._require_ready()
        return await self.rest.create_order(symbol, side, type_, price, amount)

    async def cancel_order(self, order_id):
        self._require_ready()
        return await self.rest.cancel_order(order_id)

    async def get_orders(self, symbol=None):
        self._require_ready()
        return await self.rest.get_orders(symbol)

    async def create_withdrawal(self, currency, address, amount, network=None, memo=None, *, currency_id=None):
        self._require_ready()
        return await self.rest.create_withdrawal(currency, address, amount, network, memo, currency_id=currency_id)

    async def close(self):
        import asyncio
        if self._close_task is None:
            self._closed = True
            self._close_task = asyncio.create_task(self._close_resources())
        # One caller cancelling must not abandon sockets or let another caller
        # return before shutdown actually finishes.
        await asyncio.shield(self._close_task)

    async def _close_resources(self):
        try:
            if isinstance(self.auth, SessionAuth):
                self.auth.save_session()
        finally:
            import asyncio
            resources = [self._history, self._market, self._account_streams, self._site, self._archive, self._p2p, self.rest]
            results = await asyncio.gather(*(r.close() for r in resources if r is not None), return_exceptions=True)
            for result in results:
                if isinstance(result, BaseException):
                    raise result

    @property
    def market(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._market is None:
            from .market_streams import BitTeamMarketStreams
            self._market = BitTeamMarketStreams()
        return self._market

    @property
    def account_streams(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._account_streams is None:
            from .account_streams import BitTeamAccountStreams
            self._account_streams = BitTeamAccountStreams(self._session_auth())
        return self._account_streams

    @property
    def site(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._site is None:
            from .site_api import BitTeamSiteAPI
            self._site = BitTeamSiteAPI()
        return self._site

    @property
    def archive(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._archive is None:
            from .archive import BitTeamArchive
            self._archive = BitTeamArchive(self.auth)
        return self._archive

    @property
    def p2p(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._p2p is None:
            from .p2p_api import BitTeamP2PAPI
            self._p2p = BitTeamP2PAPI(self.auth)
        return self._p2p

    @property
    def history(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        if self._history is None:
            from .websocket import BitTeamWebSocket
            self._history = BitTeamWebSocket()
        return self._history

    async def get_klines(self, symbol, interval="1m", *, start=None, end=None):
        return await self.history.get_klines(symbol, interval, start=start, end=end)

    async def fetch_klines(self, symbol, interval="1m", *, start, end, **bounds):
        from .history import fetch_klines
        return await fetch_klines(symbol, interval, start=start, end=end, source=self.history, **bounds)

    def iter_klines(self, symbol, interval="1m", *, start, end, **bounds):
        from .history import iter_klines
        return iter_klines(symbol, interval, start=start, end=end, source=self.history, **bounds)

    async def get_orderbook_snapshot(self, symbol):
        from .orderbook import OrderBookSnapshot
        from .services import symbol_name
        name = symbol_name(symbol)
        return OrderBookSnapshot.from_payload(await self.api.get_orderbooks_by_symbol(name), name)

    async def subscribe_orderbook(self, symbol):
        from .services import symbol_name
        return await self.market.subscribe_orderbook(await self.rest._pair_id(symbol_name(symbol)))

    async def subscribe_trades(self, symbol):
        from .services import symbol_name
        return await self.market.subscribe_trades(await self.rest._pair_id(symbol_name(symbol)))

    async def subscribe_kline(self, symbol, interval="1m"):
        return await self.history.subscribe_kline(symbol, interval)

    async def get_klines_df(self, symbol, interval="1m", *, start=None, end=None):
        from .models import Kline
        candles = await self.get_klines(symbol, interval, start=start, end=end)
        return Kline.to_dataframe([[k.open_time, k.open, k.high, k.low, k.close, k.volume] for k in candles])

    @staticmethod
    def plot_klines(frame, title="BitTeam"):
        from .charting import plot_candles
        return plot_candles(frame, title)

    async def __aenter__(self):
        if self._closed:
            raise RuntimeError("Client is closed")
        await self.rest._get_session()
        return self

    async def __aexit__(self, *exc):
        await self.close()
