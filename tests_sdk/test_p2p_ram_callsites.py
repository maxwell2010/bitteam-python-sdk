"""User-relayed RAM inventory contracts; only synthetic HTTP dispatch."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import AuthenticationError, BitTeamAPIError
from bitteam_sdk.p2p_api import P2P_CATALOG
from test_p2p_api import Response, auth_with_cookie, client_with

# Independent fixed route/shape expectations from the reported source inventory.
CALLS = [
    ("get_currencies_with_commission", "GET", "/data/currency/with-commission", 525131, {}, None, ["opaque"]),
    ("create_wallbtc_operation", "POST", "/wallbtc/operations/create", 529881, {}, {"opaque": "caller"}, {"data": {"opaque": "value"}}),
    ("remove_blacklist_users", "POST", "/user/blacklist/remove-users", 535124, {}, None, {"opaque": "raw"}),
    ("get_email_notification_status", "GET", "/user/notification-status-email", 537267, {}, None, {"opaque": "raw"}),
    ("get_app_tokens", "GET", "/user/get-app-tokens", 539496, {}, None, {"tokens": ["opaque"]}),
    ("get_business_payments", "GET", "/user/business/get-payments", 540274, {}, None, {"data": ["opaque"]}),
    ("add_payment_system_temp", "POST", "/user/add-payment-systems-temp", 540773, {}, {"opaque": "caller"}, {"status": True, "data": {"opaque": "raw"}}),
    ("get_subscriptions", "GET", "/subscription/list", 541838, {}, None, {"data": [{"is_auto": "opaque"}]}),
    ("get_active_subscription", "GET", "/subscription/active", 542292, {}, None, {"data": {"opaque": "raw"}}),
    ("subscribe_subscription", "POST", "/subscription/subscribe", 542527, {}, {"type": "opaque"}, {"opaque": "raw"}),
    ("renew_subscription", "POST", "/subscription/renew", 543020, {}, None, {"data": {"is_auto": "opaque"}}),
    ("get_boost_price", "GET", "/boost/get-price", 543672, {}, None, {"opaque": "raw"}),
    ("get_subscription_price", "GET", "/subscription/get-price", 545095, {}, None, {"data": "opaque"}),
    ("get_notifications", "GET", "/user/get-notification", 548685, {"page": 1, "limit": 2, "type": "opaque"}, None, {"data": [], "meta": {"total": 0}}),
    ("get_active_notifications", "GET", "/user/get-active-notification", 549468, {"page": 1, "limit": 2}, None, {"data": [], "meta": {"count": 0}}),
    ("read_all_notifications", "GET", "/user/read-all-notification", 552090, {}, None, {"opaque": "raw"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("name,method,path,offset,params,body,payload", CALLS)
async def test_ram_fixed_callsites_dispatch_raw_once_without_legacy_status_assumption(name, method, path, offset, params, body, payload):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response(payload))
    result = await client.call(name, params=params, data=body)
    assert result is payload
    assert len(client._session.calls) == 1
    actual_method, url, request = client._session.calls[0]
    assert (actual_method, url) == (method, client.BASE_URL + path)
    assert request["json"] is body and request["params"] == (params or None)
    assert request["headers"]["Authorization"] == "Bearer synthetic-general-token"
    assert request["allow_redirects"] is False
    auth.refresh.assert_not_awaited()
    entry = P2P_CATALOG[name]
    assert entry["source_offset_method_start"] == offset
    assert entry["source_sha256"] == "2316cc9e89475e17ce2a2fae1378c40cb7e0eed706e80dc8f72925a7ff37ab49"
    assert entry["reported_contract"] and "source_excerpt" not in entry
    assert entry["private_live_verified"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("name,method,path,offset,params,body,payload", CALLS)
@pytest.mark.parametrize("failure,status,error", [
    ({"status": False}, 200, BitTeamAPIError),
    ({"errors": ["synthetic"]}, 200, BitTeamAPIError),
    ({"code": 409}, 200, BitTeamAPIError),
    ({"synthetic": "rejected"}, 401, AuthenticationError),
    (asyncio.TimeoutError("synthetic"), 200, asyncio.TimeoutError),
])
async def test_ram_failures_never_retry_or_refresh(name, method, path, offset, params, body, payload, failure, status, error):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response(failure, status))
    with pytest.raises(error):
        await client.call(name, params=params, data=body)
    assert len(client._session.calls) == 1
    auth.refresh.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["remove_blacklist_users", "renew_subscription"])
async def test_explicit_null_body_callsites_do_not_accept_caller_dictionary(name):
    client = client_with(auth_with_cookie())
    with pytest.raises(ValueError):
        await client.call(name, data={})
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["create_wallbtc_operation", "add_payment_system_temp", "subscribe_subscription"])
async def test_body_callsites_reject_missing_explicit_fields(name):
    client = client_with(auth_with_cookie())
    with pytest.raises(ValueError):
        await client.call(name)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"data": [], "meta": {"total": 0}}, {"data": [], "meta": {"count": 0}}])
async def test_notification_response_supports_both_observed_meta_variants(payload):
    client = client_with(auth_with_cookie(), Response(payload))
    assert await client.call("get_notifications", params={"page": 1, "limit": 2}) is payload


@pytest.mark.asyncio
@pytest.mark.parametrize("name,payload", [
    ("get_app_tokens", {}), ("get_business_payments", {}),
    ("get_subscriptions", {"data": {}}), ("renew_subscription", {"data": {}}),
    ("get_notifications", {"data": [], "meta": {}}),
    ("get_active_notifications", {"data": [], "meta": {"total": 1}}),
    ("add_payment_system_temp", {"data": {}}),
])
async def test_observed_response_paths_are_not_fabricated_when_missing(name, payload):
    client = client_with(auth_with_cookie(), Response(payload))
    with pytest.raises(BitTeamAPIError):
        await client.call(name, data={"opaque": "caller"} if name == "add_payment_system_temp" else None)
    assert len(client._session.calls) == 1


def test_mutating_notification_get_is_not_a_safe_read():
    assert P2P_CATALOG["read_all_notifications"]["get_mutation"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("raw_status", [True, "opaque-status", None, 0])
async def test_temporary_payment_status_field_is_not_a_guessed_boolean_enum(raw_status):
    payload = {"status": raw_status, "data": {"opaque": "raw"}}
    client = client_with(auth_with_cookie(), Response(payload))
    assert await client.call("add_payment_system_temp", data={"caller": "opaque"}) is payload


@pytest.mark.asyncio
async def test_read_all_notifications_503_is_single_attempt_despite_get_method():
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response({"synthetic": "unavailable"}, 503))
    with pytest.raises(BitTeamAPIError) as error:
        await client.call("read_all_notifications")
    assert error.value.status == 503
    assert len(client._session.calls) == 1
    auth.refresh.assert_not_awaited()
