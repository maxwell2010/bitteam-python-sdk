"""Private P2P routing tests use fake transports and synthetic cookies only."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest
from yarl import URL

from bitteam_sdk import SessionAuth, ApiKeyAuth, AuthState, AuthenticationError, BitTeamAPIError
from bitteam_sdk.p2p_api import BitTeamP2PAPI, P2P_CATALOG, P2P_SCHEMA


class Response:
    def __init__(self, payload=None, status=200):
        self.payload = {"status": True, "data": {"synthetic": True}, "code": 200} if payload is None else payload
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, response=None):
        self.response = response or Response()
        self.calls = []
        self.close = AsyncMock()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def auth_with_cookie(*, general=True, expired=False, wrong_domain=False):
    auth = SessionAuth()
    auth.state = AuthState.EXPIRED if expired else AuthState.READY
    auth._access = "synthetic-spot-access-never-use"
    jar = aiohttp.CookieJar()
    origin = URL("https://untrusted.example/" if wrong_domain else "https://api-v2.bit.team/api/v2")
    jar.update_cookies({"access": "synthetic-spot-cookie-never-use"}, response_url=origin)
    if general:
        jar.update_cookies({"access_token": "synthetic-general-token"}, response_url=origin)
    auth.bind(SimpleNamespace(_session=SimpleNamespace(cookie_jar=jar), _closed=False,
                              base_url="https://bit.team/trade/api"))
    return auth


def client_with(auth=None, response=None):
    client = BitTeamP2PAPI(auth)
    client._session = Session(response)
    client._limiter = SimpleNamespace(acquire=AsyncMock())
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", sorted(P2P_CATALOG))
async def test_every_confirmed_helper_routes_once_with_correct_auth(operation):
    entry = P2P_CATALOG[operation]
    payload = {"user": {}, "account": [], "total_usd": "0"} if entry.get("response_shape") == "auth_user" else {"status": True, "data": {"synthetic": True}, "code": 200}
    client = client_with(auth_with_cookie(), Response(payload))
    path = {key: "sample-id" for key in entry["path_params"]}
    params = {key: (2 if key in ("page", "limit") else "sample") for key, rule in entry["query"].items() if rule.get("required")}
    data = ({key: "sample" for key in entry.get("known_body_keys", [])} or {"explicit": "caller-body"}) if entry["method"] == "POST" else None
    result = await getattr(client, operation)(path=path, params=params, data=data)
    assert result is payload
    assert len(client._session.calls) == 1
    verb, url, request = client._session.calls[0]
    expected_path = entry["path"]
    for key in path:
        expected_path = expected_path.replace("{" + key + "}", "sample-id")
    assert verb == entry["method"]
    assert url == "https://api-v2.bit.team/api/v2" + expected_path
    assert request["allow_redirects"] is False
    assert request["json"] == data
    assert request["headers"].get("Authorization") == ("Bearer synthetic-general-token" if entry["private"] else None)
    for key, rule in entry["query"].items():
        if "fixed" in rule:
            assert request["params"][key] == rule["fixed"]
        elif "default" in rule:
            assert request["params"][key] == rule["default"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["none", "api_key", "spot_only", "expired", "other_domain"])
async def test_private_never_falls_back_to_basic_or_spot_access(mode):
    auth = {"none": None, "api_key": ApiKeyAuth("key", "secret"),
            "spot_only": auth_with_cookie(general=False), "expired": auth_with_cookie(expired=True),
            "other_domain": auth_with_cookie(wrong_domain=True)}[mode]
    client = client_with(auth)
    with pytest.raises(AuthenticationError):
        await client.get_my_advert()
    assert not client._session.calls


@pytest.mark.asyncio
async def test_expired_general_cookie_cannot_be_used():
    auth = auth_with_cookie(general=False)
    from http.cookies import SimpleCookie
    cookie = SimpleCookie(); cookie["access_token"] = "expired-secret"; cookie["access_token"]["max-age"] = "-1"
    auth._transport._session.cookie_jar.update_cookies(cookie, response_url=URL(BitTeamP2PAPI.BASE_URL))
    client = client_with(auth)
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("configuration", ["closed", "custom_spot", "custom_auth"])
async def test_private_token_from_closed_or_other_configuration_is_never_sent(configuration):
    auth = auth_with_cookie()
    if configuration == "closed":
        auth._transport._closed = True
    elif configuration == "custom_spot":
        auth._transport.base_url = "https://staging.example/trade/api"
    else:
        auth.auth_url = "https://staging-auth.example/v1"
    client = client_with(auth)
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    assert not client._session.calls


@pytest.mark.asyncio
async def test_private_request_queued_before_auth_close_does_not_send_after_close():
    auth = auth_with_cookie()
    client = client_with(auth)
    async def close_owner():
        auth._transport._closed = True
    client._limiter.acquire = close_owner
    with pytest.raises(AuthenticationError):
        await client.get_active_operations()
    assert not client._session.calls


@pytest.mark.asyncio
async def test_unknown_arbitrary_endpoint_and_unsafe_path_cannot_reach_transport():
    client = client_with(auth_with_cookie())
    for operation, path in [("get_request_cabinet", {}), ("https://untrusted.example", {}),
                            ("delete_advert_user", {"advert_id": "../other"}),
                            ("delete_advert_user", {"advert_id": "%2fother"})]:
        with pytest.raises(ValueError):
            await client.call(operation, path=path)
    assert not client._session.calls


@pytest.mark.asyncio
async def test_dynamic_query_and_unknown_body_are_explicit_and_preserved():
    client = client_with(auth_with_cookie())
    raw = {"address": "synthetic-address", "sum": "1", "comment": "explicit caller data"}
    await client.create_new_withdraw(params={"currency_id": 44}, data=raw)
    method, url, request = client._session.calls[0]
    assert method == "POST" and url.endswith("/account/create-withdraw")
    assert request["params"] == {"currency_id": 44}
    assert request["json"] is raw
    with pytest.raises(ValueError):
        await client.create_new_withdraw(data=raw)
    with pytest.raises(ValueError):
        await client.get_archived_adverts(params={"archive": 0})
    assert len(client._session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status,exception", [
    ({"status": False, "errors": {"private": "do-not-log-secret"}, "code": 422}, 422, BitTeamAPIError),
    ({"status": False, "errors": [], "code": 401}, 200, BitTeamAPIError),
    ({}, 302, BitTeamAPIError),
    (ValueError("do-not-log-secret"), 200, BitTeamAPIError),
    (asyncio.TimeoutError("do-not-log-secret"), 200, asyncio.TimeoutError),
])
async def test_mutating_get_is_single_attempt_and_errors_are_redacted(payload,status,exception,capsys):
    client = client_with(auth_with_cookie(),Response(payload,status))
    with pytest.raises(exception) as error:
        await client.accept_operation(params={"link": "synthetic-link"})
    assert len(client._session.calls) == 1
    assert "do-not-log-secret" not in str(error.value)
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


@pytest.mark.asyncio
async def test_no_account_cookies_or_environment_auth_in_own_session():
    client = BitTeamP2PAPI()
    session = await client._get_session()
    assert isinstance(session.cookie_jar,aiohttp.DummyCookieJar)
    assert not session.trust_env
    assert "Authorization" not in session.headers
    await client.close(); await client.close()
    assert session.closed


def test_catalog_coverage_and_mutating_get_annotations():
    coverage = P2P_SCHEMA["coverage"]
    assert coverage["total_helpers"] == 62
    assert coverage["included_helpers"] == 61
    assert len(P2P_CATALOG) == 61 + len(coverage["derived_callsite_operations"]) == 63
    assert "getRequestCabinet" in coverage["excluded"]
    for name in ("accept_operation", "pay_operation", "send_coin_operation", "cancel_operation",
                 "cancel_withdraw", "delete_advert_user", "get_auth_google_active"):
        assert P2P_CATALOG[name]["method"] == "GET"
        assert P2P_CATALOG[name]["get_mutation"] is True


@pytest.mark.asyncio
async def test_accounts_preserves_multi_network_wallet_data_without_requesting_creation():
    wallet = {"currency_id": 38, "balance": "1", "additional_wallets": [{"currency_id": 44, "token_name": "TRC-20"}],
              "possible_wallets": {"63": "BEP-20"}}
    payload = {"user": {"username": "synthetic-user"}, "account": [wallet], "total_usd": "1"}
    client = client_with(auth_with_cookie(), Response(payload))
    assert (await client.get_accounts())["account"][0] is wallet
    assert len(client._session.calls) == 1
    assert client._session.calls[0][0:2] == ("GET", "https://api-v2.bit.team/api/v2/auth/user")
    assert P2P_CATALOG["get_accounts"]["derived_callsite"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"user": {}}, {"account": "not-wallets"}, {"account": [], "user": "bad-profile"}])
async def test_accounts_rejects_malformed_top_level_shape(payload):
    client = client_with(auth_with_cookie(), Response(payload))
    with pytest.raises(BitTeamAPIError):
        await client.get_accounts()
