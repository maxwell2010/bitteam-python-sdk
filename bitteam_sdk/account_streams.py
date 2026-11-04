"""Session-backed website channels, isolated from anonymous market sockets."""
import asyncio
from dataclasses import dataclass
from yarl import URL

from .auth import SessionAuth, AuthState, AuthenticationError
from .market_streams import BitTeamMarketStreams, pair_identity


@dataclass
class AccountSubscription:
    stream: object
    subscription: object
    lifecycle: int

    def __aiter__(self):
        return self

    async def __anext__(self):
        self.stream._require_session(self.lifecycle)
        await self.stream.reauthenticate()
        item = await anext(self.subscription)
        self.stream._require_session(self.lifecycle)
        return item

    async def close(self):
        # An older wrapper must never unsubscribe its replacement at this path.
        if self.stream._subscriptions.get(self.subscription.path) is self.subscription:
            await self.subscription.close()
        else:
            self.subscription.closed = True

    async def resubscribe(self):
        """Return a fresh subscription. Missed events are not recovered."""
        self.stream._require_session(self.lifecycle)
        await self.close()
        return await self.stream._account_subscribe(
            self.subscription.path, self.subscription.channel,
            expected_lifecycle=self.lifecycle)


class BitTeamAccountStreams(BitTeamMarketStreams):
    def __init__(self, auth, *, url="wss://bit.team/trade/ws/", timeout=20, queue_size=1000):
        if not isinstance(auth, SessionAuth) or auth._transport is None:
            raise ValueError("Account streams require a bound SessionAuth")
        origin, target = URL(auth._transport.base_url), URL(url)
        if target.scheme != "wss" or target.host != origin.host or target.port != origin.port or target.user is not None:
            raise ValueError("Account WebSocket must use the configured spot API origin")
        super().__init__(url=url, timeout=timeout, queue_size=queue_size)
        self.auth = auth
        self._auth_generation = None
        self._reauth_lock = asyncio.Lock()
        self._connection_lifecycle = None
        self._reconnect_lock = asyncio.Lock()

    def _require_session(self, lifecycle=None):
        self.auth._assert_owner()
        if getattr(self.auth._transport, "_closed", False):
            raise RuntimeError("The owning BitTeam client is closed")
        if self.auth.state != AuthState.READY:
            raise AuthenticationError(401)
        if lifecycle is not None:
            self.auth._assert_lifecycle(lifecycle)

    def _validate_rpc(self):
        self._require_session(self._connection_lifecycle)

    async def _hello_payload(self):
        self._require_session()
        self._connection_lifecycle = self.auth._lifecycle
        self._auth_generation = self.auth.generation
        return {"type": "hello", "version": "2", "auth": {"headers": self.auth.headers()}}

    async def connect(self):
        lifecycle = self.auth._lifecycle
        self._require_session(lifecycle)
        # A new login is a new account boundary, even on the same auth object.
        if self._connection_lifecycle is not None and self._connection_lifecycle != lifecycle:
            await self.close()
        await super().connect()
        try:
            self._require_session(lifecycle)
        except BaseException:
            await self.close()
            raise
        self._connection_lifecycle = lifecycle

    async def reconnect(self, subscriptions=()):
        """Reconnect and return replacements keyed by path for explicit refs.

        Existing iterators terminate. This does not replay missed account events;
        reconcile balances/orders through REST before continuing consumption.
        No subscription is restored unless explicitly provided by the caller.
        """
        lifecycle = self.auth._lifecycle
        requested = tuple(subscriptions)
        for subscription in requested:
            if not isinstance(subscription, AccountSubscription) or subscription.stream is not self:
                raise ValueError("Expected account subscriptions belonging to this stream")
            self._require_session(subscription.lifecycle)
        async with self._reconnect_lock, self._subscription_lock:
            self._require_session(lifecycle)
            old = {id(sub): sub for sub in self._subscriptions.values()}
            old.update({id(proxy.subscription): proxy.subscription for proxy in requested})
            for subscription in old.values():
                self._retire(subscription)
            await self.close()
            self._require_session(lifecycle)
            await self.connect()
            replacements = {}
            try:
                for subscription in requested:
                    path = subscription.subscription.path
                    if path not in replacements:
                        replacements[path] = await self._account_subscribe_unlocked(
                            path, subscription.subscription.channel, expected_lifecycle=lifecycle)
                self._require_session(lifecycle)
            except BaseException:
                await self.close()
                raise
            return replacements

    async def reauthenticate(self):
        lifecycle = self.auth._lifecycle
        self._require_session(lifecycle)
        await self.connect()
        async with self._reauth_lock:
            self._require_session(lifecycle)
            while self._auth_generation != self.auth.generation:
                generation = self.auth.generation
                await self._rpc({"type": "reauth", "auth": {"headers": self.auth.headers()}})
                self._require_session(lifecycle)
                self._auth_generation = generation

    async def _account_subscribe(self, path, channel, *, expected_lifecycle=None):
        async with self._subscription_lock:
            return await self._account_subscribe_unlocked(
                path, channel, expected_lifecycle=expected_lifecycle)

    async def _account_subscribe_unlocked(self, path, channel, *, expected_lifecycle=None):
        lifecycle = self.auth._lifecycle if expected_lifecycle is None else expected_lifecycle
        self._require_session(lifecycle)
        await self.reauthenticate()
        self._require_session(lifecycle)
        subscription = await super()._subscribe_unlocked(path, channel)
        try:
            self._require_session(lifecycle)
        except BaseException:
            if self._subscriptions.get(path) is subscription:
                self._subscriptions.pop(path, None)
            subscription.closed = True
            raise
        return AccountSubscription(self, subscription, lifecycle)

    async def subscribe_balances(self):
        return await self._account_subscribe("/balances", "account_balances")

    async def subscribe_orders(self):
        return await self._account_subscribe("/orders", "account_orders")

    async def subscribe_user_trades(self, pair_id):
        return await self._account_subscribe("/userTrades/" + pair_identity(pair_id), "account_trades")

    async def subscribe_notifications(self, user_id):
        return await self._account_subscribe("/notifications/messages/" + pair_identity(user_id), "account_notifications")

    async def subscribe_chat(self, channel_id):
        return await self._account_subscribe("/user/chat/" + pair_identity(channel_id), "account_chat")

    async def _site_request(self, method, path, payload=None):
        lifecycle = self.auth._lifecycle
        await self.reauthenticate()
        self._require_session(lifecycle)
        frame = {"type": "request", "method": method, "path": path}
        if payload is not None:
            frame["payload"] = payload
        result = await self._rpc(frame)
        self._require_session(lifecycle)
        return result.get("payload")

    async def get_chat(self):
        return await self._site_request("GET", "/api/user/chats")

    async def send_chat_message(self, message, *, attachments=None):
        if not isinstance(message, str) or not message.strip() or len(message) > 10000:
            raise ValueError("A nonempty message of at most 10000 characters is required")
        if attachments is not None and not isinstance(attachments, list):
            raise ValueError("attachments must be a list of server attachment descriptors")
        return await self._site_request("POST", "/api/user/chats", {"message": message, "attachments": attachments or []})

    async def mark_notification_read(self, data):
        if not isinstance(data, dict):
            raise ValueError("Notification read payload must be a dictionary")
        return await self._site_request("POST", "/api/notification/message/read", data)
