"""Held P2P resources with a real client/REST owner and fake HTTP only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState
from bitteam_sdk.p2p_api import BitTeamP2PAPI
from test_p2p_api import Response, Session


def ready_auth(label):
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-spot-" + label
    return auth


def owner_fixture():
    auth = ready_auth("A")
    client = BitTeamClient(auth=auth)
    jar = aiohttp.CookieJar()
    jar.update_cookies({"access_token": "synthetic-general-A"}, response_url=URL(BitTeamP2PAPI.BASE_URL))
    client.rest._session = SimpleNamespace(cookie_jar=jar, close=AsyncMock())
    held = client.p2p
    held._session = Session(Response())
    held._limiter.acquire = AsyncMock()
    return client, held, auth


def replace_owner(client):
    replacement = ready_auth("B")
    replacement.bind(client.rest)
    client.rest.auth = replacement
    # Real owner replacement intentionally retires A's HTTP session/cookie jar.
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    client.rest._session.cookie_jar.update_cookies(
        {"access_token": "synthetic-general-B"}, response_url=URL(BitTeamP2PAPI.BASE_URL))


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,kwargs", [
    ("get_accounts", {}),
    ("change_status_all", {}),
    ("create_operation", {"data": {"explicit": "synthetic-body"}})])
@pytest.mark.parametrize("boundary", ["before_call", "before_call_cleared_B", "queued", "scheduled"])
async def test_held_p2p_cannot_dispatch_after_rest_owner_auth_replacement(operation, kwargs, boundary):
    client, held, auth = owner_fixture()
    lifecycle = auth._lifecycle
    try:
        if boundary in ("before_call", "before_call_cleared_B"):
            replace_owner(client)
            if boundary == "before_call_cleared_B":
                client.auth.clear()
        elif boundary == "queued":
            async def replace_while_queued():
                replace_owner(client)
            held._limiter.acquire = replace_while_queued
        if boundary == "scheduled":
            task = asyncio.create_task(getattr(held, operation)(**kwargs))
            asyncio.get_running_loop().call_soon(replace_owner, client)
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(asyncio.CancelledError):
                await getattr(held, operation)(**kwargs)
        assert auth._lifecycle == lifecycle + 1
        assert held.auth is auth
        assert client.auth is not auth
        assert not held._session.calls
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [False, True])
async def test_held_p2p_response_does_not_survive_rest_owner_auth_replacement(malformed):
    client, held, auth = owner_fixture()

    async def replace_during_response():
        replace_owner(client)
        if malformed:
            raise ValueError("synthetic-proxy-body")
        return {"status": True, "data": {"account": "synthetic-A"}}

    held._session.response.json = replace_during_response
    try:
        with pytest.raises(asyncio.CancelledError):
            await held.get_active_operations()
        assert held.auth is auth
        assert len(held._session.calls) == 1
        assert held._session.calls[0][2]["headers"]["Authorization"] == "Bearer synthetic-general-A"
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_rest_owner_missing_auth_cannot_fall_back_to_held_resource_auth():
    client, held, auth = owner_fixture()
    del client.rest.auth
    try:
        with pytest.raises(asyncio.CancelledError):
            await held.change_status_all()
        assert not held._session.calls
    finally:
        client.rest.auth = auth
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("clear_replacement", [False, True])
async def test_held_public_p2p_remains_anonymous_after_owner_auth_replacement(clear_replacement):
    client, held, _ = owner_fixture()
    replace_owner(client)
    if clear_replacement:
        client.auth.clear()
    try:
        await held.get_subjects(params={"subject_id": 1})
        assert len(held._session.calls) == 1
        assert "Authorization" not in held._session.calls[0][2]["headers"]
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_held_p2p_same_owner_refresh_can_use_rotated_general_cookie():
    client, held, auth = owner_fixture()

    async def refresh_same_owner():
        auth._generation += 1
        client.rest._session.cookie_jar.update_cookies(
            {"access_token": "synthetic-general-A-rotated"}, response_url=URL(BitTeamP2PAPI.BASE_URL))

    held._limiter.acquire = refresh_same_owner
    try:
        await held.change_status_all()
        assert held.auth is client.auth is auth
        assert len(held._session.calls) == 1
        assert held._session.calls[0][2]["headers"]["Authorization"] == "Bearer synthetic-general-A-rotated"
    finally:
        await client.close()
