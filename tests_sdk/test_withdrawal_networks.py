"""Offline withdrawal preparation contracts; never submit a withdrawal.

USDT fixture fields match the public spot catalog observed 2026-11-03.
The P2P id belongs to a different namespace. Native ETH limits below are
synthetic bounds for validation tests, not current exchange fee guidance.
"""
from copy import deepcopy
from decimal import Decimal
import socket
import urllib.request

import aiohttp
import pytest

from bitteam_sdk.withdrawal import prepare_withdrawal, withdrawal_networks


@pytest.fixture(autouse=True)
def prohibit_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Withdrawal preparation must not initiate network activity")
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(aiohttp, "ClientSession", forbidden)


@pytest.fixture
def catalog():
    return [
        {"id": 3, "symbol": "usdt", "active": True, "status": 1,
         "txLimits": {"minWithdraw": "1", "maxWithdraw": "100000",
                      "withdrawCommissionFixed": {"Tron": "2", "Binance": "2", "Ethereum": "2"}},
         "links": [{"blockChain": "Ethereum"}, {"blockChain": "Tron"}, {"blockChain": "Binance"}]},
        {"id": 2, "symbol": "eth", "active": True, "status": 1,
         "blockChain": "Ethereum", "links": [],
         "txLimits": {"minWithdraw": "0.01", "maxWithdraw": "1000", "withdrawCommissionFixed": "0.001"}},
    ]


@pytest.mark.parametrize("alias,currency,standard", [
    ("ERC20", "eth", "ERC-20"), ("ERC-20", "eth", "ERC-20"),
    ("Ethereum", "eth", "ERC-20"), ("eth", "eth", "ERC-20"),
    ("TRC20", "trx", "TRC-20"), ("TRC-20", "trx", "TRC-20"),
    ("Tron", "trx", "TRC-20"), ("trx", "trx", "TRC-20"),
    ("BEP20", "bnb", "BEP-20"), ("BEP-20", "bnb", "BEP-20"),
    ("BSC", "bnb", "BEP-20"), ("Binance Smart Chain", "bnb", "BEP-20"),
])
def test_usdt_network_aliases_preserve_spot_id_and_use_chain_currency(catalog, alias, currency, standard):
    result = prepare_withdrawal(catalog, "USDT", amount=Decimal("1.25"), address="synthetic-address", network=alias)
    assert result["payload"] == {"currencyId": 3, "currency": currency, "amount": "1.25", "to": "synthetic-address"}
    assert result["network"].standard == standard
    assert result["network"].fixed_fee == Decimal("2")
    assert result["network"].withdraw_enabled is None


def test_usdt_requires_explicit_network(catalog):
    with pytest.raises(ValueError, match="multiple networks"):
        prepare_withdrawal(catalog, "USDT", amount="1", address="synthetic-address")


@pytest.mark.parametrize("network", ["Solana", "Polygon", "Bitcoin", "OMNI"])
def test_unsupported_usdt_network_is_rejected(catalog, network):
    with pytest.raises(ValueError, match="not supported"):
        prepare_withdrawal(catalog, "USDT", amount="1", address="synthetic-address", network=network)


def test_p2p_currency_id_cannot_replace_spot_id(catalog):
    with pytest.raises(ValueError, match="P2P"):
        prepare_withdrawal(catalog, "USDT", amount="1", address="synthetic-address", network="TRC20", currency_id=44)
    result = prepare_withdrawal(catalog, "USDT", amount="1", address="synthetic-address", network="TRC20", currency_id=3)
    assert result["payload"]["currencyId"] == 3
    assert result["payload"]["currency"] == "trx"


def test_native_eth_has_only_catalog_ethereum_and_no_invented_chain_parameter(catalog):
    choices = withdrawal_networks(catalog, "ETH")
    assert len(choices) == 1
    assert choices[0].network == "Ethereum"
    assert choices[0].request_currency is None
    result = prepare_withdrawal(catalog, "ETH", amount="1", address="synthetic-address")
    assert result["payload"] == {"currencyId": 2, "amount": "1", "to": "synthetic-address"}
    with pytest.raises(ValueError, match="not supported"):
        prepare_withdrawal(catalog, "ETH", amount="1", address="synthetic-address", network="TRC20")
    with pytest.raises(ValueError, match="not supported"):
        prepare_withdrawal(catalog, "ETH", amount="1", address="synthetic-address", network="BEP20")


@pytest.mark.parametrize("active,status", [(False, 1), (True, 0), (False, 0)])
def test_inactive_catalog_currency_is_rejected(catalog, active, status):
    catalog[0].update(active=active, status=status)
    with pytest.raises(ValueError, match="inactive"):
        prepare_withdrawal(catalog, "USDT", amount="1", address="synthetic-address", network="TRC20")


@pytest.mark.parametrize("amount", [None, "0", "-1", "0.999", "100000.01", "NaN", "Infinity", "-Infinity", "invalid", True])
def test_invalid_or_out_of_bounds_amounts_are_rejected(catalog, amount):
    with pytest.raises(ValueError):
        prepare_withdrawal(catalog, "USDT", amount=amount, address="synthetic-address", network="TRC20")


@pytest.mark.parametrize("amount", ["1", "100000"])
def test_documented_amount_bounds_are_inclusive(catalog, amount):
    result = prepare_withdrawal(catalog, "USDT", amount=amount, address="synthetic-address", network="TRC20")
    assert result["payload"]["amount"] == amount


@pytest.mark.parametrize("address", [None, "", "   ", "abc def", "abc\ndef", "abc\tdef", 123])
def test_empty_or_internally_whitespace_address_is_rejected(catalog, address):
    with pytest.raises(ValueError):
        prepare_withdrawal(catalog, "USDT", amount="1", address=address, network="TRC20")


def test_preparation_is_pure_and_does_not_modify_catalog(catalog):
    original = deepcopy(catalog)
    result = prepare_withdrawal(catalog, "USDT", amount="1.2300", address=" synthetic-address ", network="ERC20")
    assert result["payload"]["amount"] == "1.2300"
    assert result["payload"]["to"] == "synthetic-address"
    assert catalog == original
    # The autouse fixture prevents HTTP session creation, urllib and socket calls.
