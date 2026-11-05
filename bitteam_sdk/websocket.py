"""Public BitTeam history WebSocket using the observed nes v2 protocol.

The old stream.bit.team/HMAC protocol was not verified. This implementation
uses history.bit.team, as the official trading page does, without credentials.
"""
import asyncio
import json
import ssl
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import urlencode

import aiohttp
from yarl import URL

from .auth import BitTeamAPIError
from .models import Kline
from .services import symbol_name


def sanitized_transport(operation):
    """Keep untrusted transport diagnostics out of public exception messages."""
    @wraps(operation)
    async def wrapped(*args, **kwargs):
        try:
            return await operation(*args, **kwargs)
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("WebSocket operation timed out; operation was not retried") from None
        except aiohttp.ClientError:
            raise ConnectionError("WebSocket transport failed; operation was not retried") from None
    return wrapped


RESOLUTIONS = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "1d": "1D"}
STREAM_RESOLUTIONS = {"1m": "1m", "5m": "5m", "15m": "15", "1h": "1h", "1d": "1d"}


def validate_candle_values(values):
    """Reject missing, nonfinite or negative market values without rounding."""
    try:
        parsed = [Decimal(str(value)) for value in values]
    except InvalidOperation:
        raise ValueError("Invalid candle values") from None
    if any(not value.is_finite() or value < 0 for value in parsed):
        raise ValueError("Invalid candle values")


def candle(symbol, interval, data):
    if not isinstance(data, dict):
        raise BitTeamAPIError(502)
    t = data.get("t", data.get("time"))
    names = [("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"), ("v", "volume")]
    try:
        values = [str(data[short] if short in data else data[long]) for short, long in names]
        validate_candle_values(values)
        seconds = Decimal(str(t))
        if not seconds.is_finite() or seconds < 0 or seconds != seconds.to_integral_value():
            raise ValueError("Invalid candle timestamp")
        return Kline(symbol.upper(), interval, int(seconds) * 1000, *values)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise BitTeamAPIError(502) from None


class KlineStreamGap(ConnectionError):
    """History subscription was replaced; reconcile candles through history reads."""


@dataclass
class KlineSubscription:
    client: object
    path: str
    symbol: str
    interval: str
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
        if not isinstance(item, dict):
            raise BitTeamAPIError(502)
        result = candle(self.symbol, self.interval, item.get("result", item))
        if self.client.storage:
            await self.client.storage.save_kline(result)
        return result

    async def close(self):
        if not self.closed:
            self.closed = True
            if self.client._subscriptions.get(self.path) is self:
                await self.client.unsubscribe(self.path, _expected=self)


