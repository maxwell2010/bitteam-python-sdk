"""Explicit caller relogin invalidates old recovery work; all I/O is RAM-only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import AuthState, BitTeamClient, SessionAuth
from bitteam_sdk import AuthenticationError


@pytest.mark.asyncio
@pytest.mark.parametrize("late_error", [False, True])
@pytest.mark.parametrize("queued_operation", ["logout", "refresh"])
async def test_explicit_relogin_preserves_new_session_against_old_recovery(late_error, queued_operation):
    auth = SessionAuth()
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    auth._install_tokens({"result": {"access": "synthetic-old-a", "refresh": "synthetic-old-r"}})
    generation = auth.generation
    entered, cancelled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    calls = []

    async def send(method, url, **kwargs):
        suffix = url.rsplit("/", 1)[-1]
        calls.append(suffix)
        if suffix == "refresh-token":
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()
            if late_error:
                raise AuthenticationError(401)
            return {"result": {"access": "synthetic-stale-a", "refresh": "synthetic-stale-r"}}
        if suffix == "login":
            return {"data": {"uid": "synthetic-new-user", "email_confirm": True, "is_authorize": True}}
        if suffix == "login-auth":
            return {"result": {"access": "synthetic-new-a", "refresh": "synthetic-new-r"}}
        raise AssertionError("Unexpected synthetic dispatch")

    client.rest._send = send
    active = asyncio.create_task(auth.refresh(expected_generation=generation))
    queued = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        queued = asyncio.create_task(
            auth.logout() if queued_operation == "logout"
            else auth.refresh(expected_generation=generation)
        )
        await asyncio.sleep(0)
        result = await client.login("synthetic@example.test", "synthetic-password")
        await asyncio.wait_for(cancelled.wait(), 1)
        assert result.state is AuthState.READY
        release.set()
        outcomes = await asyncio.wait_for(asyncio.gather(active, queued, return_exceptions=True), 1)
        assert all(isinstance(outcome, asyncio.CancelledError) for outcome in outcomes)
        assert auth.state is AuthState.READY
        assert auth.headers() == {"Authorization": "Bearer synthetic-new-a"}
        assert auth._refresh == "synthetic-new-r"
        cookies = client.rest._session.cookie_jar.filter_cookies(URL(client.rest.base_url))
        assert cookies["access"].value == "synthetic-new-a"
        assert cookies["refresh"].value == "synthetic-new-r"
        assert calls == ["refresh-token", "login", "login-auth"]
        assert not auth._pending_requests
    finally:
        release.set()
        await asyncio.gather(*(task for task in (active, queued) if task is not None), return_exceptions=True)
        await client.close()
