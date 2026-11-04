"""Real REST request/limiter orchestration over fake HTTP transports only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import SessionAuth, AuthState, ApiKeyAuth, BitTeamAPIError
from bitteam_sdk.rest import BitTeamRestAPI


class Response:
    status = 200
    headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return {"ok": True, "result": {"account": "synthetic-A"}}


def ready_auth():
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-A-token"
    return auth


@pytest.mark.asyncio
@pytest.mark.parametrize("method,endpoint", [("POST", "/withdraw/create"), ("GET", "/address/wallets")])
@pytest.mark.parametrize("replacement", ["session", "keys"])
async def test_queued_rest_never_sends_old_headers_after_auth_identity_replacement(method, endpoint, replacement):
    auth = ready_auth()
    rest = BitTeamRestAPI(auth=auth)
    calls = []
    session = SimpleNamespace(request=lambda *args, **kwargs: calls.append(kwargs) or Response())
    rest._get_session = AsyncMock(return_value=session)

    async def replace():
        rest.auth = ready_auth() if replacement == "session" else ApiKeyAuth("synthetic-key", "synthetic-secret")
        if replacement == "session":
            assert rest.auth._lifecycle == auth._lifecycle
            rest.auth.bind(rest)

    rest._limiter.acquire = replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await rest._request(method, endpoint)
        assert calls == []
    finally:
        await rest.close()


@pytest.mark.asyncio
async def test_late_rest_json_does_not_return_old_account_data_after_auth_replacement():
    rest = BitTeamRestAPI(auth=ready_auth())
    response = Response()

    async def replace():
        rest.auth = ready_auth()
        rest.auth.bind(rest)
        return {"ok": True, "result": {"account": "synthetic-A"}}

    response.json = replace
    rest._get_session = AsyncMock(return_value=SimpleNamespace(request=lambda *a, **k: response))
    rest._limiter.acquire = AsyncMock()
    try:
        with pytest.raises(asyncio.CancelledError):
            await rest._request("GET", "/address/wallets")
    finally:
        await rest.close()


@pytest.mark.asyncio
async def test_rest_same_lifecycle_token_refresh_remains_usable():
    rest = BitTeamRestAPI(auth=ready_auth())
    rest._get_session = AsyncMock(return_value=SimpleNamespace(request=lambda *a, **k: Response()))

    async def refresh():
        rest.auth._generation += 1

    rest._limiter.acquire = refresh
    try:
        assert (await rest._request("GET", "/address/wallets"))["ok"] is True
    finally:
        await rest.close()


@pytest.mark.asyncio
async def test_auth_replacement_before_scheduled_rest_dispatch_prevents_send():
    rest = BitTeamRestAPI(auth=ready_auth())
    rest._send = AsyncMock(return_value={"ok": True})
    def replace():
        rest.auth = ready_auth()
        rest.auth.bind(rest)
    task = asyncio.create_task(rest._request("POST", "/withdraw/create"))
    asyncio.get_running_loop().call_soon(replace)
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        rest._send.assert_not_awaited()
    finally:
        await rest.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["retry", "refresh"])
async def test_rest_retry_or_refresh_never_replays_after_auth_identity_change(boundary, monkeypatch):
    auth = ready_auth()
    rest = BitTeamRestAPI(auth=auth)
    rest._send = AsyncMock(side_effect=BitTeamAPIError(
        503 if boundary == "retry" else 401, None if boundary == "retry" else 401000))
    async def replace(*args, **kwargs):
        rest.auth = ready_auth()
        rest.auth.bind(rest)
    if boundary == "retry":
        monkeypatch.setattr("bitteam_sdk.rest.asyncio.sleep", replace)
    else:
        auth.refresh = replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await rest._request("GET", "/address/wallets")
        assert rest._send.await_count == 1
    finally:
        await rest.close()
