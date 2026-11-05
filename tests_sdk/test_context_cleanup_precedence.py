"""Real context managers with fake close failures, no HTTP/cache involvement."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamClient
from bitteam_sdk.rest import BitTeamRestAPI


def context(kind, failure=None):
    resource = kind()
    transport = resource.rest if isinstance(resource, BitTeamClient) else resource
    session = SimpleNamespace(close=AsyncMock(side_effect=failure), closed=False)
    transport._session = session
    return resource, session


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamClient, BitTeamRestAPI])
@pytest.mark.parametrize('primary', [ValueError('synthetic request failure'), asyncio.CancelledError('synthetic cancel')])
async def test_context_cleanup_preserves_primary_failure(kind, primary):
    cleanup = OSError('synthetic cleanup failure')
    resource, session = context(kind, cleanup)
    with pytest.raises(type(primary)) as caught:
        async with resource:
            raise primary
    assert caught.value is primary
    session.close.assert_awaited_once()
    # A secondary cleanup failure is not converted to later apparent success.
    with pytest.raises(OSError) as closed:
        await resource.close()
    assert closed.value is cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamClient, BitTeamRestAPI])
async def test_context_close_failure_without_primary_is_visible(kind):
    cleanup = OSError('synthetic cleanup failure')
    resource, session = context(kind, cleanup)
    with pytest.raises(OSError) as caught:
        async with resource:
            pass
    assert caught.value is cleanup
    session.close.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', [BitTeamClient, BitTeamRestAPI])
async def test_context_success_closes_normally(kind):
    resource, session = context(kind)
    async with resource:
        pass
    session.close.assert_awaited_once()
