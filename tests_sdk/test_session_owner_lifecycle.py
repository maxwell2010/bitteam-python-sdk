"""Stale auth references never read/write another owner's jar or cache.

Real BitTeamClient/REST ownership, synthetic tokens, in-memory cache and HTTP.
"""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState


class Cache:
    def __init__(self, label):
        self.data = {"version": 1, "base_url": "https://bit.team/trade/api",
                     "auth_url": "https://auth2.bit.team/v1", "email": None,
                     "access": "synthetic-access-" + label,
                     "refresh": "synthetic-refresh-" + label, "cookies": []}
        self.loads, self.saves, self.deletes = 0, [], 0

    def load(self):
        self.loads += 1
        return deepcopy(self.data)

    def save(self, data):
        self.saves.append(deepcopy(data))
        self.data = deepcopy(data)

    def delete(self):
        self.deletes += 1
        self.data = None


def ready(label):
    auth = SessionAuth(cache=Cache(label))
    auth.state = AuthState.READY
    auth._access, auth._refresh = "synthetic-access-" + label, "synthetic-refresh-" + label
    auth._uid = "synthetic-uid-" + label
    return auth


def session(label):
    jar = aiohttp.CookieJar()
    jar.update_cookies({"owner_cookie": "synthetic-cookie-" + label}, response_url=URL("https://bit.team/"))
    return SimpleNamespace(cookie_jar=jar, close=AsyncMock())


