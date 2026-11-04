"""Owner A -> B -> A invalidates old work even when I/O ignores cancellation.

Real SDK client/REST coordination; fake HTTP, RAM cookies and synthetic tokens.
"""
import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState


def ready(label):
    auth = SessionAuth()
    auth.state = AuthState.READY
    auth._access, auth._refresh = "synthetic-access-" + label, "synthetic-refresh-" + label
    return auth


class Response:
    status, headers = 200, {}

    def __init__(self, payload, entered=None, release=None, cancelled=None):
        self.payload = payload
        self.entered, self.release, self.cancelled = entered, release, cancelled

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if self.entered is not None:
            self.entered.set()
            while not self.release.is_set():
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    # Model a transport cleanup that still returns a late body.
                    self.cancelled.set()
        return self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.cookie_jar = aiohttp.CookieJar()
        self.close = AsyncMock()
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, str(url), kwargs))
        if str(url).endswith("/refresh-token"):
            return Response({"result": {"access": "synthetic-refreshed-A", "refresh": "synthetic-refreshed-r-A"}})
        return self.response


@pytest.mark.asyncio
@pytest.mark.parametrize("public", [False, True])
async def test_owner_roundtrip_rejects_cancellation_immune_old_response_and_allows_fresh_work(public):
    auth = ready("A")
    client = BitTeamClient(auth=auth)
    rest = client.rest
    rest._limiter.acquire = AsyncMock()
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    original = Session(Response({"ok": True, "result": {"epoch": "old-A"}}, entered, release, cancelled))
    rest._session = original
    task = asyncio.create_task(rest._request("GET", "/pairs" if public else "/address/wallets", public=public))
    await entered.wait()
    try:
        rest.auth = ready("B")
        rest.auth = auth
        await asyncio.sleep(0)
        assert cancelled.is_set(), "Owner replacement must request cancellation of old I/O"
        # Detaching an owner is an operation boundary, not a token/cache reset.
        assert auth.state == AuthState.READY
        assert auth._access == "synthetic-access-A" and auth._refresh == "synthetic-refresh-A"
        fresh = Session(Response({"ok": True, "result": {"epoch": "new-A"}}))
        rest._session = fresh
        assert (await rest._request("GET", "/address/wallets"))["result"] == {"epoch": "new-A"}
        assert (await auth.refresh()).state == AuthState.READY
        assert auth._access == "synthetic-refreshed-A"
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert len(original.calls) == 1
        assert len(fresh.calls) == 2
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_same_owner_refresh_does_not_invalidate_waiting_request_epoch():
    auth = ready("A")
    client = BitTeamClient(auth=auth)
    rest = client.rest
    rest._limiter.acquire = AsyncMock()
    entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    rest._session = Session(Response({"ok": True, "result": {"account": "A"}}, entered, release, cancelled))
    lifecycle = auth._lifecycle
    task = asyncio.create_task(rest._request("GET", "/address/wallets"))
    await entered.wait()
    try:
        await auth.refresh()
        assert auth._lifecycle == lifecycle
        assert auth._access == "synthetic-refreshed-A"
        release.set()
        assert (await task)["result"] == {"account": "A"}
        assert not cancelled.is_set()
    finally:
        release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()
