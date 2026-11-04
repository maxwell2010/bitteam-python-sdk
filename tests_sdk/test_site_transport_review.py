"""Independent site/P2P/archive regressions; all responses and auth are synthetic."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import aiohttp
import pytest

from bitteam_sdk import SessionAuth, AuthState, AuthenticationError, BitTeamAPIError
from bitteam_sdk.archive import BitTeamArchive
from bitteam_sdk.site_api import BitTeamSiteAPI
from bitteam_sdk.p2p_api import BitTeamP2PAPI
from test_p2p_api import auth_with_cookie


class Response:
    def __init__(self, payload, status=200):
        self.payload, self.status = payload, status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        if isinstance(self.payload, BaseException):
            raise self.payload
        return self.payload


class Session:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.close = AsyncMock()

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


def fake_site(payload=None, status=200):
    client = BitTeamSiteAPI()
    client._session = Session(Response({"status": True, "data": []} if payload is None else payload, status))
    client._limiter = SimpleNamespace(acquire=AsyncMock())
    return client


def fake_archive(payload=None, status=200, auth=None):
    client = BitTeamArchive(auth)
    client._session = Session(Response({"ok": True, "result": []} if payload is None else payload, status))
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["site", "chart", "archive"])
@pytest.mark.parametrize("problem,expected", [
    (aiohttp.ClientConnectionError("synthetic-secret-query-or-header"), BitTeamAPIError),
    (asyncio.TimeoutError("synthetic-secret-query-or-header"), asyncio.TimeoutError),
])
async def test_transport_failures_are_redacted_single_attempt(kind, problem, expected, capsys):
    client = fake_archive(problem) if kind == "archive" else fake_site(problem)
    call = client.get_trades() if kind == "archive" else client.get_crypto_chart(1, "day") if kind == "chart" else client.get_coins()
    with pytest.raises(expected) as caught:
        await call
    assert "synthetic-secret" not in str(caught.value)
    assert "synthetic-secret" not in repr(caught.value)
    assert len(client._session.calls) == 1
    assert caught.value.__suppress_context__
    if expected is BitTeamAPIError:
        assert caught.value.status == 0
    assert not capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("chart", [False, True])
async def test_site_close_while_rate_limited_does_not_start_a_request(chart):
    client = fake_site()
    async def close_during_queue():
        await client.close()
    client._limiter.acquire = close_during_queue
    with pytest.raises(RuntimeError, match="closed"):
        if chart:
            await client.get_crypto_chart(1, "day")
        else:
            await client.get_coins()
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, True, False, [], {}])
async def test_site_none_and_boolean_ids_cannot_become_literal_paths(value):
    client = fake_site()
    with pytest.raises(ValueError):
        await client.get_crypto(value)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [None, True, False, [], {}])
async def test_p2p_none_and_boolean_ids_fail_before_transport(value):
    client = BitTeamP2PAPI(auth_with_cookie())
    client._session = Session(Response({"status": True, "data": {}}))
    client._limiter = SimpleNamespace(acquire=AsyncMock())
    with pytest.raises(ValueError):
        await client.get_withdrawal(path={"withdraw_id": value})
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [401, 422, 503, "200"])
async def test_p2p_inconsistent_success_envelope_is_not_accepted(code):
    client = BitTeamP2PAPI()
    client._session = Session(Response({"status": True, "data": {}, "code": code}))
    client._limiter = SimpleNamespace(acquire=AsyncMock())
    with pytest.raises(BitTeamAPIError):
        await client.get_subjects(params={"subject_id": 1})
    assert len(client._session.calls) == 1


@pytest.mark.asyncio
async def test_archive_unbound_session_auth_fails_cleanly_before_transport():
    auth = SessionAuth()
    auth.state, auth._access = AuthState.READY, "synthetic-token"
    client = fake_archive(auth=auth)
    with pytest.raises(AuthenticationError):
        await client.get_user_orders()
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["closed", "auth_origin", "spot_origin"])
async def test_archive_never_sends_spot_token_from_other_origin_or_closed_owner(mode):
    auth = auth_with_cookie()
    if mode == "closed":
        auth._transport._closed = True
    elif mode == "auth_origin":
        auth.auth_url = "https://staging-auth.example/v1"
    else:
        auth._transport.base_url = "https://staging-spot.example/trade/api"
    client = fake_archive(auth=auth)
    with pytest.raises((RuntimeError, ValueError)):
        await client.get_user_orders()
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("params", ["not-a-dict", {"limit": True}, {"limit": 0}, {"limit": 1001},
                                      {"offset": -1}, {"offset": 1000001}, {"page": 0}])
async def test_archive_pagination_is_bounded_before_request(params):
    client = fake_archive()
    with pytest.raises(ValueError):
        await client.get_trades(params=params)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"ok": False}, 200), ({"status": False}, 200), ({"errors": ["synthetic-secret"]}, 200),
    ("not-an-object", 200), (ValueError("synthetic-secret"), 200), ({}, 302), ({}, 503),
])
async def test_archive_failure_never_becomes_success_or_logs_response(payload, status):
    client = fake_archive(payload, status)
    with pytest.raises(BitTeamAPIError) as caught:
        await client.get_trades()
    assert "synthetic-secret" not in str(caught.value)
    assert len(client._session.calls) == 1
    assert client._session.calls[0][2]["allow_redirects"] is False


@pytest.mark.asyncio
async def test_archive_session_is_anonymous_and_close_is_idempotent():
    client = BitTeamArchive(None)
    session = await client._get_session()
    assert isinstance(session.cookie_jar, aiohttp.DummyCookieJar)
    assert not session.trust_env and "Authorization" not in session.headers
    assert session.timeout.total == 15
    await client.close()
    await client.close()
    assert session.closed
    with pytest.raises(RuntimeError, match="closed"):
        await client.get_trades()


@pytest.mark.asyncio
async def test_archive_private_trades_preserves_raw_result_and_uses_spot_token_only():
    auth = auth_with_cookie()
    payload = {"result": {"trades": []}}
    client = fake_archive(payload, auth=auth)
    assert await client.get_user_trades(params={"limit": 2, "offset": 0}) is payload
    method, url, request = client._session.calls[0]
    assert method == "GET" and url == "https://archive.bit.team/api/tradesByUser"
    assert request["headers"] == {"Authorization": "Bearer synthetic-spot-access-never-use"}
    await client.close()
    await client.close()
    client._session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_chart_error_array_is_not_success():
    client = fake_site({"errors": ["synthetic-private-details"]})
    with pytest.raises(BitTeamAPIError):
        await client.get_crypto_chart(1, "day")
    assert len(client._session.calls) == 1


@pytest.mark.asyncio
async def test_news_detail_categories_and_filters_use_blog_base_and_no_auth():
    client = fake_site([])
    assert await client.get_news_post(12) == []
    assert await client.get_news_categories(page=2, per_page=3) == []
    assert await client.get_news_posts(search="some & text", before="2026-01-01T00:00:00") == []
    assert client._session.calls[0][1] == "https://bit.team/blog/wp-json/wp/v2/posts/12"
    assert client._session.calls[1][2]["params"] == {"page": 2, "per_page": 3}
    assert client._session.calls[2][2]["params"]["search"] == "some & text"
    assert all(call[2]["headers"] == {"Accept": "application/json", "Accept-Language": "en"}
               for call in client._session.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["site", "archive", "p2p"])
async def test_cancellation_is_not_wrapped_as_api_failure(kind):
    client = fake_archive(asyncio.CancelledError()) if kind == "archive" else fake_site(asyncio.CancelledError())
    if kind == "p2p":
        client = BitTeamP2PAPI()
        client._session = Session(Response(asyncio.CancelledError()))
        client._limiter = SimpleNamespace(acquire=AsyncMock())
    with pytest.raises(asyncio.CancelledError):
        if kind == "archive":
            await client.get_trades()
        elif kind == "p2p":
            await client.get_subjects(params={"subject_id": 1})
        else:
            await client.get_coins()
    assert len(client._session.calls) == 1
