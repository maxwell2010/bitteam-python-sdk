"""Archive shutdown uses fake sessions only, without HTTP or cache access."""
import asyncio

import pytest

from bitteam_sdk.archive import BitTeamArchive


class BlockingSession:
    def __init__(self, *, failure=None):
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.closed = False
        self.calls = 0
        self.failure = failure

    async def close(self):
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        if self.failure:
            raise self.failure
        self.closed = True


@pytest.mark.asyncio
async def test_cancelled_archive_close_keeps_cleanup_awaitable():
    archive = BitTeamArchive(None)
    session = archive._session = BlockingSession()
    first = asyncio.create_task(archive.close())
    await session.entered.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    second = asyncio.create_task(archive.close())
    await asyncio.sleep(0)
    assert not second.done()
    session.release.set()
    await second
    assert session.closed
    assert session.calls == 1
    await archive.close()
    assert session.calls == 1


@pytest.mark.asyncio
async def test_concurrent_archive_close_waits_for_one_cleanup():
    archive = BitTeamArchive(None)
    session = archive._session = BlockingSession()
    first = asyncio.create_task(archive.close())
    await session.entered.wait()
    second = asyncio.create_task(archive.close())
    await asyncio.sleep(0)
    assert not second.done()
    session.release.set()
    await asyncio.gather(first, second)
    assert session.closed
    assert session.calls == 1


@pytest.mark.asyncio
async def test_failed_archive_close_remains_observable():
    archive = BitTeamArchive(None)
    session = archive._session = BlockingSession(failure=OSError("synthetic close failure"))
    session.release.set()
    for _ in range(2):
        with pytest.raises(OSError, match="synthetic close failure"):
            await archive.close()
    assert not session.closed
    assert session.calls == 1
    with pytest.raises(RuntimeError, match="closed"):
        await archive.get_trades()
