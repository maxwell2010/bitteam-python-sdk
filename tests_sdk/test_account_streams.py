"""Private stream contracts with synthetic sessions, without a real account."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import ApiKeyAuth, SessionAuth, AuthState, AuthenticationError
from bitteam_sdk.account_streams import BitTeamAccountStreams
from bitteam_sdk.market_streams import BitTeamMarketStreams
from bitteam_sdk.rest import BitTeamRestAPI


class FakeSocket:
    closed = False

    async def close(self):
        self.closed = True


def connected_account():
    auth = SessionAuth()
    transport = BitTeamRestAPI(auth=auth)
    auth.state = AuthState.READY
    auth._access = "synthetic-private-spot-access"
    auth._refresh = "synthetic-private-spot-refresh"
    stream = BitTeamAccountStreams(auth)
    stream.ws = FakeSocket()
    stream._rpc = AsyncMock(return_value={"payload": {"ok": True}})
    stream._auth_generation = auth.generation
    return auth, transport, stream


@pytest.mark.asyncio
async def test_private_hello_uses_spot_bearer_and_public_hello_never_receives_it():
    auth, transport, stream = connected_account()
    public = BitTeamMarketStreams()
    try:
        hello = await stream._hello_payload()
        assert hello == {"type": "hello", "version": "2", "auth": {
            "headers": {"Authorization": "Bearer synthetic-private-spot-access"}}}
        public_hello = await public._hello_payload()
        assert public_hello["auth"]["headers"]["Authorization"] == "jwt"
        assert "synthetic-private" not in repr(public_hello)
    finally:
        await stream.close()
        await transport.close()
        await public.close()


@pytest.mark.parametrize("url", [
    "wss://untrusted.test/trade/ws/", "ws://bit.team/trade/ws/",
    "wss://bit.team:444/trade/ws/", "wss://user@example.test/trade/ws/",
])
def test_private_socket_origin_cannot_differ_from_bound_spot_api(url):
    auth = SessionAuth()
    BitTeamRestAPI(auth=auth)
    with pytest.raises(ValueError):
        BitTeamAccountStreams(auth, url=url)


@pytest.mark.parametrize("auth", [SessionAuth(), ApiKeyAuth("synthetic-key", "synthetic-secret")])
def test_private_stream_requires_bound_session_auth(auth):
    with pytest.raises(ValueError):
        BitTeamAccountStreams(auth)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,path,channel", [
    ("subscribe_balances", (), "/balances", "account_balances"),
    ("subscribe_orders", (), "/orders", "account_orders"),
    ("subscribe_user_trades", (24,), "/userTrades/24", "account_trades"),
    ("subscribe_notifications", (123,), "/notifications/messages/123", "account_notifications"),
    ("subscribe_chat", (42,), "/user/chat/42", "account_chat"),
])
async def test_confirmed_account_paths_are_bound_to_current_lifecycle(method,args,path,channel):
    auth, transport, stream = connected_account()
    try:
        proxy = await getattr(stream,method)(*args)
        stream._rpc.assert_awaited_once_with({"type":"sub","path":path})
        raw = {"type":"synthetic.update","data":{"marker":"non-secret"}}
        proxy.subscription.queue.put_nowait(raw)
        event = await anext(proxy)
        assert event.path == path and event.channel == channel
        assert event.payload is raw
        assert proxy.lifecycle == auth._lifecycle
        await proxy.close()
        assert stream._rpc.await_args.args == ({"type":"unsub","path":path},)
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_token_generation_change_reauthenticates_before_new_private_subscription():
    auth, transport, stream = connected_account()
    try:
        auth._access = "synthetic-rotated-access"
        auth._generation += 1
        await stream.subscribe_balances()
        calls = [c.args[0] for c in stream._rpc.await_args_list]
        assert calls == [
            {"type":"reauth","auth":{"headers":{"Authorization":"Bearer synthetic-rotated-access"}}},
            {"type":"sub","path":"/balances"},
        ]
        await stream.reauthenticate()
        assert stream._rpc.await_count == 2
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_concurrent_reauthentication_sends_one_frame_per_generation():
    auth, transport, stream = connected_account()
    try:
        auth._generation += 1
        await asyncio.gather(*(stream.reauthenticate() for _ in range(8)))
        assert stream._rpc.await_count == 1
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("state", [AuthState.NEW,AuthState.TWO_FACTOR_REQUIRED,AuthState.EXPIRED])
async def test_incomplete_session_blocks_private_frames(state):
    auth, transport, stream = connected_account()
    try:
        auth.state = state
        with pytest.raises(AuthenticationError):
            await stream.subscribe_orders()
        stream._rpc.assert_not_awaited()
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_old_account_iterator_cannot_deliver_data_after_lifecycle_changes():
    auth, transport, stream = connected_account()
    try:
        proxy = await stream.subscribe_balances()
        proxy.subscription.queue.put_nowait({"data":{"old_account":True}})
        auth._lifecycle += 1
        with pytest.raises(asyncio.CancelledError):
            await anext(proxy)
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_lifecycle_is_checked_again_after_waiting_for_private_event():
    auth, transport, stream = connected_account()
    try:
        proxy = await stream.subscribe_orders()
        consumer = asyncio.create_task(anext(proxy))
        await asyncio.sleep(0)
        auth._lifecycle += 1
        proxy.subscription.queue.put_nowait({"data":{"old_account":True}})
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(consumer,0.5)
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_closing_source_transport_prevents_reopening_private_stream():
    auth, transport, stream = connected_account()
    try:
        await transport.close()
        with pytest.raises((AuthenticationError,RuntimeError)):
            await stream.subscribe_balances()
        stream._rpc.assert_not_awaited()
    finally:
        await stream.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["subscribe_user_trades","subscribe_notifications","subscribe_chat"])
@pytest.mark.parametrize("identity", [0,-1,True,"../123","１２３",None])
async def test_invalid_channel_identifiers_never_send_private_frames(method,identity):
    auth, transport, stream = connected_account()
    try:
        with pytest.raises(ValueError):
            await getattr(stream,method)(identity)
        stream._rpc.assert_not_awaited()
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_chat_and_notification_rpc_paths_use_explicit_payloads_only():
    auth, transport, stream = connected_account()
    try:
        assert await stream.get_chat() == {"ok":True}
        stream._rpc.assert_awaited_with({"type":"request","method":"GET","path":"/api/user/chats"})
        await stream.send_chat_message("synthetic test text")
        stream._rpc.assert_awaited_with({"type":"request","method":"POST","path":"/api/user/chats",
            "payload":{"message":"synthetic test text","attachments":[]}})
        await stream.mark_notification_read({"id":123})
        stream._rpc.assert_awaited_with({"type":"request","method":"POST","path":"/api/notification/message/read","payload":{"id":123}})
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_refresh_during_reauth_repeats_until_current_generation():
    auth, transport, stream = connected_account()
    try:
        auth._generation += 1
        async def reply(frame):
            if stream._rpc.await_count == 1:
                auth._generation += 1
                auth._access = "synthetic-newest-access"
            return {}
        stream._rpc.side_effect = reply
        await stream.reauthenticate()
        assert stream._rpc.await_count == 2
        assert stream._auth_generation == auth.generation
        assert stream._rpc.await_args.args[0]["auth"]["headers"]["Authorization"] == "Bearer synthetic-newest-access"
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_logout_during_reauth_never_marks_socket_current():
    auth, transport, stream = connected_account()
    try:
        old_generation = stream._auth_generation
        auth._generation += 1
        async def reply(frame):
            auth._lifecycle += 1
            return {}
        stream._rpc.side_effect = reply
        with pytest.raises(asyncio.CancelledError):
            await stream.reauthenticate()
        assert stream._auth_generation == old_generation
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_explicit_account_reconnect_returns_only_requested_replacements(monkeypatch):
    auth, transport, stream = connected_account()
    try:
        balances = await stream.subscribe_balances()
        orders = await stream.subscribe_orders()
        async def fake_connect(self):
            self.ws = FakeSocket()
        monkeypatch.setattr(BitTeamMarketStreams, "connect", fake_connect)
        replacements = await stream.reconnect([balances, balances])
        fresh = replacements["/balances"]
        assert list(replacements) == ["/balances"]
        assert fresh is not balances
        assert fresh.subscription is not balances.subscription
        assert "/orders" not in stream._subscriptions
        with pytest.raises(ConnectionError, match="events may be missing"):
            await anext(balances)
        await balances.close()
        assert stream._subscriptions["/balances"] is fresh.subscription
        fresh.subscription.queue.put_nowait({"synthetic": True})
        assert (await anext(fresh)).payload == {"synthetic": True}
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_old_lifecycle_cannot_be_resubscribed_or_reconnected():
    auth, transport, stream = connected_account()
    try:
        old = await stream.subscribe_balances()
        auth._lifecycle += 1
        stream._rpc.reset_mock()
        with pytest.raises(asyncio.CancelledError):
            await old.resubscribe()
        with pytest.raises(asyncio.CancelledError):
            await stream.reconnect([old])
        stream._rpc.assert_not_awaited()
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_new_login_closes_old_socket_before_connect(monkeypatch):
    auth, transport, stream = connected_account()
    try:
        old = await stream.subscribe_balances()
        socket = stream.ws
        auth._lifecycle += 1
        async def fake_connect(self):
            assert socket.closed
            assert not self._subscriptions
            self.ws = FakeSocket()
        monkeypatch.setattr(BitTeamMarketStreams, "connect", fake_connect)
        await stream.connect()
        assert stream._connection_lifecycle == auth._lifecycle
        with pytest.raises(asyncio.CancelledError):
            await anext(old)
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_reconnect_rejects_foreign_refs_before_closing_socket():
    auth, transport, stream = connected_account()
    other_auth, other_transport, other = connected_account()
    try:
        foreign = await other.subscribe_balances()
        socket = stream.ws
        with pytest.raises(ValueError):
            await stream.reconnect([foreign])
        assert not socket.closed
    finally:
        await stream.close()
        await other.close()
        await transport.close()
        await other_transport.close()


@pytest.mark.asyncio
async def test_reconnect_failed_batch_discards_all_new_account_subscriptions(monkeypatch):
    auth, transport, stream = connected_account()
    try:
        balances = await stream.subscribe_balances()
        orders = await stream.subscribe_orders()
        async def fake_connect(self):
            self.ws = FakeSocket()
        monkeypatch.setattr(BitTeamMarketStreams, "connect", fake_connect)
        async def reply(frame):
            if frame.get("path") == "/orders":
                raise ConnectionError("synthetic disconnect")
            return {}
        stream._rpc.side_effect = reply
        with pytest.raises(ConnectionError):
            await stream.reconnect([balances, orders])
        assert not stream._subscriptions
        assert stream.ws.closed
    finally:
        await stream.close()
        await transport.close()


@pytest.mark.asyncio
async def test_disconnect_old_reference_can_explicitly_resubscribe(monkeypatch):
    auth, transport, stream = connected_account()
    try:
        old = await stream.subscribe_orders()
        stream._subscriptions.clear()
        stream.ws.closed = True
        old.subscription.queue.put_nowait(ConnectionError("synthetic disconnect"))
        async def fake_connect(self):
            self.ws = FakeSocket()
        monkeypatch.setattr(BitTeamMarketStreams, "connect", fake_connect)
        fresh = await old.resubscribe()
        assert fresh.lifecycle == old.lifecycle
        assert fresh.subscription is not old.subscription
        assert stream._subscriptions["/orders"] is fresh.subscription
        await old.close()
        assert stream._subscriptions["/orders"] is fresh.subscription
    finally:
        await stream.close()
        await transport.close()
