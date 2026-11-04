"""Archive lifecycle regressions use synthetic credentials and responses only."""
import asyncio

import pytest

from test_p2p_api import auth_with_cookie
from test_site_transport_review import fake_archive


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["logout", "owner_close", "archive_close"])
async def test_private_archive_does_not_return_response_after_invalidation(change):
    auth = auth_with_cookie()
    client = fake_archive(auth=auth)

    async def invalidated_response():
        if change == "logout":
            auth._lifecycle += 1
        elif change == "owner_close":
            auth._transport._closed = True
        else:
            await client.close()
        return {"result": {"orders": []}}

    client._session.response.json = invalidated_response
    expected = asyncio.CancelledError if change == "logout" else RuntimeError
    with pytest.raises(expected):
        await client.get_user_orders()


@pytest.mark.asyncio
async def test_private_archive_rechecks_lifecycle_before_sending_captured_token():
    auth = auth_with_cookie()
    client = fake_archive(auth=auth)
    session = client._session

    async def invalidated_session():
        auth._lifecycle += 1
        return session

    client._get_session = invalidated_session
    with pytest.raises(asyncio.CancelledError):
        await client.get_user_trades()
    assert session.calls == []


@pytest.mark.asyncio
async def test_archive_auth_replacement_cannot_validate_old_account_response():
    auth = auth_with_cookie()
    client = fake_archive(auth=auth)

    async def replace_auth():
        client.auth = auth_with_cookie()
        return {"result": {"orders": []}}

    client._session.response.json = replace_auth
    with pytest.raises(asyncio.CancelledError):
        await client.get_user_orders()


@pytest.mark.asyncio
async def test_archive_refresh_in_same_session_preserves_response():
    auth = auth_with_cookie()
    client = fake_archive(auth=auth)
    payload = {"result": {"orders": []}}

    async def refreshed_response():
        auth._generation += 1
        return payload

    client._session.response.json = refreshed_response
    assert await client.get_user_orders() is payload


@pytest.mark.asyncio
async def test_public_archive_close_during_response_does_not_return_data():
    client = fake_archive()

    async def closed_response():
        await client.close()
        return []

    client._session.response.json = closed_response
    with pytest.raises(RuntimeError, match="closed"):
        await client.get_trades()
