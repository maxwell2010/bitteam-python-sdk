"""Independent auth lifecycle regressions. Synthetic sessions, no network or user cache."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import BitTeamClient, SessionAuth, AuthState, AuthenticationError, BitTeamAPIError


class MemoryCache:
    def __init__(self, data=None):
        self.data = deepcopy(data)
    def load(self):
        return deepcopy(self.data)
    def save(self, data):
        self.data = deepcopy(data)
    def delete(self):
        self.data = None


def snapshot():
    return {'version': 1, 'base_url': 'https://bit.team/trade/api',
            'auth_url': 'https://auth2.bit.team/v1', 'email': None,
            'access': 'synthetic-access', 'refresh': 'synthetic-refresh', 'cookies': []}


def local_client(cache):
    client = BitTeamClient(auth=SessionAuth(cache=cache))
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize('operation,cleanup', [('login', 'logout'), ('totp', 'clear'), ('device', 'clear')])
async def test_cleanup_prevents_pending_auth_response_from_reopening_session(operation, cleanup):
    cache = MemoryCache()
    client = local_client(cache)
    entered, release = asyncio.Event(), asyncio.Event()
    exchanges = []
    endpoint = {'login': '/clients/web/login', 'totp': '/clients/web/login-2fa',
                'device': '/authorize/check-code'}[operation]
    async def send(method, url, **kwargs):
        if url.endswith(endpoint):
            entered.set()
            await release.wait()
            # A completed HTTP auth response can also modify the cookie jar.
            client.rest._session.cookie_jar.update_cookies({'response_cookie': 'synthetic'},
                                                          response_url=URL('https://bit.team/'))
            return {'data': True} if operation == 'device' else {'data': {
                'uid': 'synthetic-user', 'email_confirm': True, 'is_authorize': True}}
        if url.endswith('/login-auth'):
            exchanges.append(True)
            return {'result': {'access': 'synthetic-new-access', 'refresh': 'synthetic-new-refresh'}}
        if url.endswith('/logout'):
            return {'ok': True}
        raise AssertionError('Unexpected operation in local regression test')
    client.rest._send = send
    if operation == 'totp':
        client.auth.state = AuthState.TWO_FACTOR_REQUIRED
        client.auth._uid = 'synthetic-user'
    if operation == 'device':
        client.auth.state = AuthState.DEVICE_CONFIRMATION_REQUIRED
        client.auth._uid = 'synthetic-user'
    call = {'login': lambda: client.login('synthetic@example.test', 'synthetic-password'),
            'totp': lambda: client.submit_totp('012345'),
            'device': lambda: client.confirm_device('0123')}[operation]
    pending = asyncio.create_task(call())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(client.logout() if cleanup == 'logout' else client.clear_session(), 1)
        release.set()
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, (AuthenticationError, asyncio.CancelledError))
        assert client.auth.state == AuthState.NEW
        assert not exchanges
        assert cache.load() is None
        assert len(client.rest._session.cookie_jar) == 0
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_clear_while_resume_waits_for_session_does_not_restore_old_cache():
    cache = MemoryCache(snapshot())
    client = local_client(cache)
    entered, release = asyncio.Event(), asyncio.Event()
    session = client.rest._session
    async def delayed_session():
        entered.set()
        await release.wait()
        return session
    client.rest._get_session = delayed_session
    pending = asyncio.create_task(client.resume_session(validate=False))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(client.clear_session(), 1)
        release.set()
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, (AuthenticationError, asyncio.CancelledError))
        assert client.auth.state == AuthState.NEW
        assert cache.load() is None
        assert len(session.cookie_jar) == 0
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_http200_invalid_refresh_deletes_cache_and_disables_authentication():
    cache = MemoryCache()
    client = local_client(cache)
    client.auth._install_tokens({'result': {'access': 'synthetic-access', 'refresh': 'synthetic-refresh'}})
    async def rejected(*args, **kwargs):
        raise BitTeamAPIError(200, 401010)
    client.rest._send = rejected
    try:
        with pytest.raises(BitTeamAPIError):
            await client.refresh()
        assert cache.load() is None
        assert client.auth.state == AuthState.EXPIRED
        assert len(client.rest._session.cookie_jar) == 0
        with pytest.raises(AuthenticationError):
            client.auth.headers()
    finally:
        await client.close()
    assert cache.load() is None


@pytest.mark.asyncio
async def test_http200_invalid_refresh_during_resume_requires_fresh_login():
    cache = MemoryCache(snapshot())
    client = local_client(cache)
    async def rejected(method, url, **kwargs):
        raise BitTeamAPIError(200, 401010 if url.endswith('/refresh-token') else 401000)
    client.rest._send = rejected
    try:
        assert await client.resume_session() is False
        assert cache.load() is None
        assert client.auth.state == AuthState.EXPIRED
        assert len(client.rest._session.cookie_jar) == 0
    finally:
        await client.close()
    assert cache.load() is None


@pytest.mark.asyncio
async def test_clear_cancels_resume_validation_before_late_response_can_restore_cookies():
    cache = MemoryCache(snapshot())
    client = local_client(cache)
    entered, release = asyncio.Event(), asyncio.Event()
    async def delayed_balance(method, url, **kwargs):
        assert url.endswith('/address/wallets')
        entered.set()
        await release.wait()
        client.rest._session.cookie_jar.update_cookies(
            {'late_response_cookie': 'synthetic'}, response_url=URL('https://bit.team/'))
        return {'ok': True, 'result': {}}
    client.rest._send = delayed_balance
    pending = asyncio.create_task(client.resume_session())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.wait_for(client.clear_session(), 1)
        release.set()
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, (AuthenticationError, asyncio.CancelledError))
        assert client.auth.state == AuthState.NEW
        assert cache.load() is None
        assert len(client.rest._session.cookie_jar) == 0
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_resume_p2p_code_conflict_preserves_cache_without_logout_or_expiry():
    original = snapshot()
    cache = MemoryCache(original)
    cache.delete = Mock(wraps=cache.delete)
    client = local_client(cache)
    calls = []
    failure = BitTeamAPIError(409, 409003)
    async def rejected_validation(method, url, **kwargs):
        calls.append((method, url))
        assert method == "GET" and url.endswith("/address/wallets")
        raise failure
    client.rest._send = rejected_validation
    try:
        with pytest.raises(BitTeamAPIError) as raised:
            await client.resume_session()
        assert raised.value is failure
        preserved = cache.load()
        assert preserved is not None
        assert all(preserved[key] == original[key] for key in original if key != "cookies")
        cache.delete.assert_not_called()
        assert client.auth.state == AuthState.READY
        assert client.auth.headers() == {"Authorization": "Bearer synthetic-access"}
        assert len(calls) == 1  # No logout, token refresh or automatic retry.
    finally:
        await client.close()
    assert cache.load() is not None
    cache.delete.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("public", [False, True])
async def test_clear_cancels_regular_rest_response_before_late_cookie(public):
    client = local_client(MemoryCache())
    client.auth._install_tokens({"result": {"access": "synthetic-access", "refresh": "synthetic-refresh"}})
    entered, release = asyncio.Event(), asyncio.Event()
    async def response(*args, **kwargs):
        entered.set()
        await release.wait()
        client.rest._session.cookie_jar.update_cookies(
            {"late_cookie": "synthetic"}, response_url=URL("https://bit.team/"))
        return {"ok": True}
    client.rest._send = response
    pending = asyncio.create_task(client.rest._request("GET", "/pairs" if public else "/address/wallets", public=public))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await client.clear_session()
        release.set()
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, asyncio.CancelledError)
        assert len(client.rest._session.cookie_jar) == 0
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_new_login_during_server_logout_survives_old_logout_cleanup():
    client = local_client(MemoryCache())
    client.auth._install_tokens({"result": {"access": "synthetic-old", "refresh": "synthetic-old-refresh"}})
    entered = asyncio.Event()
    async def send(method, url, **kwargs):
        if url.endswith("/logout"):
            entered.set()
            await asyncio.Event().wait()
        if url.endswith("/clients/web/login"):
            return {"data": {"uid": "synthetic-user", "email_confirm": True, "is_authorize": True}}
        if url.endswith("/login-auth"):
            return {"result": {"access": "synthetic-new", "refresh": "synthetic-new-refresh"}}
        raise AssertionError("Unexpected local request")
    client.rest._send = send
    logout = asyncio.create_task(client.auth.logout())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert (await client.login("synthetic@example.test", "synthetic-password")).state == AuthState.READY
        result = (await asyncio.gather(logout, return_exceptions=True))[0]
        assert isinstance(result, asyncio.CancelledError)
        assert client.auth.headers() == {"Authorization": "Bearer synthetic-new"}
        assert client.auth.cache.load()["access"] == "synthetic-new"
        assert client.rest._session.cookie_jar.filter_cookies(URL(client.rest.base_url))["access"].value == "synthetic-new"
    finally:
        logout.cancel()
        await asyncio.gather(logout, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_clear_drain_does_not_remove_new_lifecycle_cookies():
    client = local_client(MemoryCache())
    entered, canceled, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    async def slow_cleanup():
        entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            canceled.set()
            await release.wait()
        return {}
    pending = asyncio.create_task(client.auth._tracked_operation(slow_cleanup()))
    cleanup = None
    try:
        await asyncio.wait_for(entered.wait(), 1)
        cleanup = asyncio.create_task(client.auth.clear_session())
        await asyncio.wait_for(canceled.wait(), 1)
        client.auth.clear(delete_cache=False)  # Simulates the next login boundary.
        client.auth._install_tokens({"result": {"access": "synthetic-next", "refresh": "synthetic-next-refresh"}})
        release.set()
        await asyncio.wait_for(cleanup, 1)
        assert client.rest._session.cookie_jar.filter_cookies(URL(client.rest.base_url))["access"].value == "synthetic-next"
        assert client.auth.state == AuthState.READY
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        if cleanup is not None:
            await asyncio.gather(cleanup, return_exceptions=True)
        await client.close()


@pytest.mark.asyncio
async def test_read_retry_wait_cannot_send_old_headers_after_new_login(monkeypatch):
    client = local_client(MemoryCache())
    client.auth._install_tokens({"result": {"access": "synthetic-old", "refresh": "synthetic-refresh"}})
    sleeping, release = asyncio.Event(), asyncio.Event()
    sends = []
    async def limited(*args, **kwargs):
        sends.append(kwargs["headers"])
        raise BitTeamAPIError(503, retry_after=0.1)
    async def retry_wait(delay):
        sleeping.set()
        await release.wait()
    client.rest._send = limited
    monkeypatch.setattr("bitteam_sdk.rest.asyncio.sleep", retry_wait)
    pending = asyncio.create_task(client.rest.get_balance())
    try:
        await asyncio.wait_for(sleeping.wait(), 1)
        await client.auth.clear_session()
        client.auth._install_tokens({"result": {"access": "synthetic-new", "refresh": "synthetic-new-refresh"}})
        release.set()
        outcome = (await asyncio.gather(pending, return_exceptions=True))[0]
        assert isinstance(outcome, asyncio.CancelledError)
        assert sends == [{"Authorization": "Bearer synthetic-old"}]
        assert client.auth.state == AuthState.READY
    finally:
        release.set()
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await client.close()
