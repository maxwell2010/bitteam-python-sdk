"""Cache-validation generation races use only RAM cache and fake transport."""
import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import AuthenticationError, AuthState, BitTeamClient, SessionAuth


class Cache:
    def __init__(self):
        self.data = {'version': 1, 'base_url': 'https://bit.team/trade/api',
                     'auth_url': 'https://auth2.bit.team/v1', 'email': None,
                     'access': 'synthetic-cached-a', 'refresh': 'synthetic-cached-r', 'cookies': []}
        self.deletes = 0
    def load(self): return deepcopy(self.data)
    def save(self, value): self.data = deepcopy(value)
    def delete(self): self.deletes += 1; self.data = None


@pytest.mark.asyncio
@pytest.mark.parametrize('error', [AuthenticationError(401), AuthenticationError(200, 401001)])
async def test_late_resume_validation_failure_does_not_clear_refreshed_generation(error):
    cache = Cache()
    auth = SessionAuth(cache=cache)
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    entered, release = asyncio.Event(), asyncio.Event()
    async def balance():
        entered.set()
        await release.wait()
        raise error
    client.rest.get_balance = balance
    client.rest._send = AsyncMock(return_value={'result': {'access': 'synthetic-new-a', 'refresh': 'synthetic-new-r'}})
    old = asyncio.create_task(auth.resume())
    try:
        await entered.wait()
        await auth.refresh()
        generation, lifecycle = auth.generation, auth._lifecycle
        cache_after_refresh = deepcopy(cache.data)
        release.set()
        with pytest.raises(AuthenticationError) as caught:
            await old
        assert caught.value is error
        assert auth.state is AuthState.READY
        assert auth.headers() == {'Authorization': 'Bearer synthetic-new-a'}
        assert auth._refresh == 'synthetic-new-r'
        assert (auth.generation, auth._lifecycle) == (generation, lifecycle)
        assert cache.data == cache_after_refresh and cache.deletes == 0
        cookies = client.rest._session.cookie_jar.filter_cookies(URL(client.rest.base_url))
        assert cookies['access'].value == 'synthetic-new-a'
        assert cookies['refresh'].value == 'synthetic-new-r'
        assert not auth._pending_requests
    finally:
        release.set()
        await asyncio.gather(old, return_exceptions=True)
        await client.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('refresh,fail', [(False, True), (False, False), (True, False)])
async def test_resume_validation_controls_preserve_current_contract(refresh, fail):
    cache = Cache()
    auth = SessionAuth(cache=cache)
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    entered, release = asyncio.Event(), asyncio.Event()
    async def balance():
        entered.set()
        await release.wait()
        if fail: raise AuthenticationError(401)
        return {'synthetic': 'balance'}
    client.rest.get_balance = balance
    client.rest._send = AsyncMock(return_value={'result': {'access': 'synthetic-new-a', 'refresh': 'synthetic-new-r'}})
    task = asyncio.create_task(auth.resume())
    try:
        await entered.wait()
        if refresh: await auth.refresh()
        release.set()
        assert await task is (not fail)
        if fail:
            assert auth.state is AuthState.EXPIRED
            assert auth._access is None and auth._refresh is None
            assert cache.deletes == 1 and cache.data is None
            assert not client.rest._session.cookie_jar
        else:
            assert auth.state is AuthState.READY and cache.deletes == 0
            assert auth._access == ('synthetic-new-a' if refresh else 'synthetic-cached-a')
        assert not auth._pending_requests
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('code', [401001, 401010])
async def test_resume_clears_current_credentials_rejected_after_automatic_refresh(code):
    cache = Cache()
    auth = SessionAuth(cache=cache)
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    calls = []
    async def send(method, url, **kwargs):
        calls.append(kwargs['headers']['Authorization'])
        if url.endswith('/refresh-token'):
            return {'result': {'access': 'synthetic-new-a', 'refresh': 'synthetic-new-r'}}
        if len(calls) == 1:
            raise AuthenticationError(401, 401000)
        raise AuthenticationError(401, code)
    client.rest._send = send
    try:
        assert await auth.resume() is False
        assert calls == ['Bearer synthetic-cached-a', 'Bearer synthetic-cached-r', 'Bearer synthetic-new-a']
        assert auth.state is AuthState.EXPIRED
        assert auth._access is None and auth._refresh is None
        assert cache.data is None and cache.deletes == 1
        assert not client.rest._session.cookie_jar
        assert not auth._pending_requests
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_request_late_old_credential_failure_preserves_concurrent_refresh():
    cache = Cache()
    auth = SessionAuth(cache=cache)
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    entered, release = asyncio.Event(), asyncio.Event()
    old_error = AuthenticationError(401, 401001)
    calls = []
    async def send(method, url, **kwargs):
        calls.append(kwargs['headers']['Authorization'])
        if url.endswith('/refresh-token'):
            return {'result': {'access': 'synthetic-new-a', 'refresh': 'synthetic-new-r'}}
        entered.set()
        await release.wait()
        raise old_error
    client.rest._send = send
    task = asyncio.create_task(auth.resume())
    try:
        await entered.wait()
        await auth.refresh()
        release.set()
        with pytest.raises(AuthenticationError) as caught:
            await task
        assert caught.value is old_error
        assert calls == ['Bearer synthetic-cached-a', 'Bearer synthetic-cached-r']
        assert auth.state is AuthState.READY and auth._access == 'synthetic-new-a'
        assert cache.data['access'] == 'synthetic-new-a' and cache.deletes == 0
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()

@pytest.mark.asyncio
async def test_replayed_validation_tags_its_headers_before_later_refresh():
    cache = Cache()
    auth = SessionAuth(cache=cache)
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    replay_entered, release = asyncio.Event(), asyncio.Event()
    rejected = AuthenticationError(401, 401001)
    calls, refreshes = [], []
    async def send(method, url, **kwargs):
        bearer = kwargs['headers']['Authorization']
        calls.append(bearer)
        if url.endswith('/refresh-token'):
            label = 'B' if not refreshes else 'C'
            refreshes.append(label)
            return {'result': {'access': 'synthetic-access-' + label, 'refresh': 'synthetic-refresh-' + label}}
        if bearer == 'Bearer synthetic-cached-a':
            raise AuthenticationError(401, 401000)
        replay_entered.set()
        await release.wait()
        raise rejected
    client.rest._send = send
    task = asyncio.create_task(auth.resume())
    try:
        await replay_entered.wait()
        replay_generation = auth.generation
        await auth.refresh()
        release.set()
        with pytest.raises(AuthenticationError) as caught:
            await task
        assert caught.value is rejected
        assert rejected._credential_generation == replay_generation
        assert auth.generation == replay_generation + 1
        assert auth.state is AuthState.READY
        assert auth._access == cache.data['access'] == 'synthetic-access-C'
        assert cache.deletes == 0
        assert calls == ['Bearer synthetic-cached-a', 'Bearer synthetic-cached-r',
                         'Bearer synthetic-access-B', 'Bearer synthetic-refresh-B']
        assert not auth._pending_requests
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
        await client.close()
