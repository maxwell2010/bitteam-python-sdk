import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from bitteam_sdk import BitTeamClient, SessionAuth, AuthState
from bitteam_sdk.withdrawal_tracking import read_withdrawal, wait_for_withdrawal, WithdrawalWaitTimeout

@pytest.mark.asyncio
async def test_concurrent_close_waits_for_shared_resource_shutdown():
    client=BitTeamClient()
    entered, finish = asyncio.Event(), asyncio.Event()
    async def stop():
        entered.set()
        await finish.wait()
    client._site=SimpleNamespace(close=AsyncMock(side_effect=stop))
    first=asyncio.create_task(client.close())
    await entered.wait()
    second=asyncio.create_task(client.close())
    await asyncio.sleep(0)
    assert not second.done()
    first.cancel()
    with pytest.raises(asyncio.CancelledError): await first
    assert not second.done()
    finish.set()
    await asyncio.wait_for(second,1)
    client._site.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_closed_facade_does_not_restart_auth_or_open_resources():
    client=BitTeamClient(auth=SessionAuth())
    client.auth.login=AsyncMock()
    client.rest._get_session=AsyncMock()
    await client.close()
    for call in [lambda:client.login('a','b'),client.init,client.__aenter__,client.get_balance]:
        with pytest.raises(RuntimeError,match='closed'): await call()
    client.auth.login.assert_not_awaited()
    client.rest._get_session.assert_not_awaited()

@pytest.mark.asyncio
async def test_late_withdrawal_read_does_not_escape_client_close():
    started, release=asyncio.Event(),asyncio.Event()
    async def read(**kwargs):
        started.set()
        await release.wait()
        return {'id':'old'}
    client=SimpleNamespace(_closed=False,p2p=SimpleNamespace(get_withdrawal=read))
    task=asyncio.create_task(read_withdrawal(client,'old',source='p2p'))
    await started.wait()
    client._closed=True
    release.set()
    with pytest.raises(RuntimeError,match='closed'): await task

@pytest.mark.asyncio
async def test_late_withdrawal_read_cannot_cross_login_lifecycle():
    client=BitTeamClient(auth=SessionAuth())
    client.auth.state=AuthState.READY
    async def read(**kwargs):
        client.auth._lifecycle+=1
        return {'id':'old'}
    client._p2p=SimpleNamespace(get_withdrawal=read,close=AsyncMock())
    with pytest.raises(asyncio.CancelledError): await read_withdrawal(client,'old',source='p2p')
    await client.close()

@pytest.mark.asyncio
async def test_slow_predicate_cannot_report_success_after_deadline():
    client=SimpleNamespace(_closed=False,p2p=SimpleNamespace(get_withdrawal=AsyncMock(return_value={'id':'old'})))
    def slow(observation):
        time.sleep(.02)
        return True
    with pytest.raises(WithdrawalWaitTimeout) as error:
        await wait_for_withdrawal(client,'old',source='p2p',predicate=slow,timeout=.01)
    assert error.value.last_observation is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [{"amount":"NaN"},{"amount":"-1"},{"amount":"0"},{"currency_id":True},{"currency_id":2.0},{"address":"bad address"}])
async def test_request_withdrawal_validates_before_http(override):
    from bitteam_sdk.services import ServiceMethods
    from unittest.mock import Mock
    client=ServiceMethods()
    client._require_ready=Mock()
    client.api=SimpleNamespace(post_withdraw_create=AsyncMock())
    kwargs={"currency_id":2,"amount":"1","address":"synthetic"}
    kwargs.update(override)
    with pytest.raises(ValueError):await client.request_withdrawal(**kwargs)
    client.api.post_withdraw_create.assert_not_awaited()
