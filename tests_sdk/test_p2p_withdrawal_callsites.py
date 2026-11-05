"""Body-based frontend withdrawal call sites; HTTP is always synthetic."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import AuthenticationError, BitTeamAPIError
from bitteam_sdk.p2p_api import P2P_CATALOG, P2P_SCHEMA
from test_p2p_api import Response, auth_with_cookie, client_with


CALLS = [
    ("create_withdrawal_body", "/account/create-withdraw", 44),
    ("create_withdrawal_to_stock_body", "/account/create-withdraw-to-stock", 95),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
@pytest.mark.parametrize("mutation", ["switch_branch", "remove_selector"])
async def test_queued_body_mutation_cannot_bypass_fixed_callsite_selector(operation, route, currency_id, mutation):
    client = client_with(auth_with_cookie(), Response({"data": {"id": "synthetic-id"}}))
    body = {"currency_id": currency_id}
    async def mutate_while_queued():
        if mutation == "remove_selector":
            body.clear()
        else:
            body["currency_id"] = 95 if currency_id != 95 else 44
    client._limiter.acquire = mutate_while_queued
    with pytest.raises(ValueError):
        await getattr(client, operation)(data=body)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
async def test_body_callsites_send_explicit_body_once_without_currency_query(operation, route, currency_id):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response({"status": True, "data": {"id": "opaque-record-id"}}))
    # These are caller-provided opaque fields, not a generated withdrawal hash.
    body = {"currency_id": currency_id, "address": "synthetic-address", "sum": "1.25",
            "hash": "explicit-synthetic-opaque-value"}
    result = await getattr(client, operation)(data=body)
    assert result == {"status": True, "data": {"id": "opaque-record-id"}}
    assert len(client._session.calls) == 1
    method, url, request = client._session.calls[0]
    assert method == "POST" and url == client.BASE_URL + route
    assert request["params"] is None
    assert request["json"] is body
    assert request["headers"]["Authorization"] == "Bearer synthetic-general-token"
    assert request["allow_redirects"] is False
    auth.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_helper_keeps_its_distinct_query_currency_contract():
    client = client_with(auth_with_cookie(), Response({"status": True, "data": {"id": "synthetic-created-id"}}))
    body = {"address": "synthetic-address", "sum": "1.25"}
    await client.create_new_withdraw(params={"currency_id": 44}, data=body)
    _, url, request = client._session.calls[0]
    assert url == client.BASE_URL + "/account/create-withdraw"
    assert request["params"] == {"currency_id": 44}
    assert request["json"] is body
    assert "currency_id" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
async def test_body_callsites_require_explicit_dictionary_not_guessed_fields(operation, route, currency_id):
    client = client_with(auth_with_cookie(), Response({"status": True, "data": {"id": "synthetic-created-id"}}))
    with pytest.raises(ValueError):
        await getattr(client, operation)()
    with pytest.raises(ValueError):
        await getattr(client, operation)(data=[("currency_id", currency_id)])
    assert not client._session.calls
    with pytest.raises(ValueError):
        await getattr(client, operation)(data={"opaque": "caller-supplied"})
    # Only currency_id is required by this call-site selector. A complete
    # server body schema or stock hash algorithm is not inferred here.
    body = {"currency_id": currency_id, "opaque": "caller-supplied"}
    await getattr(client, operation)(data=body)
    assert client._session.calls[0][2]["json"] is body


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
@pytest.mark.parametrize("payload,status,error", [
    ({"status": False}, 401, AuthenticationError),
    (ValueError("synthetic-proxy-html"), 401, AuthenticationError),
    ({"status": False, "errors": {"sum": "synthetic-error"}}, 422, BitTeamAPIError),
    (asyncio.TimeoutError("synthetic-timeout"), 200, asyncio.TimeoutError),
])
async def test_withdrawal_body_errors_never_retry_refresh_or_confirm(operation, route, currency_id, payload, status, error):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response(payload, status))
    before = (auth.state, auth._lifecycle, auth.generation, auth.headers())
    with pytest.raises(error):
        await getattr(client, operation)(data={"currency_id": currency_id, "explicit": "synthetic-body"})
    assert len(client._session.calls) == 1
    assert client._session.calls[0][1] == client.BASE_URL + route
    assert (auth.state, auth._lifecycle, auth.generation, auth.headers()) == before
    auth.refresh.assert_not_awaited()


def test_derived_withdrawal_provenance_is_separate_from_helper_inventory():
    coverage = P2P_SCHEMA["coverage"]
    assert coverage["included_helpers"] == 61
    assert len(P2P_CATALOG) == 61 + len(coverage["derived_callsite_operations"]) == 84
    for operation, route, _ in CALLS:
        entry = P2P_CATALOG[operation]
        assert entry["derived_callsite"] is True and entry["js_helper"] is None
        assert entry["path"] == route and entry["method"] == "POST"
        assert entry["query"] == {} and entry["path_params"] == []
        assert entry["source_sha256"] == "3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685"
        assert entry["source_offset_is_approximate"] is True
        assert entry["evidence_observation"] == "user-reported public static GET HTTP200; SHA256 matches saved source"
        assert entry["private_live_verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,currency_id", [
    ("create_withdrawal_body", 95), ("create_withdrawal_body", 95.0),
    ("create_withdrawal_to_stock_body", "95"), ("create_withdrawal_to_stock_body", 44),
    ("create_withdrawal_to_stock_body", True), ("create_withdrawal_to_stock_body", None),
])
async def test_fixed_body_callsite_rejects_conflicting_selector_without_rerouting(operation, currency_id):
    client = client_with(auth_with_cookie(), Response({"status": True, "data": {"id": "synthetic-created-id"}}))
    with pytest.raises(ValueError):
        await getattr(client, operation)(data={"currency_id": currency_id, "hash": "caller-opaque"})
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,currency_id,route", [
    ("create_withdrawal_to_stock_body", 95.0, "/account/create-withdraw-to-stock"),
    ("create_withdrawal_body", "95", "/account/create-withdraw"),
])
async def test_raw_selector_matches_frontend_strict_numeric_comparison(operation, currency_id, route):
    client = client_with(auth_with_cookie(), Response({"status": True, "data": {"id": "synthetic-created-id"}}))
    await getattr(client, operation)(data={"currency_id": currency_id, "hash": "caller-opaque"})
    assert len(client._session.calls) == 1
    assert client._session.calls[0][1] == client.BASE_URL + route
    # These fake responses establish dispatch only, not accepted server bodies.
    assert client._session.calls[0][2]["json"]["currency_id"] == currency_id


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
@pytest.mark.parametrize("params", [{"currency_id": 44}, {"limit": 1}, {"opaque": "caller-value"}])
async def test_fixed_body_callsites_cannot_mix_in_legacy_or_unknown_query(operation, route, currency_id, params):
    client = client_with(auth_with_cookie(), Response({"status": True, "data": {"id": "synthetic-created-id"}}))
    with pytest.raises(ValueError):
        await getattr(client, operation)(params=params, data={"currency_id": currency_id})
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
@pytest.mark.parametrize("opaque_id", ["unrelated-record-id", 123, None, {"opaque": "uninterpreted"}])
async def test_direct_body_callsite_preserves_data_id_without_inventing_status_or_id_type(operation, route, currency_id, opaque_id):
    payload = {"data": {"id": opaque_id}}
    client = client_with(auth_with_cookie(), Response(payload))
    result = await getattr(client, operation)(data={"currency_id": currency_id})
    assert result is payload
    assert result["data"]["id"] is opaque_id
    assert "status" not in result
    assert len(client._session.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,route,currency_id", CALLS)
@pytest.mark.parametrize("payload", [
    {"data": {}}, {"data": []}, {"data": None}, {},
    {"data": {"id": "opaque"}, "status": False},
    {"data": {"id": "opaque"}, "ok": False},
    {"data": {"id": "opaque"}, "errors": {"synthetic": "error"}},
    {"data": {"id": "opaque"}, "code": 409},
    {"data": {"id": "opaque"}, "code": False},
])
async def test_direct_body_callsite_never_confuses_data_id_with_error_or_malformed_payload(operation, route, currency_id, payload):
    client = client_with(auth_with_cookie(), Response(payload))
    with pytest.raises(BitTeamAPIError):
        await getattr(client, operation)(data={"currency_id": currency_id})
    assert len(client._session.calls) == 1
