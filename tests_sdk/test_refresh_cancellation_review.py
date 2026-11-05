"""Controlled RAM transport cancellation; no requests or session cache."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk import AuthState, BitTeamClient, SessionAuth


@pytest.mark.asyncio
@pytest.mark.parametrize("repeat_cancel", [False, True])
async def test_refresh_caller_cancel_survives_transport_suppression(repeat_cancel):
    auth = SessionAuth()
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    auth.state = AuthState.READY
    auth._access, auth._refresh = "synthetic-old-a", "synthetic-old-r"
    entered, suppressed, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def send(*args, **kwargs):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            suppressed.set()
            await release.wait()
        return {"result": {"access": "synthetic-new-a", "refresh": "synthetic-new-r"}}

    client.rest._send = send
    task = asyncio.create_task(auth.refresh())
    try:
        await entered.wait()
        task.cancel()
        await suppressed.wait()
        if repeat_cancel:
            task.cancel()
            await asyncio.sleep(0)
        assert auth._pending_requests
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not auth._pending_requests
        assert auth._access == "synthetic-old-a"
        assert auth._refresh == "synthetic-old-r"
        assert auth.state is AuthState.READY
        assert not client.rest._session.cookie_jar
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_cancelled_refresh_does_not_cancel_independent_queued_recovery():
    auth = SessionAuth()
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    auth.state = AuthState.READY
    auth._access, auth._refresh = "synthetic-old-a", "synthetic-old-r"
    entered, suppressed, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def send(*args, **kwargs):
        calls.append(kwargs["headers"]["Authorization"])
        if len(calls) == 1:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                suppressed.set()
                await release.wait()
            return {"result": {"access": "synthetic-cancelled-a", "refresh": "synthetic-cancelled-r"}}
        return {"result": {"access": "synthetic-sibling-a", "refresh": "synthetic-sibling-r"}}

    client.rest._send = send
    active = asyncio.create_task(auth.refresh(expected_generation=0))
    await entered.wait()
    sibling = asyncio.create_task(auth.refresh(expected_generation=0))
    cancelled_waiter = asyncio.create_task(auth.refresh(expected_generation=0))
    try:
        await asyncio.sleep(0)
        cancelled_waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_waiter
        active.cancel()
        await suppressed.wait()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await active
        assert (await sibling).state is AuthState.READY
        assert calls == ["Bearer synthetic-old-r", "Bearer synthetic-old-r"]
        assert auth._access == "synthetic-sibling-a"
        assert auth.generation == 1
        assert not auth._pending_requests
    finally:
        release.set()
        await asyncio.gather(active, sibling, cancelled_waiter, return_exceptions=True)
        await client.close()
