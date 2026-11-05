"""Synthetic challenge transitions: no delivery, accounts, cache or transport."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk import AuthenticationError, AuthState, BitTeamClient, SessionAuth


def device_client(response):
    auth = SessionAuth()
    auth.state = AuthState.DEVICE_CONFIRMATION_REQUIRED
    auth._uid = 'synthetic-challenge-A'
    client = BitTeamClient(auth=auth)
    client.rest._session = SimpleNamespace(cookie_jar=aiohttp.CookieJar(), close=AsyncMock())
    calls = []
    async def send(method, url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith('/login-auth'):
            return {'result': {'access': 'synthetic-access', 'refresh': 'synthetic-refresh'}}
        return response
    client.rest._send = send
    return client, auth, calls


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [0, False])
@pytest.mark.parametrize('facade', [False, True])
async def test_device_explicit_denial_does_not_open_spot(value, facade):
    client, auth, calls = device_client({'data': {'is_authorize': value}})
    with pytest.raises(AuthenticationError):
        await (client.confirm_device('0123') if facade else auth.confirm_device('0123'))
    assert auth.state == AuthState.DEVICE_CONFIRMATION_REQUIRED
    assert len(calls) == 1 and calls[0][0].endswith('/authorize/check-code')
    assert auth._access is None and auth._refresh is None


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [1, True])
async def test_device_explicit_success_opens_spot_once(value):
    client, auth, calls = device_client({'data': {'is_authorize': value}})
    assert (await client.confirm_device('0123')).state == AuthState.READY
    assert [url.rsplit('/', 1)[-1] for url, _ in calls] == ['check-code', 'login-auth']
    assert auth.headers() == {'Authorization': 'Bearer synthetic-access'}


@pytest.mark.asyncio
async def test_malformed_totp_transition_preserves_challenge_for_retry():
    client, auth, calls = device_client({'data': {'uid': 'synthetic-unvalidated-UID'}})
    auth.state = AuthState.TWO_FACTOR_REQUIRED
    with pytest.raises(AuthenticationError):
        await auth.submit_totp('012345')
    assert auth._uid == 'synthetic-challenge-A'
    assert auth.state == AuthState.TWO_FACTOR_REQUIRED
    async def retry(method, url, **kwargs):
        calls.append((url, kwargs))
        return {'data': {'uid': 'synthetic-valid-UID', 'is_authorize': 0}}
    client.rest._send = retry
    assert (await auth.submit_totp('012345')).state == AuthState.DEVICE_CONFIRMATION_REQUIRED
    assert calls[-1][1]['data']['uid'] == 'synthetic-challenge-A'
    assert auth._uid == 'synthetic-valid-UID'

@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, '0', '1', 2, [], {}])
async def test_device_unknown_explicit_flag_does_not_authorize(value):
    client, auth, calls = device_client({'data': {'is_authorize': value}})
    with pytest.raises(AuthenticationError):
        await client.confirm_device('0123')
    assert auth.state == AuthState.DEVICE_CONFIRMATION_REQUIRED
    assert len(calls) == 1
