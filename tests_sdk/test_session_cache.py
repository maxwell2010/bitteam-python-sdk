import sys
import time
import pytest
from cryptography.fernet import Fernet
from bitteam_sdk import SessionCache, SessionCacheError
from bitteam_sdk.session_cache import WindowsDPAPI
from bitteam_sdk import BitTeamAPIError
from test_auth import environment


class TestProtector:
    __test__ = False
    def __init__(self):
        self.key = Fernet(Fernet.generate_key())
    def protect(self, content):
        return self.key.encrypt(content)
    def unprotect(self, content):
        return self.key.decrypt(content)


@pytest.fixture
def cache(tmp_path):
    return SessionCache('test', directory=tmp_path, protector=TestProtector())


def test_cache_encrypts_all_sensitive_fields_and_rejects_extra_password(cache):
    data={'version':1,'base_url':'https://bit.team/trade/api','auth_url':'https://auth2.bit.team/v1',
          'email':'private-email@example.test','access':'private-access','refresh':'private-refresh','cookies':[]}
    cache.save(data)
    raw=cache.path.read_bytes()
    for secret in ('private-email','private-access','private-refresh'):
        assert secret.encode() not in raw
    assert cache.load()==data
    with pytest.raises(SessionCacheError):
        cache.save(dict(data,password='never-save-this'))
    cache.path.write_bytes(raw[:-3]+b'bad')
    with pytest.raises(SessionCacheError):
        cache.load()
    cache.delete()
    assert cache.load() is None


@pytest.mark.skipif(sys.platform!='win32',reason='Windows DPAPI is platform-specific')
def test_real_windows_dpapi_roundtrip_and_integrity(tmp_path):
    cache=SessionCache('dpapi-test',directory=tmp_path)
    data={'version':1,'base_url':'https://bit.team/trade/api','auth_url':'https://auth2.bit.team/v1',
          'email':None,'access':'dpapi-access-sentinel','refresh':'dpapi-refresh-sentinel','cookies':[]}
    cache.save(data)
    assert b'dpapi-access-sentinel' not in cache.path.read_bytes()
    assert cache.load()==data
    cache.path.write_bytes(cache.path.read_bytes()[:-10]+b'corrupted!')
    with pytest.raises(SessionCacheError):
        cache.load()


@pytest.mark.asyncio
async def test_new_client_resumes_without_login_and_persists_rotated_tokens(environment,cache):
    state,create=environment
    first=await create(); first.auth.cache=cache
    await first.login('person@example.test','secret-password')
    await first.close()
    logins=state['counts']['/v1/clients/web/login']
    second=await create(); second.auth.cache=cache
    assert await second.resume_session()
    assert state['counts']['/v1/clients/web/login']==logins
    assert any(c.key=='p2p_access_token' for c in second.rest._session.cookie_jar)
    await second.refresh()
    assert cache.load()['access']=='spot-a1'
    assert cache.load()['refresh']=='spot-r1'
    await second.close()
    # Re-closing an old client must not overwrite the latest rotated tokens.
    await first.close()
    assert cache.load()['access']=='spot-a1'
    third=await create(); third.auth.cache=cache
    assert await third.resume_session()
    assert state['counts']['/v1/clients/web/login']==logins


@pytest.mark.asyncio
async def test_resume_auto_refreshes_expired_access(environment,cache):
    state,create=environment
    first=await create();first.auth.cache=cache
    await first.login('person@example.test','secret-password');await first.close()
    state['expire']=True
    second=await create();second.auth.cache=cache
    assert await second.resume_session()
    assert cache.load()['access']=='spot-a1'
    assert state['counts']['/trade/api/refresh-token']==1


@pytest.mark.asyncio
async def test_invalid_refresh_deletes_cached_session(environment,cache):
    state,create=environment
    first=await create();first.auth.cache=cache
    await first.login('person@example.test','secret-password');await first.close()
    state.update(expire=True,refresh_fail=True)
    second=await create();second.auth.cache=cache
    assert not await second.resume_session()
    assert not cache.exists
    assert len(second.rest._session.cookie_jar)==0


@pytest.mark.asyncio
async def test_temporary_server_failure_does_not_delete_cache(environment,cache):
    state,create=environment
    first=await create();first.auth.cache=cache
    await first.login('person@example.test','secret-password');await first.close()
    state.update(expire=True,refresh_unavailable=True)
    second=await create();second.auth.cache=cache
    with pytest.raises(BitTeamAPIError):
        await second.resume_session()
    assert cache.exists


@pytest.mark.asyncio
async def test_local_clear_makes_no_server_request_and_close_does_not_recreate_cache(environment,cache):
    state,create=environment
    client=await create();client.auth.cache=cache
    await client.login('person@example.test','secret-password')
    count=len(state['calls'])
    await client.clear_session()
    assert len(state['calls'])==count
    assert not cache.exists
    assert len(client.rest._session.cookie_jar)==0
    await client.close()
    assert not cache.exists


@pytest.mark.asyncio
async def test_logout_revokes_and_deletes_cache_even_if_server_fails(environment,cache,monkeypatch):
    state,create=environment
    client=await create();client.auth.cache=cache
    await client.login('person@example.test','secret-password')
    async def failed(*args,**kwargs):
        raise BitTeamAPIError(503)
    monkeypatch.setattr(client.rest,'_send',failed)
    with pytest.raises(BitTeamAPIError):
        await client.logout()
    assert not cache.exists
    assert len(client.rest._session.cookie_jar)==0
    await client.close()
    assert not cache.exists


@pytest.mark.asyncio
async def test_expired_cookie_is_not_resurrected_and_host_only_is_preserved(environment,cache):
    state,create=environment
    first=await create();first.auth.cache=cache
    await first.login('person@example.test','secret-password');await first.close()
    data=cache.load()
    for cookie in data['cookies']:
        if cookie['name']=='p2p_access_token':cookie['expires_at']=time.time()-1
    cache.save(data)
    second=await create();second.auth.cache=cache
    assert await second.resume_session()
    names={c.key for c in second.rest._session.cookie_jar}
    assert 'p2p_access_token' not in names
    from yarl import URL
    assert 'access' not in second.rest._session.cookie_jar.filter_cookies(URL(second.auth.auth_url))


@pytest.mark.asyncio
async def test_different_api_origin_cannot_use_saved_tokens(environment,cache):
    state,create=environment
    first=await create();first.auth.cache=cache
    await first.login('person@example.test','secret-password');await first.close()
    data=cache.load();data['base_url']='https://another.example/trade/api';cache.save(data)
    second=await create();second.auth.cache=cache
    before=len(state['calls'])
    with pytest.raises(SessionCacheError):
        await second.resume_session()
    assert len(state['calls'])==before


def test_profile_cannot_escape_cache_directory(tmp_path):
    with pytest.raises(ValueError):
        SessionCache('../bad',directory=tmp_path,protector=TestProtector())
