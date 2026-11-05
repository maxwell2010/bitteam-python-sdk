"""Cancellation and shared retirement cleanup with real REST and fake sessions."""
import asyncio

import pytest

from bitteam_sdk import SessionAuth
from bitteam_sdk.rest import BitTeamRestAPI


class RetiredSession:
    def __init__(self):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.closed = False
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        self.closed = True


def owner_with_retired_session():
    rest = BitTeamRestAPI(auth=SessionAuth())
    retired = RetiredSession()
    rest._session = retired
    rest.auth = SessionAuth()
    assert rest._session is None
    return rest, retired


@pytest.mark.asyncio
async def test_cancelling_get_session_preserves_retired_close_until_owner_close():
    rest, retired = owner_with_retired_session()
    opening = asyncio.create_task(rest._get_session())
    closing = None
    try:
        await retired.entered.wait()
        opening.cancel()
        with pytest.raises(asyncio.CancelledError):
            await opening
        assert not retired.cancelled.is_set(), "Caller cancellation abandoned retired socket cleanup"
        closing = asyncio.create_task(rest.close())
        done, _ = await asyncio.wait({closing}, timeout=0.01)
        assert not done, "Owner close returned while a retired HTTP session was still open"
        retired.release.set()
        await closing
        assert retired.closed and retired.close_calls == 1
    finally:
        retired.release.set()
        opening.cancel()
        await asyncio.gather(opening, return_exceptions=True)
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await rest.close()


@pytest.mark.asyncio
async def test_concurrent_owner_close_waits_for_common_retired_drain():
    rest, retired = owner_with_retired_session()
    opening = asyncio.create_task(rest._get_session())
    closing = None
    try:
        await retired.entered.wait()
        closing = asyncio.create_task(rest.close())
        done, _ = await asyncio.wait({closing}, timeout=0.01)
        assert not done, "Concurrent close must await retirement already started by another caller"
        retired.release.set()
        await closing
        with pytest.raises(RuntimeError, match="closed"):
            await opening
        assert retired.closed and retired.close_calls == 1
    finally:
        retired.release.set()
        await asyncio.gather(opening, return_exceptions=True)
        if closing is not None:
            await asyncio.gather(closing, return_exceptions=True)
        await rest.close()


@pytest.mark.asyncio
async def test_retired_close_failure_cannot_become_later_successful_owner_close():
    rest = BitTeamRestAPI(auth=SessionAuth())
    error = RuntimeError("Synthetic retired session close failure")
    class FailedSession:
        async def close(self):
            raise error
    rest._session = FailedSession()
    rest.auth = SessionAuth()
    with pytest.raises(RuntimeError) as first:
        await rest._get_session()
    assert first.value is error
    with pytest.raises(RuntimeError) as second:
        await rest.close()
    assert second.value is error
