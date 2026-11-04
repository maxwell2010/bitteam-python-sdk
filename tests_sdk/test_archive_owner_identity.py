"""Held archive references with a real owner and synthetic response transport."""
import asyncio

import pytest

from bitteam_sdk import AuthState, BitTeamClient, SessionAuth
from test_site_transport_review import Response, Session


def ready_auth(label):
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-" + label
    return auth


def replace_owner(client):
    replacement = ready_auth("B")
    replacement.bind(client.rest)
    client.rest.auth = replacement
    return replacement


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["get_user_orders", "get_user_trades"])
@pytest.mark.parametrize("clear_replacement", [False, True])
async def test_held_archive_rejects_replaced_real_owner_before_any_await(method, clear_replacement):
    original = ready_auth("A")
    client = BitTeamClient(auth=original)
    archive = client.archive
    session = Session(Response({"result": []}))
    archive._session = session
    before = original._lifecycle
    replacement = replace_owner(client)
    if clear_replacement:
        replacement.clear()
    entered = False
    async def session_factory():
        nonlocal entered
        entered = True
        return session
    archive._get_session = session_factory
    try:
        with pytest.raises(asyncio.CancelledError):
            await getattr(archive, method)()
        assert not entered and not session.calls
        assert original._lifecycle == before + 1 and original.state == AuthState.READY
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["session", "json", "invalid_json"])
@pytest.mark.parametrize("method", ["get_user_orders", "get_user_trades"])
async def test_archive_rechecks_real_owner_at_dispatch_and_response(stage, method):
    client = BitTeamClient(auth=ready_auth("A"))
    archive = client.archive
    session = Session(Response({"result": []}))
    archive._session = session
    if stage == "session":
        async def session_factory():
            replace_owner(client)
            return session
        archive._get_session = session_factory
    else:
        async def response_json():
            replace_owner(client)
            if stage == "invalid_json":
                raise ValueError("synthetic HTML")
            return {"result": []}
        session.response.json = response_json
    try:
        with pytest.raises(asyncio.CancelledError):
            await getattr(archive, method)()
        assert len(session.calls) == (0 if stage == "session" else 1)
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_held_archive_allows_same_owner_refresh():
    original = ready_auth("A")
    client = BitTeamClient(auth=original)
    archive = client.archive
    payload = {"result": []}
    archive._session = Session(Response(payload))
    async def response_json():
        original._generation += 1
        original._access = "synthetic-refreshed-A"
        return payload
    archive._session.response.json = response_json
    try:
        assert await archive.get_user_orders() is payload
        assert len(archive._session.calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_archive_ignores_owner_replacement_and_has_no_credentials():
    client = BitTeamClient(auth=ready_auth("A"))
    archive = client.archive
    payload = []
    archive._session = Session(Response(payload))
    replace_owner(client).clear()
    try:
        assert await archive.get_trades() is payload
        assert archive._session.calls[0][2]["headers"] == {}
    finally:
        await client.close()
