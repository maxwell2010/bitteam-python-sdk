"""General API-v2 auth boundaries, using only synthetic cookies and responses."""
import asyncio
from unittest.mock import AsyncMock
from http.cookies import SimpleCookie

import pytest
from yarl import URL

from bitteam_sdk import AuthenticationError, AuthState
from bitteam_sdk.p2p_api import BitTeamP2PAPI
from test_p2p_api import auth_with_cookie, client_with, Response


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["lifecycle", "replacement"])
@pytest.mark.parametrize("operation,kwargs", [("get_active_operations", {}),
    ("change_status_all", {}),
    ("accept_operation", {"params": {"link": "synthetic-operation"}}),
    ("create_operation", {"data": {"explicit": "synthetic-body"}})])
async def test_queued_private_request_cannot_cross_accounts(boundary, operation, kwargs):
    auth = auth_with_cookie()
    client = client_with(auth)

    async def change_account():
        if boundary == "lifecycle":
            # Model completion of logout/login as a fresh auth lifecycle.
            auth.clear()
            auth.state = AuthState.READY
            auth._access = "synthetic-spot-account-B"
        else:
            client.auth = auth_with_cookie()
        client.auth._transport._session.cookie_jar.update_cookies(
            {"access_token": "synthetic-general-account-B"}, response_url=URL(BitTeamP2PAPI.BASE_URL))

    client._limiter.acquire = change_account
    with pytest.raises(asyncio.CancelledError):
        await getattr(client, operation)(**kwargs)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["lifecycle", "replacement", "client_close", "owner_close"])
@pytest.mark.parametrize("operation", ["get_active_operations", "change_status_all"])
async def test_private_response_cannot_survive_invalidation(boundary, operation):
    auth = auth_with_cookie()
    client = client_with(auth)

    async def changed_response():
        if boundary == "lifecycle":
            auth._lifecycle += 1
        elif boundary == "replacement":
            client.auth = auth_with_cookie()
        elif boundary == "client_close":
            await client.close()
        else:
            auth._transport._closed = True
        return {"status": True, "data": {}}

    client._session.response.json = changed_response
    expected = asyncio.CancelledError if boundary in ("lifecycle", "replacement") else (RuntimeError, AuthenticationError)
    with pytest.raises(expected):
        await getattr(client, operation)()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"status": False}, ValueError("synthetic-private-body")])
async def test_http401_blocks_rejected_general_token_without_spot_refresh(payload):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response(payload, 401))
    # This GET mutates server state. It must never be automatically replayed.
    with pytest.raises(AuthenticationError):
        await client.accept_operation(params={"link": "synthetic-operation"})
    assert len(client._session.calls) == 1
    with pytest.raises(AuthenticationError):
        await client.accept_operation(params={"link": "synthetic-operation"})
    assert len(client._session.calls) == 1
    auth.refresh.assert_not_awaited()
    assert auth.state == AuthState.READY
    assert auth.headers() == {"Authorization": "Bearer synthetic-spot-access-never-use"}


@pytest.mark.asyncio
async def test_new_general_token_can_be_used_after_rejection():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    auth._transport._session.cookie_jar.update_cookies(
        {"access_token": "synthetic-rotated-general"}, response_url=URL(BitTeamP2PAPI.BASE_URL))
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2
    assert client._session.calls[-1][2]["headers"]["Authorization"] == "Bearer synthetic-rotated-general"


@pytest.mark.asyncio
async def test_late_http401_does_not_block_rotated_general_cookie():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))

    async def rotate_before_response():
        auth._transport._session.cookie_jar.update_cookies(
            {"access_token": "synthetic-rotated-general"}, response_url=URL(BitTeamP2PAPI.BASE_URL))
        return {}

    client._session.response.json = rotate_before_response
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2


@pytest.mark.asyncio
async def test_old_account_http401_cannot_poison_new_session():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))

    async def new_session_before_response():
        auth._lifecycle += 1
        return {}

    client._session.response.json = new_session_before_response
    with pytest.raises(asyncio.CancelledError):
        await client.get_active_operations()
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2


@pytest.mark.asyncio
async def test_http403_does_not_infer_general_token_expiration():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 403))
    from bitteam_sdk import BitTeamAPIError
    with pytest.raises(BitTeamAPIError):
        await client.get_active_operations()
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2


@pytest.mark.asyncio
async def test_expired_general_cookie_fails_locally_without_refresh_or_request():
    auth = auth_with_cookie(general=False)
    auth.refresh = AsyncMock()
    cookie = SimpleCookie()
    cookie["access_token"] = "synthetic-expired-general"
    cookie["access_token"]["max-age"] = "-1"
    auth._transport._session.cookie_jar.update_cookies(cookie, response_url=URL(BitTeamP2PAPI.BASE_URL))
    client = client_with(auth)
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    assert not client._session.calls
    auth.refresh.assert_not_awaited()
    assert auth.state == AuthState.READY


