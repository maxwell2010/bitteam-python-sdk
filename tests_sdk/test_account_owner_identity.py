"""Account streams stay bound to their actual client owner; fake WebSockets only."""
import asyncio
import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState
from bitteam_sdk.market_streams import BitTeamMarketStreams


class Socket:
    def __init__(self, stream):
        self.closed = False
        self.stream = stream
        self.sent = []

    async def send_json(self, frame):
        self.sent.append(frame)
        self.stream._pending[frame["id"]].set_result({"payload": {"synthetic": True}})

    async def close(self):
        self.closed = True


def ready():
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-owner-access"
    return auth


def connected():
    client = BitTeamClient(auth=ready())
    stream = client.account_streams
    stream.ws = Socket(stream)
    stream._connection_lifecycle = stream.auth._lifecycle
    stream._auth_generation = stream.auth.generation
    return client, stream


def replace_owner_auth(client, *, clear=False):
    client.rest.auth = ready()
    client.rest.auth.bind(client.rest)
    if clear:
        client.rest.auth.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["hello", "subscribe", "chat", "reauth"])
@pytest.mark.parametrize("clear", [False, True])
async def test_held_private_stream_rejects_replaced_owner_before_private_frames(operation, clear):
    client, stream = connected()
    replace_owner_auth(client, clear=clear)
    try:
        with pytest.raises(asyncio.CancelledError):
            if operation == "hello":
                await stream._hello_payload()
            elif operation == "subscribe":
                await stream.subscribe_balances()
            elif operation == "chat":
                await stream.get_chat()
            else:
                await stream.reauthenticate()
        assert stream.ws.sent == []
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", [False, True])
async def test_buffered_or_awaiting_private_iterator_cannot_deliver_previous_owner(waiting):
    client, stream = connected()
    subscription = await stream.subscribe_balances()
    task = None
    try:
        if waiting:
            task = asyncio.create_task(anext(subscription))
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        replace_owner_auth(client)
        subscription.subscription.queue.put_nowait({"synthetic": "old-account-event"})
        with pytest.raises(asyncio.CancelledError):
            await (task if task is not None else anext(subscription))
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_private_rpc_rechecks_owner_inside_scheduled_exchange(monkeypatch):
    client, stream = connected()
    try:
        # Force the dispatch scheduling gap also on Python versions where
        # wait_for may begin awaiting its coroutine without creating a task.
        entered, release = asyncio.Event(), asyncio.Event()
        original_wait_for = asyncio.wait_for
        async def deferred_wait_for(operation, timeout):
            entered.set()
            await release.wait()
            return await original_wait_for(operation, timeout)
        monkeypatch.setattr("bitteam_sdk.websocket.asyncio.wait_for", deferred_wait_for)
        task = asyncio.create_task(stream._rpc({"type": "request", "path": "/api/user/chats"}))
        await entered.wait()
        replace_owner_auth(client)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stream.ws.sent == []
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_private_rpc_does_not_return_reply_after_owner_replacement():
    client, stream = connected()
    original_send = stream.ws.send_json
    async def reply_and_replace(frame):
        await original_send(frame)
        replace_owner_auth(client)
    stream.ws.send_json = reply_and_replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await stream.get_chat()
        assert len(stream.ws.sent) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_same_owner_refresh_and_public_stream_remain_usable():
    client, stream = connected()
    public = BitTeamMarketStreams()
    public.ws = Socket(public)
    try:
        stream.auth._generation += 1
        assert await stream.get_chat() == {"synthetic": True}
        assert [row["type"] for row in stream.ws.sent] == ["reauth", "request"]
        replace_owner_auth(client)
        assert (await public.subscribe_tickers()).path == "/prices"
    finally:
        await client.close()
        await public.close()


@pytest.mark.asyncio
async def test_missing_auth_attribute_on_real_rest_owner_fails_closed():
    client, stream = connected()
    owner_auth = client.rest.auth
    del client.rest.auth
    try:
        with pytest.raises(asyncio.CancelledError):
            await stream._hello_payload()
        assert stream.ws.sent == []
    finally:
        client.rest.auth = owner_auth
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("different_auth", [False, True])
async def test_legacy_duck_typed_owner_without_auth_remains_supported(different_auth):
    from types import SimpleNamespace
    from bitteam_sdk.account_streams import BitTeamAccountStreams
    auth = ready()
    transport = SimpleNamespace(base_url="https://bit.team/trade/api", _closed=False)
    if different_auth:
        transport.auth = ready()
    auth.bind(transport)
    stream = BitTeamAccountStreams(auth)
    try:
        if different_auth:
            with pytest.raises(asyncio.CancelledError):
                await stream._hello_payload()
        else:
            hello = await stream._hello_payload()
            assert hello["auth"]["headers"] == {"Authorization": "Bearer synthetic-owner-access"}
    finally:
        await stream.close()
