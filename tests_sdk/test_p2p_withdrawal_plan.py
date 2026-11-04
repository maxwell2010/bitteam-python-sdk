"""Pure synthetic form preparation. No exchange calls or secret material."""
from decimal import Inexact, Rounded, localcontext

import pytest

from bitteam_sdk.p2p_withdrawal import P2PWithdrawalPlan, prepare_p2p_withdrawal


def test_standard_plan_matches_observed_form_fields_and_body_currency_id():
    plan = prepare_p2p_withdrawal(7, address="synthetic-destination", amount="001.230000000000000000001")
    assert isinstance(plan, P2PWithdrawalPlan)
    assert plan.operation == "create_withdrawal_body"
    assert plan.payload == {
        "address": "synthetic-destination", "public": "", "comment": "", "label": "",
        "sum": "001.230000000000000000001", "commission_booster_name": None,
        "currency_id": 7,
    }
    assert "date" not in plan.payload and "hash" not in plan.payload


def test_amount_is_exact_and_independent_of_application_decimal_context():
    amount = "1234567890123456789012345678901234567890.000000000000000000000000000001"
    with localcontext() as context:
        context.prec, context.Emax, context.Emin = 2, 9, -9
        context.traps[Inexact] = context.traps[Rounded] = True
        plan = prepare_p2p_withdrawal(7, address="synthetic", amount=amount)
    assert plan.payload["sum"] == amount


@pytest.mark.parametrize("public,booster", [
    ("opaque-public-value", "raw-booster"),
    (None, None),
    ({"caller-supplied": ["raw"]}, {"unverified-option": ["raw"]}),
    (False, 0),
])
def test_optional_public_and_commission_values_are_opaque_and_detached(public, booster):
    plan = prepare_p2p_withdrawal(7, address="synthetic", amount="0.00000001",
        public=public, commission_booster_name=booster)
    assert plan.payload["public"] == public
    assert plan.payload["commission_booster_name"] == booster
    if isinstance(public, dict):
        public["caller-supplied"].clear()
        booster["unverified-option"].clear()
        assert plan.payload["public"] == {"caller-supplied": ["raw"]}
        assert plan.payload["commission_booster_name"] == {"unverified-option": ["raw"]}


def test_inputs_and_plan_repr_do_not_disclose_destination_or_form_values():
    secret = "synthetic-private-SECRET"
    plan = prepare_p2p_withdrawal(7, address=secret, amount="1.000", public=secret,
                                comment=secret, label=secret, commission_booster_name=secret)
    assert secret not in repr(plan)
    assert plan.payload["address"] == secret
    assert plan.payload["comment"] == plan.payload["label"] == secret


@pytest.mark.parametrize("currency_id", [95, True, False, None, "7", 0, -1, 7.0])
def test_unsupported_currency_and_noninteger_ids_fail_before_preparing_plan(currency_id):
    with pytest.raises(ValueError):
        prepare_p2p_withdrawal(currency_id, address="synthetic", amount="1")


def test_currency95_does_not_offer_a_standard_route_or_invent_hash():
    with pytest.raises(ValueError, match="95.*date/hash"):
        prepare_p2p_withdrawal(95, address="synthetic", amount="1")


@pytest.mark.parametrize("amount", [None, True, 1, 1.5, "", "0", "0.000", "-1", "NaN",
    "Infinity", "1e2", " 1", "1 ", "1_000", "１", ".1", "1.", "+1"])
def test_local_decimal_input_policy_is_explicit_without_numeric_coercion(amount):
    with pytest.raises(ValueError):
        prepare_p2p_withdrawal(7, address="synthetic", amount=amount)


@pytest.mark.parametrize("address", [None, True, 4, "", " \t"])
def test_blank_or_nonstring_destination_fails_without_network_assumptions(address):
    with pytest.raises(ValueError):
        prepare_p2p_withdrawal(7, address=address, amount="1")


@pytest.mark.parametrize("field", ["comment", "label"])
def test_form_text_fields_have_local_string_policy(field):
    with pytest.raises(ValueError):
        prepare_p2p_withdrawal(7, address="synthetic", amount="1", **{field: None})


def test_planner_does_not_normalize_or_validate_an_unverified_address_network():
    address = " caller-supplied opaque destination "
    plan = prepare_p2p_withdrawal(7, address=address, amount="1")
    assert plan.payload["address"] == address
