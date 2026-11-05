"""Separate user-supplied frontend labels from financial transaction evidence."""
import pytest

from bitteam_sdk.transactions import TransactionEvidence, transaction_evidence


@pytest.mark.parametrize("status,ui_state,state", [
    (-1, "cancelled", "cancelled"), (0, "created", "created"),
    (1, "confirmed", "pending"), (2, "done", "unknown"),
])
def test_p2p_ui_labels_do_not_promote_primary_financial_state(status, ui_state, state):
    evidence = transaction_evidence({"type": "withdraw", "status": status}, source="p2p")
    assert evidence.ui_state == ui_state
    assert evidence.state == state and evidence.raw_status == status
    assert evidence.ui_state_source == "https://bit.team/p2p/_next/static/chunks/3812-633d8d6f222bceb0.js"
    assert evidence.tx_hash is None


@pytest.mark.parametrize("status", [True, False, "1", "2", "done", 1.0, None, {}, [], 3, -2])
def test_ui_mapping_does_not_guess_future_or_noninteger_statuses(status):
    evidence = transaction_evidence({"type": "withdraw", "status": status}, source="p2p")
    assert evidence.ui_state == "unknown"
    assert evidence.state == "unknown"
    assert evidence.ui_state_source is None


@pytest.mark.parametrize("source,row", [
    ("spot_transaction", {"type": "withdraw", "status": 1}),
    ("spot_transaction", {"type": "withdraw", "status": 2}),
    ("spot_transaction", {"type": "withdraw", "status": -1}),
    ("p2p", {"type": "deposit", "status": 2}),
    ("p2p", {"status": 2}),
])
def test_p2p_withdraw_ui_mapping_does_not_cross_source_or_record_type(source, row):
    evidence = transaction_evidence(row, source=source)
    assert evidence.ui_state == "unknown" and evidence.ui_state_source is None
    if source == "spot_transaction" and row["status"] == -1:
        assert evidence.state == "failed"


def test_existing_positional_constructor_preserves_field_order_and_new_defaults():
    raw = {"old-positional-field": True}
    evidence = TransactionEvidence("p2p", "id", "pending", 1, None, None, False, raw)
    assert evidence.raw is raw
    assert evidence.ui_state == "unknown" and evidence.ui_state_source is None


def test_raw_ui_inputs_remain_detached_and_sensitive_fields_stay_out_of_repr():
    secret = "synthetic-private-status-SECRET"
    status = {"nested": [secret]}
    row = {"type": "withdraw", "status": status, "address": secret}
    evidence = transaction_evidence(row, source="p2p")
    status["nested"].clear()
    row["address"] = "changed"
    assert evidence.raw_status == {"nested": [secret]}
    assert evidence.raw["status"] == {"nested": [secret]}
    assert evidence.raw["address"] == secret
    assert evidence.ui_state == "unknown" and secret not in repr(evidence)
