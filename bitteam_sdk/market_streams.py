"""Public market push from the official site's nes v2 connection.

Confirmed 2026-11-03: wss://bit.team/trade/ws/ accepts anonymous hello and
subscriptions /prices, /pairs, /orderbooks/{pairId}, /trades/{pairId}. Actual
publications were observed for all four channels, including trade.new, during
the module's live check. These are raw events, not historical L2 snapshots.
"""
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ssl

import aiohttp

from .websocket import BitTeamWebSocket


class MarketStreamGap(ConnectionError):
    """A stream was replaced; missed events require consumer resynchronization."""


@dataclass(frozen=True)
class MarketEvent:
    channel: str
    path: str
    received_at: str
    payload: object
    source: str = "websocket"
    is_snapshot: bool = False


class MarketEventQueue(asyncio.Queue):
    def __init__(self, maxsize, path, channel):
        super().__init__(maxsize)
        self.path, self.channel = path, channel

    def put_nowait(self, item):
        if item is not None and not isinstance(item, (Exception, MarketEvent)):
            item = MarketEvent(self.channel, self.path, datetime.now(timezone.utc).isoformat(), item)
        return super().put_nowait(item)


@dataclass
class MarketSubscription:
    client: object
    path: str
    channel: str
    queue: asyncio.Queue
    closed: bool = False
    _terminal_error: object = field(default=None, repr=False)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.closed:
            raise StopAsyncIteration
        item = await self.queue.get()
        if item is None:
            self.closed = True
            raise StopAsyncIteration
        if isinstance(item, Exception):
            self.closed = True
            raise item
        # The timestamp was captured when the reader queued the publication,
        # not when a slow consumer finally retrieved it.
        return item

    async def close(self):
        if not self.closed:
            self.closed = True
            if self.client._subscriptions.get(self.path) is self:
                await self.client.unsubscribe(self.path)


def pair_identity(value):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError("pair_id must be a positive exchange pair id")
    text = str(value)
    if not text.isascii() or not text.isdigit() or int(text) <= 0:
        raise ValueError("pair_id must be a positive exchange pair id")
    return str(int(text))


class BitTeamMarketStreams(BitTeamWebSocket):
    """Bounded public raw-event subscriptions; no hidden reconnect or replay.

    On disconnect/overflow the iterator raises ConnectionError. Explicit
    reconnect(old_subscriptions) returns replacement iterators; acquire a new
    REST snapshot to resynchronize consumer state. No missed events are replayed.
    HTTP market snapshots stay on the REST client; tested market GET RPC paths
    returned 404 and are not represented as working WebSocket operations.
    """

    def __init__(self, *, url="wss://bit.team/trade/ws/", timeout=20, queue_size=1000):
        if isinstance(queue_size, bool) or not isinstance(queue_size, int) or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        super().__init__(url=url, timeout=timeout, queue_size=queue_size)
        self._subscription_lock = asyncio.Lock()

    async def _hello_payload(self):
        """Extension hook for separately reviewed session-backed subclasses."""
        return {"type": "hello", "version": "2", "auth": {"headers": {"Authorization": "jwt"}}}

    async def connect(self):
        async with self._connect_lock:
            if self.ws is not None and not self.ws.closed:
                return
            await self._stop_reader()
            # Call before opening the socket so authentication hook failures
            # cannot leave a connection or newly allocated session behind.
            hello = await self._hello_payload()
            if self._session is None or self._session.closed:
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    context = ssl.create_default_context()
                self._session = aiohttp.ClientSession(
                    connector=aiohttp.TCPConnector(ssl=context), cookie_jar=aiohttp.DummyCookieJar())
            try:
                self.ws = await asyncio.wait_for(
                    self._session.ws_connect(
                        self.url, protocols=["nes"], origin="https://bit.team",
                        max_msg_size=8 * 1024 * 1024, timeout=aiohttp.ClientWSTimeout(ws_close=5)),
                    self.timeout)
                self._reader_task = asyncio.create_task(self._reader())
                await self._rpc(hello)
            except BaseException:
                await self._close()
                raise

    async def _subscribe(self, path, channel):
        async with self._subscription_lock:
            return await self._subscribe_unlocked(path, channel)

    async def _subscribe_unlocked(self, path, channel):
        await self.connect()
        existing = self._subscriptions.get(path)
        if existing is not None and not existing.closed:
            return existing
        subscription = MarketSubscription(self, path, channel, MarketEventQueue(self.queue_size, path, channel))
        self._subscriptions[path] = subscription
        try:
            await self._rpc({"type": "sub", "path": path})
        except BaseException:
            self._subscriptions.pop(path, None)
            subscription.closed = True
            raise
        return subscription

    @staticmethod
    def _retire(subscription):
        # Replacing buffered events is explicit: the next read reports a gap,
        # even when a slow consumer filled the bounded queue before reconnect.
        while not subscription.queue.empty():
            subscription.queue.get_nowait()
        subscription._terminal_error = MarketStreamGap(
            "Market stream replaced; events may be missing, acquire a fresh snapshot")
        subscription.queue.put_nowait(subscription._terminal_error)

    async def reconnect(self, subscriptions):
        """Replace an explicit iterable of public subscriptions and return a path map.

        Keep the old subscription objects after a disconnect and pass them here.
        All previously active subscriptions end; only the supplied paths resume.
        No missed events are replayed and book events are not full snapshots.
        Resynchronize consumer state from REST before trusting the new stream.
        A failed/cancelled batch closes all new subscriptions; it never returns
        a partially restored set. Callers control retry timing and attempts.
        """
        requested = {}
        for subscription in subscriptions:
            if not isinstance(subscription, MarketSubscription) or subscription.client is not self:
                raise ValueError("Expected subscriptions belonging to this market stream")
            path, channel = subscription.path, subscription.channel
            valid = (path, channel) in (("/prices", "tickers"), ("/pairs", "pairs"))
            for prefix, expected in (("/orderbooks/", "orderbook"), ("/trades/", "trades")):
                if path.startswith(prefix) and channel == expected:
                    identity = path[len(prefix):]
                    valid = pair_identity(identity) == identity
            if not valid:
                raise ValueError("Expected a confirmed public market channel")
            requested[path] = subscription
        async with self._subscription_lock:
            old = {id(sub): sub for sub in self._subscriptions.values()}
            old.update({id(sub): sub for sub in requested.values()})
            # Retire before close yields to the reader or waiting consumers.
            for subscription in old.values():
                self._retire(subscription)
            await self.close()
            restored = {}
            try:
                await self.connect()
                for path, subscription in requested.items():
                    restored[path] = await self._subscribe_unlocked(path, subscription.channel)
                return restored
            except BaseException:
                for subscription in restored.values():
                    self._retire(subscription)
                await self.close()
                raise

    async def subscribe_tickers(self):
        return await self._subscribe("/prices", "tickers")

    async def subscribe_pairs(self):
        return await self._subscribe("/pairs", "pairs")

    async def subscribe_orderbook(self, pair_id):
        return await self._subscribe("/orderbooks/" + pair_identity(pair_id), "orderbook")

    async def subscribe_trades(self, pair_id):
        return await self._subscribe("/trades/" + pair_identity(pair_id), "trades")

    async def request(self, path, *, params=None):
        raise NotImplementedError("Use the REST client for public snapshots; market GET RPC was not available")

    async def subscribe_kline(self, symbol, interval="1m"):
        raise NotImplementedError("Use the separate history WebSocket for candles")


MarketStreams = BitTeamMarketStreams
