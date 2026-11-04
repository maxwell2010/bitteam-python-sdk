"""Local validation of withdrawal facade; no transport or network is used."""
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import SessionAuth
from bitteam_sdk.rest import BitTeamRestAPI


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [None, True, False, "NaN", "Infinity", "-Infinity", "bad", "0", "-1", Decimal("NaN")])
@pytest.mark.parametrize("network", [None, "ERC20"])
async def test_invalid_quantity_is_rejected_before_any_http(amount, network):
    rest = BitTeamRestAPI("synthetic-key", "synthetic-secret")
    rest._request = AsyncMock()
    with pytest.raises(ValueError):
        await rest.create_withdrawal("ETH", "synthetic-address", amount, network=network, currency_id=2)
    rest._request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("currency_id", [True, False, 0, -1, "2", 2.0])
async def test_invalid_currency_identifier_cannot_reach_http(currency_id):
    rest = BitTeamRestAPI("synthetic-key", "synthetic-secret")
    rest._request = AsyncMock()
    with pytest.raises(ValueError):
        await rest.create_withdrawal("ETH", "synthetic-address", "1", currency_id=currency_id)
    rest._request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("session", [False, True])
async def test_native_withdrawal_serializes_exact_decimal_as_string(session):
    rest = BitTeamRestAPI(auth=SessionAuth()) if session else BitTeamRestAPI("synthetic-key", "synthetic-secret")
    rest._request = AsyncMock(return_value={"ok": True})
    await rest.create_withdrawal("ETH", " synthetic-address ", Decimal("0.12345678901234567890123456789"), currency_id=2)
    rest._request.assert_awaited_once_with("POST", "/withdraw/create" if session else "/ccxt/withdraw", data={
        "currencyId": 2, "currency": "ETH", "to": "synthetic-address", "amount": "0.12345678901234567890123456789"})
