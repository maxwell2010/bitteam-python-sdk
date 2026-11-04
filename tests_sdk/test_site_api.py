"""Public site API contracts without live requests or account fixtures."""
import asyncio
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk.auth import BitTeamAPIError
from bitteam_sdk.site_api import BitTeamSiteAPI


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.close = AsyncMock()

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


def client_with(payload=None, status=200):
    client = BitTeamSiteAPI()
    client._session = Session(Response(payload if payload is not None else {"status": True, "data": []}, status))
    client._limiter = type("Limiter", (), {"acquire": AsyncMock()})()
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,kwargs,path,params", [
    ("get_coins", (), {}, "/public/coins/list", None),
    ("get_currencies", (), {}, "/public/currencies/list", None),
    ("get_rates_by_period", (3,2), {}, "/public/rates-by-period", {"coin_id":3,"currency_id":2,"type":"day","period":1}),
    ("get_static_menu", (), {}, "/public/static-page/2/get-all-menu", None),
    ("get_static_page", (2,1,41), {}, "/public/static-page/2/1/41", None),
    ("get_p2p_currencies", (), {}, "/get/data-init-currency", {"type":"coin,token"}),
    ("get_p2p_currencies", ("valute",), {}, "/get/data-init-currency", {"type":"valute"}),
    ("get_payment_methods", ("rub",), {}, "/get/data-init-payment-method", {"fiat_short_name":"RUB"}),
    ("get_advertisement_limits", (), {}, "/anunt/get-limit-percent", None),
    ("get_advertisements", (), {"type_":"buy","coin":"BTC","fiat":"RUB","limit":2,"online_only":True},
     "/anunt/get", {"type":"buy","coin_short_name":"BTC","fiat_short_name":"RUB","limit":2,"offset":0,"filter[strict][users.is_online]":1}),
])
async def test_v2_named_methods_construct_only_known_get_routes(method,args,kwargs,path,params):
    payload={"status":True,"data":[],"code":200}
    client=client_with(payload)
    assert await getattr(client,method)(*args,**kwargs) is payload
    url,request=client._session.calls[0]
    assert url=='https://api-v2.bit.team/api/v2'+path
    assert request['params']==params
    assert request['headers']=={'Accept':'application/json','Accept-Language':'en'}
    assert request['allow_redirects'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,kwargs,url,params", [
    ('get_crypto_map',(),{},'/cryptocurrency/map',{'limit':50,'page':1}),
    ('get_crypto_map',(),{'category':'gainers','limit':2},'/cryptocurrency/map/categories/gainers',{'limit':2,'page':1}),
    ('get_crypto_map',(),{'tag':'defi'},'/cryptocurrency/map',{'limit':50,'page':1,'tag':'defi'}),
    ('get_crypto',('bitcoin',),{},'/cryptocurrency/one/bitcoin',None),
    ('get_crypto_history',('bitcoin',),{'page':2},'/cryptocurrency/historical/bitcoin',{'limit':50,'page':2}),
    ('get_market_pairs',('bitcoin',),{},'/market_pairs/coin/bitcoin',{'limit':50,'page':1}),
    ('get_crypto_metadata',('bitcoin',),{},'/page/coin-meta/bitcoin',None),
    ('get_common_cryptos',(),{},'/core/common/cryptos',None),
    ('get_common_markets',(),{},'/core/common/markets',None),
])
async def test_market_routes_preserve_raw_json(method,args,kwargs,url,params):
    payload=[{'arbitrary':'public-server-data'}]
    client=client_with(payload)
    assert await getattr(client,method)(*args,**kwargs) is payload
    actual,request=client._session.calls[0]
    assert actual=='https://bitteam-market-back.bit.team/api'+url
    assert request['params']==params
    assert request['headers']['Accept-Language']=='en-US'


@pytest.mark.asyncio
async def test_docs_search_is_query_encoded_not_path_interpolated():
    client=client_with({'data':[]})
    assert await client.get_docs_pages(locale='ru',search='test & other')=={'data':[]}
    url,request=client._session.calls[0]
    assert url=='https://docs-api.bit.team/api/v1/pages'
    assert request['params']=={'locale':'ru','include':'parent','filter[name]':'test & other','fields[pages]':'slug,name,parent'}


@pytest.mark.asyncio
@pytest.mark.parametrize("method,args,kwargs", [
    ('get_rates_by_period',(True,2),{}),
    ('get_crypto',('../private',),{}),
    ('get_static_page',(2,1,0),{}),
    ('get_p2p_currencies',('unknown',),{}),
    ('get_advertisements',(),{'type_':'delete','coin':'BTC','fiat':'RUB'}),
    ('get_advertisements',(),{'type_':'buy','coin':'BTC','fiat':'RUB','limit':1001}),
    ('get_advertisements',(),{'type_':'buy','coin':'BTC','fiat':'RUB','sum_':'NaN'}),
    ('get_crypto_map',(),{'category':'gainers','tag':'defi'}),
    ('get_docs_pages',(),{'search':'x'*201}),
])
async def test_invalid_inputs_are_rejected_without_transport(method,args,kwargs):
    client=client_with()
    with pytest.raises(ValueError):
        await getattr(client,method)(*args,**kwargs)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('payload,status', [
    ({'status':False,'message':'sensitive response must not echo','code':422},200),
    ({'status':True,'data':[],'errors':['sensitive response must not echo']},200),
    ([],200),
    ({'data':[]},200),
    ({'status':True,'data':[],'code':500},200),
    (ValueError('sensitive response must not echo'),200),
    ({},302),
    ({},502),
])
async def test_failed_or_malformed_envelopes_and_redirects_never_become_fake_success(payload,status,capsys):
    client=client_with(payload,status)
    with pytest.raises(BitTeamAPIError) as error:
        await client.get_coins()
    assert 'sensitive response' not in str(error.value)
    output=capsys.readouterr()
    assert not output.out and not output.err
    assert len(client._session.calls)==1


@pytest.mark.asyncio
async def test_timeout_propagates_without_inventing_data_or_retries():
    client=client_with(asyncio.TimeoutError())
    with pytest.raises(asyncio.TimeoutError):
        await client.get_crypto('bitcoin')
    assert len(client._session.calls)==1


@pytest.mark.asyncio
async def test_only_get_allowlist_no_mutations_or_arbitrary_url():
    client=client_with()
    for operation in ('create_withdraw','accept_operation','https://untrusted.example'):
        with pytest.raises(ValueError):
            await client._get(operation)
    assert not client._session.calls
    assert not hasattr(client,'post')


@pytest.mark.asyncio
async def test_own_session_is_anonymous_and_close_is_idempotent():
    client=BitTeamSiteAPI()
    session=await client._get_session()
    assert isinstance(session.cookie_jar,aiohttp.DummyCookieJar)
    assert session.trust_env is False
    assert 'Authorization' not in session.headers
    assert session.timeout.total==20
    await client.close();await client.close()
    assert session.closed
    with pytest.raises(RuntimeError):
        await client.get_coins()


@pytest.mark.parametrize('kwargs',[{'timeout':0},{'timeout':61},{'timeout':float('nan')},{'locale':'en-US'}])
def test_invalid_configuration(kwargs):
    with pytest.raises(ValueError):
        BitTeamSiteAPI(**kwargs)
