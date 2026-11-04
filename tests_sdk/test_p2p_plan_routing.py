"""A pure plan reaches only a fake body-callsite transport when explicitly used."""
import aiohttp
import pytest

from bitteam_sdk import P2PWithdrawalPlan, prepare_p2p_withdrawal
from test_p2p_api import Response, auth_with_cookie, client_with


def test_public_plan_export_never_opens_a_session(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Pure plan must not create an HTTP session")
    monkeypatch.setattr(aiohttp, "ClientSession", forbidden)
    plan = prepare_p2p_withdrawal(44, address="synthetic", amount="1.2500")
    assert isinstance(plan, P2PWithdrawalPlan)
    assert plan.payload["sum"] == "1.2500"


@pytest.mark.asyncio
async def test_explicit_plan_dispatch_uses_body_contract_without_legacy_query():
    client = client_with(auth_with_cookie(), Response({"data": {"id": "synthetic-record-id"}}))
    plan = prepare_p2p_withdrawal(44, address="synthetic", amount="1.2500")
    assert not client._session.calls
    await client.call(plan.operation, data=plan.payload)
    assert len(client._session.calls) == 1
    method, url, request = client._session.calls[0]
    assert method == "POST" and url == client.BASE_URL + "/account/create-withdraw"
    assert request["params"] is None
    assert request["json"] == plan.payload
    assert request["json"]["currency_id"] == 44
    assert request["json"]["sum"] == "1.2500"
    assert "hash" not in request["json"] and "date" not in request["json"]
