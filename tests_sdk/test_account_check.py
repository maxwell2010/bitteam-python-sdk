import json
from unittest.mock import AsyncMock
import pytest
from bitteam_sdk import BitTeamClient, SessionAuth, BitTeamAPIError
from bitteam_sdk.account_check import AccountCheck, run_check


@pytest.mark.asyncio
async def test_probe_allows_only_authentication_and_balance(tmp_path):
    client = BitTeamClient(auth=SessionAuth())
    original = AsyncMock(return_value={'result': {}})
    client.rest._send = original
    probe = AccountCheck(client, tmp_path / 'report.json')
    for method, url in [
        ('POST','https://bit.team/trade/api/order/create'),
        ('POST','https://bit.team/trade/api/withdraw/create'),
        ('POST','https://bit.team/trade/api/all-orders/cancel'),
        ('GET','https://bit.team/trade/api/address/9/create'),
        ('GET','https://untrusted.test/trade/api/stock/balance'),
        ('GET','http://bit.team/trade/api/stock/balance'),
    ]:
        with pytest.raises(RuntimeError):
            await probe.guarded_send(method, url, data={})
    original.assert_not_called()
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('fail_refresh',[False,True])
async def test_probe_end_to_end_report_never_contains_credentials_or_balances(tmp_path,fail_refresh):
    client = BitTeamClient(auth=SessionAuth())
    await client.rest._get_session()
    async def response(method,url,**kwargs):
        if url.endswith('/clients/web/login'):
            return {'data':{'uid':'private-user-uid','email_confirm':True,'double_auth_google':True,'is_authorize':False}}
        if url.endswith('/clients/web/login-2fa'):
            return {'data':{'uid':'private-user-uid','is_authorize':False}}
        if url.endswith('/authorize/send-code'):
            return {'data':True}
        if url.endswith('/authorize/check-code'):
            return {'data':True}
        if url.endswith('/login-auth'):
            return {'result':{'access':'secret-access-one','refresh':'secret-refresh-one'}}
        if url.endswith('/refresh-token'):
            if fail_refresh:
                raise BitTeamAPIError(401,401010)
            return {'result':{'access':'secret-access-two','refresh':'secret-refresh-two'}}
        if url.endswith('/address/wallets'):
            return {'ok':True,'result':{'USDT':{'free':'987654.321098'}}}
        if url.endswith('/logout'):
            return {'ok':True}
        raise AssertionError('Unexpected operation')
    client.rest._send = response
    answers=iter(['secret-person@example.test','secret-password-value','012345','0123','telegram'])
    async def prompt(*args,**kwargs):
        return next(answers)
    destination=tmp_path/'report.json'
    await run_check(destination,prompt=prompt,client=client)
    raw=destination.read_text(encoding='utf-8')
    for secret in ['secret-person','secret-password','012345','0123','private-user-uid','secret-access','secret-refresh','987654.321098','USDT']:
        assert secret not in raw
    report=json.loads(raw)
    assert report['status']==('incomplete' if fail_refresh else 'passed')
    assert report['two_factor']=='passed'
    assert report['device_code']=='passed'
    assert report['device_delivery_user_reported']=='telegram'
    assert all(r['operation'] not in ('order','withdraw') for r in report['requests'])
