"""Auth replacement isolates late Set-Cookie; real REST, fake HTTP, RAM only."""
import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import AuthState, SessionAuth
from bitteam_sdk.rest import BitTeamRestAPI


def ready():
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-access"
    return auth


class Session:
    def __init__(self):
        self.cookie_jar = aiohttp.CookieJar()
        self.close = AsyncMock()


@pytest.mark.asyncio
async def test_owner_replacement_retires_cookie_jar_and_cancels_old_tracked_request():
    auth = ready()
    rest = BitTeamRestAPI(auth=auth)
    original = Session()
    rest._session = original
    rest._limiter.acquire = AsyncMock()
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class Response:
        status, headers = 200, {}
        async def __aenter__(self):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                # Simulate cleanup that still processes a late cookie header.
                await release.wait()
            original.cookie_jar.update_cookies({"late_A": "synthetic-A"}, response_url=URL(rest.base_url))
            return self
        async def __aexit__(self, *args):
            pass
        async def json(self):
            return {"ok": True}

    original.request = lambda *a, **k: Response()
    task = asyncio.create_task(rest._request("GET", "/address/wallets"))
    await entered.wait()
    replacement = ready()
    try:
        rest.auth = replacement
        replacement.bind(rest)
        assert rest._session is None, "Old HTTP session must not become B's cookie jar"
        fresh = Session()
        fresh.cookie_jar.update_cookies({"account_B": "synthetic-B"}, response_url=URL(rest.base_url))
        rest._session = fresh
        await asyncio.sleep(0)
        assert cancelled.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "late_A" not in fresh.cookie_jar.filter_cookies(URL(rest.base_url))
        assert "account_B" in fresh.cookie_jar.filter_cookies(URL(rest.base_url))
        assert "late_A" in original.cookie_jar.filter_cookies(URL(rest.base_url))
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rest.close()
    original.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_assigning_same_auth_preserves_session_and_does_not_cancel_requests():
    auth = ready()
    rest = BitTeamRestAPI(auth=auth)
    session = Session()
    rest._session = session
    task = asyncio.create_task(asyncio.Event().wait())
    auth._pending_requests.add(task)
    try:
        rest.auth = auth
        assert rest._session is session
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        auth._pending_requests.discard(task)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await rest.close()