class BitTeamWebSocket:
    def __init__(self, api_key=None, api_secret=None, storage=None, *,
                 url="wss://history.bit.team/api/", timeout=20, queue_size=1000):
        if api_key is not None or api_secret is not None:
            raise NotImplementedError("This is the public history connection; use REST for private operations")
        if URL(url).scheme != "wss":
            raise ValueError("WebSocket requires WSS")
        if isinstance(queue_size, bool) or not isinstance(queue_size, int) or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        self.url, self.timeout, self.storage = url, timeout, storage
        self.queue_size = queue_size
        self.ws = None
        self._session = None
        self._reader_task = None
        self._connect_lock = asyncio.Lock()
        self._subscription_lock = asyncio.Lock()
        self._pending = {}
        self._subscriptions = {}
        self._sequence = 0
        self._subscription_cleanup = None
        self._owner_guard = None

    def _assert_owner_open(self):
        # Standalone streams remain reusable after close; a client-owned stream
        # must never reconnect after that client's permanent close boundary.
        if self._owner_guard is not None:
            self._owner_guard()

    @sanitized_transport
    async def connect(self):
        self._assert_owner_open()
        await self._await_subscription_cleanup()
        self._assert_owner_open()
        async with self._connect_lock:
            self._assert_owner_open()
            if self.ws is not None and not self.ws.closed:
                return
            await self._stop_reader()
            self._assert_owner_open()
            if self._session is None or self._session.closed:
                try:
                    import certifi
                    context = ssl.create_default_context(cafile=certifi.where())
                except ImportError:
                    context = ssl.create_default_context()
                self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context),
                                                      cookie_jar=aiohttp.DummyCookieJar())
            try:
                self.ws = await asyncio.wait_for(
                    self._session.ws_connect(self.url, protocols=["nes"], origin="https://bit.team",
                                             max_msg_size=8 * 1024 * 1024,
                                             timeout=aiohttp.ClientWSTimeout(ws_close=5)),
                    self.timeout)
                self._assert_owner_open()
            except BaseException:
                await self._close_after_failure(locked=True)
                raise
            self._reader_task = asyncio.create_task(self._reader())
            try:
                await self._rpc({"type": "hello", "version": "2", "auth": {"headers": {"Authorization": "jwt"}}})
                self._assert_owner_open()
            except BaseException:
                await self._close_after_failure(locked=True)
                raise

    async def _stop_reader(self):
        """Finish the previous reader before a replacement may own registries."""
        task = self._reader_task
        if task is not None and task is not asyncio.current_task():
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if self._reader_task is task:
                self._reader_task = None

    def _validate_rpc(self):
        """Hook for private streams to check the owner at dispatch boundaries."""
        self._assert_owner_open()

    @sanitized_transport
    async def _rpc(self, payload):
        self._validate_rpc()
        if self._subscription_cleanup is not None and not self._subscription_cleanup.done():
            raise ConnectionError("Subscription state is uncertain; connection is retiring")
        if self.ws is None or self.ws.closed:
            raise ConnectionError("History WebSocket is disconnected")
        self._sequence += 1
        identity = self._sequence
        future = asyncio.get_running_loop().create_future()
        self._pending[identity] = future
        async def exchange():
            self._validate_rpc()
            await self.ws.send_json(dict(payload, id=identity))
            self._validate_rpc()
            result = await future
            self._validate_rpc()
            return result

        try:
            # Backpressure while sending belongs to the same RPC deadline.
            result = await asyncio.wait_for(exchange(), self.timeout)
            self._validate_rpc()
            return result
        finally:
            self._pending.pop(identity, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                # A disconnect may fail the reply while send_json is blocked.
                future.exception()

    def _notify_error(self, error):
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(error)
        for subscription in list(self._subscriptions.values()):
            if subscription.queue.full():
                subscription.queue.get_nowait()
            subscription.queue.put_nowait(getattr(subscription, "_terminal_error", None) or error)

    async def _reader(self):
        socket = self.ws
        chunks = []
        size = 0
        try:
            while True:
                message = await asyncio.wait_for(socket.receive(), 45)
                if message.type != aiohttp.WSMsgType.TEXT:
                    if message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.ERROR):
                        break
                    continue
                raw = message.data
                if not raw.startswith("{"):
                    if not raw or raw[0] not in ("+", "!"):
                        raise ConnectionError("Invalid nes frame")
                    chunks.append(raw[1:])
                    size += len(raw)
                    if size > 8 * 1024 * 1024:
                        raise ConnectionError("History message is too large")
                    if raw[0] != "!":
                        continue
                    raw, chunks, size = "".join(chunks), [], 0
                frame = json.loads(raw)
                if frame.get("type") == "ping":
                    await socket.send_json({"type": "ping"})
                    continue
                if frame.get("type") in ("pub", "revoke"):
                    sub = self._subscriptions.get(frame.get("path"))
                    if sub is not None:
                        if frame["type"] == "revoke":
                            self._subscriptions.pop(frame.get("path"), None)
                            while not sub.queue.empty():
                                sub.queue.get_nowait()
                            sub.queue.put_nowait(ConnectionError("Subscription revoked"))
                        elif sub.queue.full():
                            raise ConnectionError("Subscription queue overflow; resynchronize history")
                        else:
                            sub.queue.put_nowait(frame.get("message", {}))
                    continue
                future = self._pending.get(frame.get("id"))
                if future is not None and not future.done():
                    payload = frame.get("payload")
                    status = frame.get("statusCode", 200)
                    if status >= 400 or (isinstance(payload, dict) and payload.get("ok") is False):
                        future.set_exception(BitTeamAPIError(status, payload.get("code") if isinstance(payload, dict) else None))
                    else:
                        future.set_result(frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._notify_error(ConnectionError("History WebSocket receive failed"))
        finally:
            self._notify_error(ConnectionError("History WebSocket is disconnected"))
            self._subscriptions.clear()
            if not socket.closed:
                await socket.close()

    async def request(self, path, *, params=None):
        if not path.startswith("/api/tw/") or ".." in path or "?" in path or "#" in path:
            raise ValueError("Expected a public /api/tw/ history path")
        await self.connect()
        if params:
            path += "?" + urlencode(params)
        frame = await self._rpc({"type": "request", "method": "GET", "path": path})
        return frame.get("payload")

    async def get_config(self):
        return await self.request("/api/tw/config")

    async def get_server_time(self):
        return await self.request("/api/tw/time")

    async def get_symbol(self, symbol):
        return await self.request("/api/tw/pairs/" + symbol_name(symbol))

    async def get_klines(self, symbol, interval="1m", *, start=None, end=None):
        if interval not in RESOLUTIONS:
            raise ValueError("Unsupported candle interval")
        end = int(time.time()) if end is None else int(end)
        start = end - 86400 if start is None else int(start)
        if start < 0 or start >= end:
            raise ValueError("Expected Unix seconds with start < end")
        name = symbol_name(symbol)
        payload = await self.request("/api/tw/history/" + name.upper() + "/" + RESOLUTIONS[interval],
                                     params={"from": start, "to": end})
        result = payload.get("result") if isinstance(payload, dict) else None
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, list):
            raise BitTeamAPIError(502)
        result = [candle(name, interval, item) for item in data]
        return sorted(result, key=lambda k: k.open_time)

    async def subscribe_kline(self, symbol, interval="1m"):
        if interval not in STREAM_RESOLUTIONS:
            raise ValueError("Unsupported candle interval")
        async with self._subscription_lock:
            return await self._subscribe_kline(symbol, interval)

    async def _subscribe_kline(self, symbol, interval):
        self._assert_owner_open()
        await self.connect()
        self._assert_owner_open()
        name = symbol_name(symbol)
        path = "/klines/" + name + "/" + STREAM_RESOLUTIONS[interval]
        existing = self._subscriptions.get(path)
        if existing is not None and not existing.closed:
            return existing
        subscription = KlineSubscription(self, path, name, interval, asyncio.Queue(self.queue_size))
        self._subscriptions[path] = subscription
        try:
            await self._rpc({"type": "sub", "path": path})
            self._assert_owner_open()
        except BaseException:
            await self._retire_uncertain_subscription()
            raise
        return subscription

    @staticmethod
    def _retire(subscription):
        while not subscription.queue.empty():
            subscription.queue.get_nowait()
        subscription._terminal_error = KlineStreamGap(
            "History stream replaced; candles may be missing, reconcile history")
        subscription.queue.put_nowait(subscription._terminal_error)

    async def reconnect(self, subscriptions):
        """Return explicit replacement candle subscriptions keyed by path.

        Old iterators signal a gap. No replay or missed-candle recovery is
        promised; reconcile through get_klines using application-held bounds.
        Failure/cancellation closes the partial batch and returns no replacements.
        """
        self._assert_owner_open()
        requested = {}
        for subscription in subscriptions:
            if not isinstance(subscription, KlineSubscription) or subscription.client is not self:
                raise ValueError("Expected history subscriptions belonging to this connection")
            if subscription.interval not in STREAM_RESOLUTIONS:
                raise ValueError("Expected a supported history candle interval")
            name = symbol_name(subscription.symbol)
            path = "/klines/" + name + "/" + STREAM_RESOLUTIONS[subscription.interval]
            if subscription.symbol != name or subscription.path != path:
                raise ValueError("Expected an unchanged history subscription path")
            requested[path] = subscription
        async with self._subscription_lock:
            self._assert_owner_open()
            old = {id(sub): sub for sub in self._subscriptions.values()}
            old.update({id(sub): sub for sub in requested.values()})
            for subscription in old.values():
                self._retire(subscription)
            await self.close()
            self._assert_owner_open()
            restored = {}
            try:
                await self.connect()
                self._assert_owner_open()
                for path, subscription in requested.items():
                    restored[path] = await self._subscribe_kline(subscription.symbol, subscription.interval)
                    self._assert_owner_open()
                return restored
            except BaseException:
                for subscription in restored.values():
                    self._retire(subscription)
                await self._close_after_failure()
                raise

    async def _close_after_failure(self, *, locked=False):
        """Finish cleanup without replacing an already active primary failure."""
        try:
            if locked:
                await self._close()
            else:
                await self.close()
        except BaseException:
            # A failed shutdown must not let the next connect reuse this socket.
            self.ws = None

    async def _await_subscription_cleanup(self):
        task = self._subscription_cleanup
        if task is not None:
            await asyncio.shield(task)

    async def _retire_uncertain_subscription(self):
        """A missing ACK cannot establish the server's subscription state."""
        self._notify_error(ConnectionError("Subscription acknowledgement lost; resynchronize stream"))
        self._subscriptions.clear()

        async def cleanup():
            async with self._connect_lock:
                try:
                    await self._close()
                except BaseException:
                    # Even a failed transport close must not allow socket reuse.
                    self.ws = None
                    raise

        task = asyncio.create_task(cleanup())
        self._subscription_cleanup = task
        # Retrieve failures even if another cancellation interrupts this waiter.
        task.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            await asyncio.shield(task)
        except BaseException:
            # Preserve the initiating RPC error/cancellation, not a close error.
            pass

    async def unsubscribe(self, path, *, _expected=None):
        async with self._subscription_lock:
            if _expected is not None and self._subscriptions.get(path) is not _expected:
                return
            await self._unsubscribe_unlocked(path)

    async def _unsubscribe_unlocked(self, path):
        sub = self._subscriptions.pop(path, None)
        if sub is not None:
            while not sub.queue.empty():
                sub.queue.get_nowait()
            sub.queue.put_nowait(None)
            if self.ws is not None and not self.ws.closed:
                try:
                    await self._rpc({"type": "unsub", "path": path})
                except BaseException:
                    await self._retire_uncertain_subscription()
                    raise

    @sanitized_transport
    async def close(self):
        async with self._connect_lock:
            await self._close()

    async def _close(self):
        for future in list(self._pending.values()):
            if not future.done():
                future.set_exception(ConnectionError("WebSocket is closed"))
        failure = None
        try:
            if self.ws is not None:
                await self.ws.close()
        except BaseException as error:
            failure = error
        try:
            await self._stop_reader()
        except BaseException as error:
            if failure is None:
                failure = error
        try:
            if self._session is not None:
                await self._session.close()
        except BaseException as error:
            if failure is None:
                failure = error
        finally:
            for sub in self._subscriptions.values():
                while not sub.queue.empty():
                    sub.queue.get_nowait()
                sub.queue.put_nowait(getattr(sub, "_terminal_error", None))
            self._subscriptions.clear()
        if failure is not None:
            raise failure

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self.close()
