"""Deterministic challenge concurrency with RAM-only fake transport."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import AuthState, AuthenticationError, SessionAuth


def make_auth(state):
    auth = SessionAuth()
    auth.state = state
    auth._uid = 'synthetic-original-uid'
    auth.bind(SimpleNamespace(base_url='https://bit.team/trade/api',
                              clear_cookies=AsyncMock(), set_spot_cookies=lambda *args: None))
    return auth


@pytest.mark.asyncio
@pytest.mark.parametrize('method,state,success', [
    ('submit_totp', AuthState.TWO_FACTOR_REQUIRED, {'data': {'is_authorize': True}}),
    ('confirm_device', AuthState.DEVICE_CONFIRMATION_REQUIRED, {'data': True}),
])
async def test_completed_challenge_rejects_queued_duplicate_without_dispatch(method, state, success):
    auth = make_auth(state)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def send(*args, **kwargs):
        calls.append(args[1])
        if args[1].endswith('/login-auth'):
            return {'result': {'access': 'synthetic-access', 'refresh': 'synthetic-refresh'}}
        entered.set()
        await release.wait()
        return success
    auth._transport._send = send
    code = '012345' if method == 'submit_totp' else '0123'
    first = asyncio.create_task(getattr(auth, method)(code))
    await entered.wait()
    second = asyncio.create_task(getattr(auth, method)(code))
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        assert (await first).state is AuthState.GENERAL_SESSION_READY
        with pytest.raises(RuntimeError):
            await second
        await auth.open_spot_session()
        assert auth.state is AuthState.READY
        assert len(calls) == 2
    finally:
        release.set()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_failed_totp_releases_lock_for_independent_retry():
    auth = make_auth(AuthState.TWO_FACTOR_REQUIRED)
    count = 0
    async def send(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1: raise AuthenticationError(401)
        return {'data': {'is_authorize': False}}
    auth._transport._send = send
    with pytest.raises(AuthenticationError):
        await auth.submit_totp('012345')
    assert (await auth.submit_totp('012345')).state is AuthState.DEVICE_CONFIRMATION_REQUIRED
    assert count == 2


@pytest.mark.asyncio
async def test_relogin_invalidates_queued_old_challenge_even_when_state_matches():
    auth = make_auth(AuthState.TWO_FACTOR_REQUIRED)
    calls = []
    async def send(*args, **kwargs):
        calls.append((args[1], kwargs['data']))
        return {'data': {'uid': 'synthetic-new-uid', 'double_auth_google': True}}
    auth._transport._send = send
    await auth._login_lock.acquire()
    login = asyncio.create_task(auth.login('synthetic@example.test', 'synthetic-password'))
    await asyncio.sleep(0)
    stale = asyncio.create_task(auth.submit_totp('012345'))
    await asyncio.sleep(0)
    auth._login_lock.release()
    try:
        assert (await login).state is AuthState.TWO_FACTOR_REQUIRED
        with pytest.raises(asyncio.CancelledError):
            await stale
        assert len(calls) == 1 and calls[0][0].endswith('/clients/web/login')
        assert auth._uid == 'synthetic-new-uid'
    finally:
        await asyncio.gather(login, stale, return_exceptions=True)

@pytest.mark.asyncio
async def test_queued_send_code_does_not_dispatch_after_device_confirmation():
    auth = make_auth(AuthState.DEVICE_CONFIRMATION_REQUIRED)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []
    async def send(*args, **kwargs):
        calls.append(args[1])
        entered.set()
        await release.wait()
        return {'data': True}
    auth._transport._send = send
    confirm = asyncio.create_task(auth.confirm_device('0123'))
    await entered.wait()
    delivery = asyncio.create_task(auth.send_device_code())
    try:
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        await confirm
        with pytest.raises(RuntimeError):
            await delivery
        assert len(calls) == 1
    finally:
        release.set()
        await asyncio.gather(confirm, delivery, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelling_active_totp_unlocks_for_queued_retry():
    auth = make_auth(AuthState.TWO_FACTOR_REQUIRED)
    entered = asyncio.Event()
    calls = []
    async def send(*args, **kwargs):
        calls.append(args[1])
        if len(calls) == 1:
            entered.set()
            await asyncio.Future()
        return {'data': {'is_authorize': False}}
    auth._transport._send = send
    active = asyncio.create_task(auth.submit_totp('012345'))
    await entered.wait()
    retry = asyncio.create_task(auth.submit_totp('012345'))
    try:
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
        assert (await retry).state is AuthState.DEVICE_CONFIRMATION_REQUIRED
        assert len(calls) == 2 and not auth._pending_requests
    finally:
        active.cancel()
        retry.cancel()
        await asyncio.gather(active, retry, return_exceptions=True)
