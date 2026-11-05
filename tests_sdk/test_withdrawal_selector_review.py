"""Pure spot selector regressions; catalog visibility is not dispatch evidence."""
from copy import deepcopy

import pytest

from bitteam_sdk.withdrawal import prepare_withdrawal, withdrawal_networks


def catalog(symbol, chains):
    return [{"id": 3 if symbol == "usdt" else 17, "symbol": symbol,
             "active": True, "status": 1,
             "txLimits": {"minWithdraw": "1", "maxWithdraw": "100"},
             "links": [{"blockChain": chain} for chain in chains]}]


@pytest.mark.parametrize("chains", [["Ethereum", "Arbitrum"], ["Arbitrum"]])
def test_visible_unknown_usdt_chain_cannot_produce_a_selectorless_plan(chains):
    currencies = catalog("usdt", chains)
    before = deepcopy(currencies)
    choices = withdrawal_networks(currencies, "USDT")
    unknown = next(choice for choice in choices if choice.network == "Arbitrum")
    assert unknown.request_currency is None and unknown.withdraw_enabled is None
    with pytest.raises(ValueError, match="selector"):
        prepare_withdrawal(currencies, "USDT", amount="2", address="synthetic", network="Arbitrum")
    assert currencies == before


@pytest.mark.parametrize("network", ["Ethereum", "Arbitrum"])
def test_nonusdt_multinetwork_choices_cannot_create_indistinguishable_payloads(network):
    currencies = catalog("synthetic", ["Ethereum", "Arbitrum"])
    choices = withdrawal_networks(currencies, "SYNTHETIC")
    assert len(choices) == 2 and {choice.currency_id for choice in choices} == {17}
    assert all(choice.request_currency is None for choice in choices)
    with pytest.raises(ValueError, match="selector"):
        prepare_withdrawal(currencies, "SYNTHETIC", amount="2", address="synthetic", network=network)


@pytest.mark.parametrize("network,selector", [("Ethereum", "eth"), ("Tron", "trx"), ("Binance", "bnb")])
def test_verified_usdt_selectors_remain_distinct_when_unknown_metadata_is_visible(network, selector):
    currencies = catalog("usdt", ["Ethereum", "Tron", "Binance", "Arbitrum"])
    plan = prepare_withdrawal(currencies, "USDT", amount="2", address="synthetic", network=network)
    assert plan["payload"] == {"currencyId": 3, "amount": "2", "to": "synthetic", "currency": selector}
    assert plan["network"].network == network


@pytest.mark.parametrize("explicit", [False, True])
def test_single_native_currency_retains_currency_id_without_inventing_selector(explicit):
    currencies = catalog("eth", ["Ethereum"])
    plan = prepare_withdrawal(currencies, "ETH", amount="2", address="synthetic",
                              **({"network": "Ethereum"} if explicit else {}))
    assert plan["payload"] == {"currencyId": 17, "amount": "2", "to": "synthetic"}
    assert plan["network"].request_currency is None