@pytest.mark.asyncio
async def test_expired_general_cookie_while_queued_does_not_send():
    auth = auth_with_cookie()
    client = client_with(auth)

    async def expire_cookie():
        auth._transport._session.cookie_jar.clear()

    client._limiter.acquire = expire_cookie
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    assert not client._session.calls


@pytest.mark.asyncio
async def test_rejection_is_shared_between_p2p_facades_bound_to_same_auth():
    auth = auth_with_cookie()
    first = client_with(auth, Response({}, 401))
    second = client_with(auth)
    with pytest.raises(AuthenticationError):
        await first.get_active_operations()
    with pytest.raises(AuthenticationError):
        await second.get_active_operations()
    assert not second._session.calls


@pytest.mark.asyncio
async def test_local_session_clear_removes_rejections_from_previous_lifecycle():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    auth.clear()
    auth.state = AuthState.GENERAL_SESSION_READY
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2


@pytest.mark.asyncio
async def test_public_http401_does_not_reject_bound_general_token():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))
    from bitteam_sdk import BitTeamAPIError
    with pytest.raises(BitTeamAPIError):
        await client.get_subjects(params={"subject_id": 1})
    client._session.response = Response()
    await client.get_active_operations()
    assert len(client._session.calls) == 2


@pytest.mark.asyncio
async def test_rejection_memory_is_bounded_and_contains_no_raw_tokens():
    auth = auth_with_cookie()
    client = client_with(auth, Response({}, 401))
    for index in range(70):
        auth._transport._session.cookie_jar.update_cookies(
            {"access_token": "synthetic-rejected-" + str(index)}, response_url=URL(BitTeamP2PAPI.BASE_URL))
        with pytest.raises(AuthenticationError):
            await client.get_active_operations()
    assert len(auth._rejected_general_tokens) <= 65
    assert "synthetic-rejected" not in repr(auth._rejected_general_tokens)
    assert len(client._session.calls) == 65


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [409, 401, None, "200", True])
async def test_auth_user_error_code_cannot_be_accepted_as_account_snapshot(code):
    from bitteam_sdk import BitTeamAPIError
    client = client_with(auth_with_cookie(), Response({"account": [], "code": code}))
    with pytest.raises(BitTeamAPIError):
        await client.get_accounts()
    assert len(client._session.calls) == 1


@pytest.mark.asyncio
async def test_logout_cancels_inflight_general_response_without_replay():
    auth = auth_with_cookie()
    client = client_with(auth)
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def blocked_response():
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    client._session.response.json = blocked_response
    task = asyncio.create_task(client.create_operation(data={"explicit": "synthetic-body"}))
    await entered.wait()
    try:
        auth.clear()
        done, _ = await asyncio.wait({task}, timeout=0.3)
        assert task in done
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        assert not auth._pending_requests
        assert len(client._session.calls) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,kwargs", [("accept_operation", {"params": {"link": "synthetic-operation"}}),
    ("create_operation", {"data": {"explicit": "synthetic-body"}})])
async def test_queued_mutation_owner_close_prevents_dispatch(operation, kwargs):
    auth = auth_with_cookie()
    client = client_with(auth)

    async def close_owner():
        auth._transport._closed = True

    client._limiter.acquire = close_owner
    with pytest.raises(AuthenticationError):
        await getattr(client, operation)(**kwargs)
    assert not client._session.calls


@pytest.mark.asyncio
async def test_same_account_refresh_while_queued_is_allowed():
    auth = auth_with_cookie()
    client = client_with(auth)

    async def refreshed():
        auth._generation += 1
        auth._transport._session.cookie_jar.update_cookies(
            {"access_token": "synthetic-rotated-general"}, response_url=URL(BitTeamP2PAPI.BASE_URL))

    client._limiter.acquire = refreshed
    await client.get_active_operations()
    assert len(client._session.calls) == 1
    assert client._session.calls[0][2]["headers"]["Authorization"] == "Bearer synthetic-rotated-general"


@pytest.mark.asyncio
async def test_auth_replacement_before_scheduled_send_prevents_dispatch():
    client = client_with(auth_with_cookie())
    replacement = auth_with_cookie()
    task = asyncio.create_task(client.create_operation(data={"explicit": "synthetic-body"}))
    asyncio.get_running_loop().call_soon(setattr, client, "auth", replacement)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not client._session.calls