def fixture():
    auth = ready("A")
    client = BitTeamClient(auth=auth)
    client.rest._session = session("A")
    calls = []

    async def send(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith(("/refresh-token", "/login-auth")):
            return {"result": {"access": "synthetic-new-access", "refresh": "synthetic-new-refresh"}}
        if url.endswith("/authorize/check-code"):
            return {"data": True}
        return {"data": {"uid": "synthetic-uid", "is_authorize": True, "email_confirm": True}}

    client.rest._send = send
    return client, auth, calls


def replace(client):
    auth = ready("B")
    client.rest.auth = auth
    auth.bind(client.rest)
    client.rest._session = session("B")
    return auth


def jar_snapshot(client):
    return [(cookie.key, cookie.value) for cookie in client.rest._session.cookie_jar]


@pytest.mark.asyncio
async def test_stale_save_cannot_mix_old_tokens_with_new_owner_cookies():
    client, old, calls = fixture()
    replacement = replace(client)
    expected = jar_snapshot(client)
    try:
        with pytest.raises(asyncio.CancelledError):
            old.save_session()
        assert not old.cache.saves and not replacement.cache.saves
        assert jar_snapshot(client) == expected
        assert not calls
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("validate", [False, True])
async def test_stale_resume_cannot_load_old_cache_into_new_owner_jar(validate):
    client, old, calls = fixture()
    replacement = replace(client)
    expected = jar_snapshot(client)
    try:
        with pytest.raises(asyncio.CancelledError):
            await old.resume(validate=validate)
        assert old.cache.loads == 0
        assert not old.cache.saves and not replacement.cache.saves
        assert jar_snapshot(client) == expected
        assert not calls
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stale_local_clear_only_clears_old_auth_not_new_owner_cookie_jar():
    client, old, calls = fixture()
    replacement = replace(client)
    expected = jar_snapshot(client)
    try:
        await old.clear_session()
        assert old.state == AuthState.NEW and old._access is None
        assert old.cache.deletes == 0
        assert replacement.state == AuthState.READY
        assert replacement.cache.deletes == 0
        assert jar_snapshot(client) == expected
        assert not calls
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["login", "logout", "refresh_logout", "refresh", "open_spot", "totp", "send_code", "confirm_code"])
async def test_stale_auth_cannot_send_or_mutate_new_owner_state(operation):
    client, old, calls = fixture()
    if operation == "open_spot":
        old.state = AuthState.GENERAL_SESSION_READY
    elif operation == "totp":
        old.state = AuthState.TWO_FACTOR_REQUIRED
    elif operation in ("send_code", "confirm_code"):
        old.state = AuthState.DEVICE_CONFIRMATION_REQUIRED
    replacement = replace(client)
    expected = jar_snapshot(client)
    invoke = {
        "login": lambda: old.login("synthetic@example.test", "synthetic-password"),
        "logout": old.logout,
        "refresh_logout": lambda: old.logout(use_refresh=True),
        "refresh": old.refresh,
        "open_spot": old.open_spot_session,
        "totp": lambda: old.submit_totp("012345"),
        "send_code": old.send_device_code,
        "confirm_code": lambda: old.confirm_device("0123"),
    }[operation]
    try:
        with pytest.raises(asyncio.CancelledError):
            await invoke()
        assert not calls
        assert not old.cache.saves and old.cache.deletes == 0
        assert not replacement.cache.saves and replacement.cache.deletes == 0
        assert jar_snapshot(client) == expected
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_stale_token_install_does_not_write_new_owner_jar_or_cache():
    client, old, _ = fixture()
    replacement = replace(client)
    expected = jar_snapshot(client)
    try:
        with pytest.raises(asyncio.CancelledError):
            old._install_tokens({"result": {"access": "synthetic-late-A", "refresh": "synthetic-late-r-A"}})
        assert jar_snapshot(client) == expected
        assert not old.cache.saves and not replacement.cache.saves
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_resume_rechecks_owner_after_session_await_before_cookie_mutation():
    client, auth, _ = fixture()
    captured = client.rest._session
    expected_old = [(cookie.key, cookie.value) for cookie in captured.cookie_jar]

    async def replaced_session():
        replace(client)
        return captured

    client.rest._get_session = replaced_session
    try:
        with pytest.raises(asyncio.CancelledError):
            await auth.resume(validate=False)
        assert [(cookie.key, cookie.value) for cookie in captured.cookie_jar] == expected_old
        assert jar_snapshot(client) == [("owner_cookie", "synthetic-cookie-B")]
        assert not auth.cache.saves
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_auth_response_after_owner_replacement_never_installs_late_tokens():
    client, old, _ = fixture()

    async def send_and_replace(*args, **kwargs):
        replace(client)
        return {"result": {"access": "synthetic-late-A", "refresh": "synthetic-late-r-A"}}

    client.rest._send = send_and_replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await old.refresh()
        assert jar_snapshot(client) == [("owner_cookie", "synthetic-cookie-B")]
        assert not old.cache.saves
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_current_owner_save_and_same_owner_refresh_still_work():
    client, auth, calls = fixture()
    try:
        auth.save_session()
        assert auth.cache.saves[-1]["access"] == "synthetic-access-A"
        assert auth.cache.saves[-1]["cookies"][0]["value"] == "synthetic-cookie-A"
        await auth.refresh()
        assert len(calls) == 1
        assert auth.cache.saves[-1]["access"] == "synthetic-new-access"
        assert auth.state == AuthState.READY
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_fresh_replacement_can_save_only_its_own_tokens_and_cookies():
    client, old, _ = fixture()
    replacement = replace(client)
    try:
        replacement.save_session()
        saved = replacement.cache.saves[-1]
        assert saved["access"] == "synthetic-access-B"
        assert saved["cookies"][0]["value"] == "synthetic-cookie-B"
        assert not old.cache.saves
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_resume_rechecks_owner_after_cache_load_before_loading_a_session():
    client, auth, calls = fixture()
    original_load = auth.cache.load

    def load_and_replace():
        data = original_load()
        replace(client)
        return data

    auth.cache.load = load_and_replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await auth.resume(validate=False)
        assert auth.cache.loads == 1
        assert jar_snapshot(client) == [("owner_cookie", "synthetic-cookie-B")]
        assert not auth.cache.saves and not calls
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_local_clear_draining_old_task_never_clears_replacement_owner_jar():
    client, old, _ = fixture()
    entered, cancelling, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def operation_with_slow_cleanup():
        entered.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelling.set()
            while not release.is_set():
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    pass
            return {}

    pending = asyncio.create_task(old._tracked_operation(operation_with_slow_cleanup()))
    await entered.wait()
    clearing = asyncio.create_task(old.clear_session())
    await cancelling.wait()
    replacement = replace(client)
    expected = jar_snapshot(client)
    try:
        release.set()
        await clearing
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, asyncio.CancelledError)
        assert jar_snapshot(client) == expected
        assert old.state == AuthState.NEW
        assert replacement.state == AuthState.READY
    finally:
        release.set()
        pending.cancel()
        clearing.cancel()
        await asyncio.gather(pending, clearing, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_scheduled_auth_send_does_not_run_after_owner_replacement():
    client, old, calls = fixture()
    pending = asyncio.create_task(old.refresh())
    asyncio.get_running_loop().call_soon(replace, client)
    try:
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert not calls
        assert jar_snapshot(client) == [("owner_cookie", "synthetic-cookie-B")]
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup", ["clear", "clear_session"])
async def test_stale_local_clear_cannot_delete_shared_replacement_cache(cleanup):
    client, old, _ = fixture()
    replacement = replace(client)
    replacement.cache = old.cache
    replacement.save_session()
    expected_cache = deepcopy(replacement.cache.data)
    expected_jar = jar_snapshot(client)
    saves = len(replacement.cache.saves)
    try:
        if cleanup == "clear":
            old.clear()
        else:
            await old.clear_session()
        assert old.state == AuthState.NEW and old._access is None
        assert replacement.state == AuthState.READY
        assert replacement.cache.data == expected_cache
        assert replacement.cache.deletes == 0
        assert len(replacement.cache.saves) == saves
        assert jar_snapshot(client) == expected_jar
    finally:
        await client.close()


def test_unbound_explicit_local_clear_can_still_delete_its_own_cache():
    auth = ready("unbound")
    auth.clear()
    assert auth.cache.deletes == 1
    assert auth.cache.data is None
