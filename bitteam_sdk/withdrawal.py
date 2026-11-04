"""Spot withdrawal network selection derived from the site's currency catalog.

P2P currency_id is a separate namespace and is never substituted here.
Preparing a payload does not submit or confirm a withdrawal.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


NETWORKS = {
    "ethereum": ("eth", "ERC-20", {"eth", "ethereum", "erc20"}),
    "tron": ("trx", "TRC-20", {"trx", "tron", "trc20"}),
    "binance": ("bnb", "BEP-20", {"bnb", "bsc", "binancesmartchain", "binance", "bep20"}),
    "binancesmartchain": ("bnb", "BEP-20", {"bnb", "bsc", "binancesmartchain", "binance", "bep20"}),
}


def network_key(value):
    return "".join(c for c in str(value).lower() if c.isalnum())


def decimal_value(value):
    if value is None:
        return None
    try:
        result = Decimal(str(value))
    except InvalidOperation:
        raise ValueError("Invalid currency limit") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Invalid currency limit")
    return result


@dataclass(frozen=True)
class WithdrawalNetwork:
    symbol: str
    currency_id: int
    network: str
    standard: str
    request_currency: str | None
    min_amount: Decimal | None
    max_amount: Decimal | None
    fixed_fee: Decimal | None
    catalog_active: bool
    aliases: frozenset
    # Only a per-account permission check can establish current availability.
    withdraw_enabled: bool | None = None


def withdrawal_networks(currencies, symbol):
    name = str(symbol).strip().lower()
    row = next((c for c in currencies if str(c.get("symbol", "")).lower() == name), None)
    if row is None:
        raise ValueError("Currency is absent from the spot catalog")
    limits = row.get("txLimits") or {}
    chains = [link.get("blockChain") for link in row.get("links", []) if link.get("blockChain")]
    if not chains and row.get("blockChain"):
        chains = [row["blockChain"]]
    if not chains:
        raise ValueError("Currency has no documented blockchain network")
    result, seen = [], set()
    for chain in chains:
        key = network_key(chain)
        if key in seen:
            continue
        seen.add(key)
        base, standard, aliases = NETWORKS.get(key, (None, str(chain), {key}))
        # Only USDT's form is confirmed to send chain.baseSymbol as currency.
        parameter = base if name == "usdt" else None
        fee = limits.get("withdrawCommissionFixed")
        if isinstance(fee, dict):
            fee = fee.get(chain)
        result.append(WithdrawalNetwork(name.upper(), int(row["id"]), str(chain), standard, parameter,
            decimal_value(limits.get("minWithdraw")), decimal_value(limits.get("maxWithdraw")),
            decimal_value(fee), bool(row.get("active")) and row.get("status") == 1,
            frozenset(aliases | {key, network_key(standard)})))
    return result


def prepare_withdrawal(currencies, symbol, *, amount, address, network=None, currency_id=None):
    choices = withdrawal_networks(currencies, symbol)
    if network is None:
        if len(choices) != 1:
            raise ValueError("This currency has multiple networks; select network explicitly")
        selected = choices[0]
    else:
        matches = [choice for choice in choices if network_key(network) in choice.aliases]
        if len(matches) != 1:
            raise ValueError("Network is not supported for this spot currency")
        selected = matches[0]
    if not selected.catalog_active:
        raise ValueError("Currency is inactive in the spot catalog")
    if currency_id is not None and currency_id != selected.currency_id:
        raise ValueError("currency_id does not match the spot currency; P2P ids are not interchangeable")
    quantity = decimal_value(amount)
    if quantity is None or quantity <= 0:
        raise ValueError("Withdrawal amount must be positive")
    if selected.min_amount is not None and quantity < selected.min_amount:
        raise ValueError("Withdrawal amount is below the catalog minimum")
    if selected.max_amount is not None and quantity > selected.max_amount:
        raise ValueError("Withdrawal amount exceeds the catalog maximum")
    if not isinstance(address, str) or not address.strip() or any(c.isspace() for c in address.strip()):
        raise ValueError("Withdrawal address must be a nonempty string without internal whitespace")
    payload = {"currencyId": selected.currency_id, "amount": format(quantity, "f"), "to": address.strip()}
    if selected.request_currency is not None:
        payload["currency"] = selected.request_currency
    return {"payload": payload, "network": selected}
