from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from bitteam_sdk import BitTeamClient,SessionAuth,AuthState,BitTeamAPIError
from bitteam_sdk.models import Kline
from bitteam_sdk.archive import BitTeamArchive
from bitteam_sdk.site_api import BitTeamSiteAPI


@pytest.mark.asyncio
async def test_client_history_uses_shared_provider_and_half_open_range():
    client=BitTeamClient()
    client._history=SimpleNamespace(get_klines=AsyncMock(return_value=[
        Kline('DEL_USDT','1m',0,'1','1','1','1','1'),Kline('DEL_USDT','1m',60000,'1','1','1','1','1')]),close=AsyncMock())
    values=await client.fetch_klines('DEL_USDT',start=0,end=120)
    assert len(values)==2
    await client.close()
    client._history.close.assert_awaited_once()
    with pytest.raises(RuntimeError): _=client.market
    with pytest.raises(RuntimeError): _=client.site
    with pytest.raises(RuntimeError): _=client.p2p
    with pytest.raises(RuntimeError): _=client.archive


@pytest.mark.asyncio
async def test_client_public_subscriptions_resolve_exchange_pair_id():
    client=BitTeamClient()
    client.rest._pair_id=AsyncMock(return_value=24)
    client._market=SimpleNamespace(subscribe_orderbook=AsyncMock(return_value='book'),subscribe_trades=AsyncMock(return_value='trades'),close=AsyncMock())
    assert await client.subscribe_orderbook('DEL/USDT')=='book'
    assert await client.subscribe_trades('del-usdt')=='trades'
    assert all(c.args==('del_usdt',) for c in client.rest._pair_id.await_args_list)
    client._market.subscribe_orderbook.assert_awaited_once_with(24)
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('session',[False,True])
async def test_network_withdrawal_preparation_never_submits_but_explicit_request_does(session):
    client=BitTeamClient(auth=SessionAuth()) if session else BitTeamClient('key','secret')
    if session:client.auth.state=AuthState.READY;client.auth._access='synthetic-access'
    else:client._keys_validated=True
    currency={'id':3,'symbol':'usdt','active':True,'status':1,
              'txLimits':{'minWithdraw':'1','maxWithdraw':'100','withdrawCommissionFixed':{'Tron':'2'}},
              'links':[{'blockChain':'Ethereum'},{'blockChain':'Tron'},{'blockChain':'Binance'}]}
    calls=[]
    async def send(method,url,**kwargs):
        calls.append((method,url,kwargs))
        if url.endswith('/currencies'):return {'ok':True,'result':{'count':1,'currencies':[currency]}}
        return {'ok':True,'result':{'orderId':'synthetic-only'}}
    client.rest._send=send
    plan=await client.prepare_withdrawal('USDT',amount='10',address='synthetic-address',network='TRC20')
    assert plan['payload']=={'currencyId':3,'amount':'10','to':'synthetic-address','currency':'trx'}
    assert all(c[0]=='GET' for c in calls)
    await client.request_network_withdrawal('USDT',amount='10',address='synthetic-address',network='TRC20')
    posts=[c for c in calls if c[0]=='POST']
    assert len(posts)==1
    assert posts[0][1].endswith('/withdraw/create' if session else '/ccxt/withdraw')
    assert posts[0][2]['data']==plan['payload']
    await client.close()


@pytest.mark.asyncio
async def test_client_closes_every_resource_when_one_close_fails():
    c=BitTeamClient()
    c._history=SimpleNamespace(close=AsyncMock(side_effect=OSError('synthetic')))
    c._market=SimpleNamespace(close=AsyncMock())
    c._site=SimpleNamespace(close=AsyncMock())
    c.rest.close=AsyncMock()
    with pytest.raises(OSError):await c.close()
    c._market.close.assert_awaited_once();c._site.close.assert_awaited_once();c.rest.close.assert_awaited_once()


class Response:
    def __init__(self,payload,status=200):self.payload,self.status=payload,status
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def json(self):return self.payload


class Session:
    def __init__(self,response):self.response=response;self.calls=[]
    def get(self,*args,**kwargs):self.calls.append((args,kwargs));return self.response
    def post(self,*args,**kwargs):self.calls.append((args,kwargs));return self.response
    async def close(self):pass


@pytest.mark.asyncio
async def test_archive_public_does_not_send_credentials_and_does_not_follow_redirects():
    c=BitTeamClient('key','secret')
    archive=BitTeamArchive(c.auth)
    fake=Session(Response({'ok':True,'result':{'trades':[]}}))
    archive._get_session=AsyncMock(return_value=fake)
    assert (await archive.get_trades(params={'limit':2}))['ok']
    assert fake.calls[0][1]['headers']=={}
    assert fake.calls[0][1]['allow_redirects'] is False
    with pytest.raises(BitTeamAPIError):await archive.get_user_orders()
    await c.close()


@pytest.mark.asyncio
async def test_archive_uses_spot_bearer_only_for_fixed_production_origin():
    c=BitTeamClient(auth=SessionAuth());c.auth.state=AuthState.READY;c.auth._access='synthetic-spot'
    archive=BitTeamArchive(c.auth);fake=Session(Response({'result':{'orders':[]}}));archive._get_session=AsyncMock(return_value=fake)
    await archive.get_user_orders()
    assert fake.calls[0][1]['headers']=={'Authorization':'Bearer synthetic-spot'}
    c.rest.base_url='https://staging.example/trade/api'
    with pytest.raises(ValueError):await archive.get_user_orders()
    assert len(fake.calls)==1
    await c.close()


@pytest.mark.asyncio
async def test_news_and_chart_are_fixed_public_operations():
    api=BitTeamSiteAPI()
    api._get=AsyncMock(return_value=[])
    assert await api.get_news_posts(page=2,per_page=10,after='2026-01-01T00:00:00')==[]
    api._get.assert_awaited_with('news_posts',params={'page':2,'per_page':10,'after':'2026-01-01T00:00:00'})
    with pytest.raises(ValueError):await api.get_news_posts(per_page=101)
    fake=Session(Response({'data':[]}));api._get_session=AsyncMock(return_value=fake)
    await api.get_crypto_chart(1,'day')
    args,kwargs=fake.calls[0]
    assert args==('https://bitteam-market-back.bit.team/api/cryptocurrency/chart',)
    assert kwargs['json']=={'id':1,'period':'day'}
    assert kwargs['allow_redirects'] is False
    assert 'Authorization' not in kwargs['headers']
    await api.close()
