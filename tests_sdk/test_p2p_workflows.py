"""Saved frontend read contracts, synthetic payloads, no exchange requests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk.auth import BitTeamAPIError, SessionAuth
from bitteam_sdk.p2p_workflows import inspect_p2p_withdrawal, read_p2p_accounts


def client(*, accounts=None, withdrawal=None):
    return SimpleNamespace(auth=SessionAuth(), _closed=False,
        p2p=SimpleNamespace(get_accounts=AsyncMock(return_value=accounts),
                            get_withdrawal=AsyncMock(return_value=withdrawal)))


@pytest.mark.asyncio
async def test_account_snapshot_keeps_p2p_ids_and_nested_raw_fields_without_guessing():
    secret = "synthetic-private-SECRET"
    payload = {"account": [{"currency_id": 77, "balance": "1.234567890123456789",
        "hold": "0.1", "additional_wallets": [{"currency_id": 78}],
        "possible_wallets": [{"currency_id": 79}], "unknown": secret}],
        "user": {"login": secret}, "total_usd": "arbitrary-server-value"}
    api = client(accounts=payload)
    snapshot = await read_p2p_accounts(api)
    api.p2p.get_accounts.assert_awaited_once_with()
    api.p2p.get_withdrawal.assert_not_awaited()
    assert snapshot.accounts[0] == payload["account"][0]
    assert snapshot.total_usd == "arbitrary-server-value"
    assert secret not in repr(snapshot)
    payload["account"][0]["additional_wallets"].clear()
    assert snapshot.accounts[0]["additional_wallets"] == [{"currency_id": 78}]
    snapshot.raw["account"].clear()
    assert len(snapshot.accounts) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, {}, {"account": {}}, {"account": [1]},
    {"account": [], "user": None}])
async def test_malformed_account_rows_fail_without_empty_snapshot(payload):
    with pytest.raises(BitTeamAPIError):
        await read_p2p_accounts(client(accounts=payload))


@pytest.mark.asyncio
async def test_empty_accounts_valid_and_absent_optional_fields_remain_absent():
    snapshot = await read_p2p_accounts(client(accounts={"account": []}))
    assert snapshot.accounts == ()
    assert snapshot.user is None and snapshot.total_usd is None
    assert "user" not in snapshot.raw


@pytest.mark.asyncio
@pytest.mark.parametrize("status,state", [(-1, "cancelled"), (0, "created"), (1, "pending"),
    (2, "unknown"), ("success", "unknown"), (True, "unknown")])
async def test_inspection_only_reads_proven_envelope_and_preserves_unknown_status(status, state):
    api = client(withdrawal={"status": True, "data": {
        "id": "record-id", "type": "withdraw", "status": status,
        "created": "raw-date", "sum": "0.1", "percent": "raw-fee", "coin": {"alias": "raw"}}})
    snapshot = await inspect_p2p_withdrawal(api, "requested-id")
    api.p2p.get_withdrawal.assert_awaited_once_with(path={"withdraw_id": "requested-id"})
    api.p2p.get_accounts.assert_not_awaited()
    assert snapshot.observation.identifier == "requested-id"
    assert snapshot.evidence.identifier == "record-id"
    assert snapshot.requested_identifier == "requested-id"
    assert snapshot.record_identifier == "record-id" and snapshot.state == state
    assert snapshot.evidence.state == state and snapshot.evidence.raw_status == status
    assert snapshot.evidence.tx_hash is None
    assert snapshot.evidence.raw["coin"] == {"alias": "raw"}


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"data": None}, {"data": []},
    {"result": {"id": 1}}, {"id": 1}])
async def test_inspection_does_not_guess_nested_record(payload):
    with pytest.raises(BitTeamAPIError):
        await inspect_p2p_withdrawal(client(withdrawal=payload), "known-id")


@pytest.mark.asyncio
async def test_unknown_record_type_never_receives_withdrawal_status_mapping():
    snapshot = await inspect_p2p_withdrawal(client(withdrawal={"data": {"type": "deposit", "status": 1}}), "known-id")
    assert snapshot.evidence.state == "unknown"


@pytest.mark.asyncio
async def test_withdrawal_snapshot_redacts_and_detaches_payload():
    payload = {"data": {"id": "synthetic-secret-id", "type": "withdraw", "status": 1,
                        "address": "synthetic-secret-address"}}
    snapshot = await inspect_p2p_withdrawal(client(withdrawal=payload), "synthetic-secret-request")
    assert "synthetic-secret" not in repr(snapshot)
    payload["data"]["address"] = "changed"
    assert snapshot.observation.payload["data"]["address"] == "synthetic-secret-address"
    snapshot.observation.payload["data"]["address"] = "another"
    assert snapshot.evidence.raw["address"] == "synthetic-secret-address"


@pytest.mark.asyncio
@pytest.mark.parametrize("workflow", ["accounts", "withdrawal"])
async def test_workflow_propagates_read_error_without_retry(workflow):
    api = client()
    method = api.p2p.get_accounts if workflow == "accounts" else api.p2p.get_withdrawal
    error = BitTeamAPIError(503)
    method.side_effect = error
    with pytest.raises(BitTeamAPIError) as caught:
        await (read_p2p_accounts(api) if workflow == "accounts" else inspect_p2p_withdrawal(api, "known-id"))
    assert caught.value is error and method.await_count == 1


@pytest.mark.asyncio
async def test_account_snapshot_rejects_auth_replacement_during_read():
    api = client()
    async def response():
        api.auth = SessionAuth()
        return {"account": []}
    api.p2p.get_accounts.side_effect = response
    with pytest.raises(asyncio.CancelledError):
        await read_p2p_accounts(api)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [{"status": False}, {"ok": False},
    {"errors": ["synthetic rejection"]}, {"code": 409}])
@pytest.mark.parametrize("workflow", ["accounts", "withdrawal"])
async def test_explicit_failure_envelope_cannot_become_snapshot(failure, workflow):
    payload = {"account": [], "data": {"type": "withdraw", "status": 1}, **failure}
    api = client(accounts=payload, withdrawal=payload)
    with pytest.raises(BitTeamAPIError):
        await (read_p2p_accounts(api) if workflow == "accounts" else inspect_p2p_withdrawal(api, "known-id"))
