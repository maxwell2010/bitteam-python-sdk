"""Separate internal-stock frontend callsite; pure plans and fake HTTP only."""
from decimal import Inexact, Rounded, localcontext

import pytest

from bitteam_sdk import BitTeamAPIError
from bitteam_sdk.p2p_withdrawal import (
    P2PInternalTransferPlan, prepare_p2p_internal_transfer, prepare_p2p_withdrawal,
)
from test_p2p_api import auth_with_cookie, client_with, Response


@pytest.mark.parametrize("currency_id", [7, 95, 1234567])
def test_internal_plan_is_distinct_from_currency95_withdrawal_form(currency_id):
    plan = prepare_p2p_internal_transfer(currency_id, "001.230000000000000000001")
    assert isinstance(plan, P2PInternalTransferPlan)
    assert plan.operation == "create_internal_stock_transfer"
    assert plan.payload == {"currency_id": currency_id, "sum": "001.230000000000000000001",
                            "internal_request": True}
    assert not ({"address", "public", "date", "hash", "code"} & plan.payload.keys())
    if currency_id == 95:
        with pytest.raises(ValueError, match="date/hash"):
            prepare_p2p_withdrawal(currency_id, address="synthetic", amount="1")


def test_internal_plan_preserves_decimal_text_without_ambient_rounding_or_repr_leak():
    amount = "12345678901234567890.000000000000000000001"
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 2, 9, -9
        context.traps[Inexact] = context.traps[Rounded] = True
        plan = prepare_p2p_internal_transfer(7, amount)
    assert plan.payload["sum"] == amount
    assert amount not in repr(plan)


@pytest.mark.parametrize("currency_id", [None, True, False, 0, -1, 7.0, "7"])
def test_internal_plan_uses_explicit_local_currency_policy(currency_id):
    with pytest.raises(ValueError):
        prepare_p2p_internal_transfer(currency_id, "1")


@pytest.mark.parametrize("amount", [None, True, 1, 1.5, "0", "-1", "NaN", "Infinity",
    "1e2", " 1", "1_000", "１", ".1", "1."])
def test_internal_plan_uses_explicit_local_amount_policy(amount):
    with pytest.raises(ValueError):
        prepare_p2p_internal_transfer(7, amount)


@pytest.mark.asyncio
@pytest.mark.parametrize("currency_id", [7, 95])
async def test_explicit_raw_integration_sends_only_confirmed_body_and_general_bearer(currency_id):
    plan = prepare_p2p_internal_transfer(currency_id, "1.000000000000000001")
    payload = {"unverified-response-field": "raw"}
    api = client_with(auth_with_cookie(), Response(payload))
    assert await getattr(api, plan.operation)(data=plan.payload) is payload
    assert len(api._session.calls) == 1
    method, url, request = api._session.calls[0]
    assert method == "POST"
    assert url == "https://api-v2.bit.team/api/v2/account/create-withdraw-to-stock"
    assert request["json"] == plan.payload
    assert request["params"] is None and request["allow_redirects"] is False
    assert request["headers"]["Authorization"] == "Bearer synthetic-general-token"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"data": {}}, {"status": True}, [], None, "unverified", True])
async def test_internal_raw_response_does_not_require_id_or_infer_response_fields(payload):
    # Response(None) supplies a default fixture, so assign the value explicitly.
    response = Response()
    response.payload = payload
    api = client_with(auth_with_cookie(), response)
    assert await api.create_internal_stock_transfer(data={"currency_id": 7, "sum": "1", "internal_request": True}) is payload


@pytest.mark.asyncio
@pytest.mark.parametrize("status,payload", [(503, {}), (429, {}), (200, {"status": False}),
    (200, {"errors": ["synthetic"]}), (200, {"code": 409})])
async def test_internal_raw_http_and_explicit_envelope_errors_never_retry(status, payload):
    api = client_with(auth_with_cookie(), Response(payload, status))
    with pytest.raises(BitTeamAPIError):
        await api.create_internal_stock_transfer(data={"currency_id": 7, "sum": "1", "internal_request": True})
    assert len(api._session.calls) == 1
