"""Owner replacement invalidates REST work even for non-session strategies."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import ApiKeyAuth, PublicAuth
from bitteam_sdk.rest import BitTeamRestAPI


class Response:
    status = 200
    headers = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return {"result": "synthetic account A"}


def fake_rest(auth):
    rest = BitTeamRestAPI(auth=auth)
    response = Response()
    calls = []
    session = SimpleNamespace(
        request=lambda *args, **kwargs: calls.append(kwargs) or response,
        close=AsyncMock())
    rest._session = session
    rest._limiter.acquire = AsyncMock()
    return rest, response, calls


def keys(suffix):
    return ApiKeyAuth("synthetic-" + suffix, "synthetic-secret-" + suffix)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["queue", "json"])
@pytest.mark.parametrize("roundtrip", [False, True])
@pytest.mark.parametrize("method,endpoint", [("POST", "/ccxt/ordercreate"), ("GET", "/ccxt/balance")])
async def test_key_replacement_invalidates_queued_dispatch_and_late_json(boundary, roundtrip, method, endpoint):
    auth = keys("A")
    rest, response, calls = fake_rest(auth)

    async def replace():
        rest.auth = keys("B")
        if roundtrip:
            rest.auth = auth
        return {"result": "synthetic account A"}

    if boundary == "queue":
        rest._limiter.acquire = replace
    else:
        response.json = replace
    try:
        with pytest.raises(asyncio.CancelledError):
            await rest._request(method, endpoint)
        assert len(calls) == (0 if boundary == "queue" else 1)
    finally:
        await rest.close()


@pytest.mark.asyncio
async def test_same_key_strategy_assignment_preserves_queued_request():
    auth = keys("A")
    rest, response, calls = fake_rest(auth)
    epoch = rest._auth_epoch

    async def preserve():
        rest.auth = auth

    rest._limiter.acquire = preserve
    try:
        assert await rest.get_balance() == {"result": "synthetic account A"}
        assert rest._auth_epoch == epoch
        assert len(calls) == 1
    finally:
        await rest.close()


@pytest.mark.asyncio
async def test_anonymous_public_request_remains_available():
    rest, response, calls = fake_rest(PublicAuth())
    try:
        assert await rest.api.get_pairs() == {"result": "synthetic account A"}
        assert len(calls) == 1
        assert calls[0]["headers"] == {}
    finally:
        await rest.close()
