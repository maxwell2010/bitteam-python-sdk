"""An A -> B -> A REST owner round trip cannot revive old stream consumers."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import AuthState
from test_account_owner_identity import Socket, connected, ready


def switch_away_and_back(client, original):
    replacement = ready()
    client.rest.auth = replacement
    client.rest.auth = original


@pytest.mark.asyncio
@pytest.mark.parametrize("waiting", [False, True])
async def test_returned_owner_cannot_revive_buffered_or_waiting_old_subscription(waiting):
    client, stream = connected()
    original = client.rest.auth
    subscription = await stream.subscribe_balances()
    old_generation, old_token = original.generation, original._access
    task = None
    try:
        if waiting:
            entered = asyncio.Event()
            original_get = subscription.subscription.queue.get
            async def waiting_get():
                entered.set()
                return await original_get()
            subscription.subscription.queue.get = waiting_get
            task = asyncio.create_task(anext(subscription))
            await entered.wait()
        else:
            subscription.subscription.queue.put_nowait({"synthetic": "old-owner-buffer"})
        switch_away_and_back(client, original)
        if waiting:
            subscription.subscription.queue.put_nowait({"synthetic": "old-owner-delayed-event"})
        with pytest.raises(asyncio.CancelledError):
            await (task if task is not None else anext(subscription))
        assert original.state == AuthState.READY
        assert original._access == old_token and original.generation == old_generation
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_returned_owner_can_open_fresh_subscription_and_request_in_current_epoch():
    client, stream = connected()
    original = client.rest.auth
    old = await stream.subscribe_orders()
    old_lifecycle = old.lifecycle
    # All connection/ACK operations below remain fake; no HTTP or real socket.
    new_socket = Socket(stream)
    stream._session = SimpleNamespace(closed=False, close=AsyncMock(),
                                     ws_connect=AsyncMock(return_value=new_socket))
    async def reader():
        await asyncio.Future()
    stream._reader = reader
    try:
        switch_away_and_back(client, original)
        old.subscription.queue.put_nowait({"synthetic": "old-epoch-event"})
        with pytest.raises(asyncio.CancelledError):
            await anext(old)
        fresh = await stream.subscribe_orders()
        assert fresh.lifecycle != old_lifecycle
        assert fresh.subscription is not old.subscription
        fresh.subscription.queue.put_nowait({"synthetic": "new-epoch-event"})
        assert (await anext(fresh)).payload == {"synthetic": "new-epoch-event"}
        assert await stream.get_chat() == {"synthetic": True}
        assert original.state == AuthState.READY
    finally:
        await client.close()
