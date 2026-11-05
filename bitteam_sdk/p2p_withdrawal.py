"""Pure preparation of the observed standard P2P withdrawal form body.

Evidence was supplied by the user's public-static-GET coordinator, not fetched
by this cloud run: Withdraw-56b2a70d301a037a.js (41423 bytes), SHA256
cbffa511c29dcfeba14c4fa5f7c24a4b3dc47a4ab75761dd3e51745b246eee86,
form defaults at offset 16625 and selected currency_id at offset 21434.
The saved chunk6034-f2e976244927be8e.js function Z, approximately offset 5295,
branches currency_id=95 to a different endpoint; the form adds date/hash
using an algorithm not established here.
No account request or financial outcome is established by that evidence.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re


@dataclass(frozen=True)
class P2PWithdrawalPlan:
    """Detached request body only; it neither submits nor estimates fees.

    Payload is excluded from repr. Its nested values are not immutable. The
    operation is explicit metadata, not an instruction to execute the plan.
    """

    payload: dict = field(repr=False)
    operation: str = field(default="create_withdrawal_body", init=False)


@dataclass(frozen=True)
class P2PInternalTransferPlan:
    """Pure internal-stock request body, without a result or execution promise."""

    payload: dict = field(repr=False)
    operation: str = field(default="create_internal_stock_transfer", init=False)


def _positive_currency_id(currency_id):
    if isinstance(currency_id, bool) or not isinstance(currency_id, int) or currency_id <= 0:
        raise ValueError("P2P currency_id must be a positive integer")


def _positive_amount_text(amount):
    if not isinstance(amount, str) or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", amount) is None:
        raise ValueError("P2P withdrawal amount must be a positive plain decimal string")
    try:
        quantity = Decimal(amount)
    except InvalidOperation:
        raise ValueError("P2P withdrawal amount must be positive and finite") from None
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("P2P withdrawal amount must be positive and finite")


def prepare_p2p_withdrawal(currency_id, *, address, amount, public="", comment="",
                           label="", commission_booster_name=None):
    """Prepare the confirmed standard body without HTTP or account access.

    Local input policy (not a proven server schema): a positive integer currency
    ID other than 95, a nonblank address, string comment/label, and a positive
    finite amount in plain ASCII decimal notation. Amount text is preserved
    exactly; no floating-point conversion, rounding or balance/fee math occurs.
    Address/network validity is not inferred. ``public`` and
    ``commission_booster_name`` are opaque caller values copied unchanged;
    their types, meanings and supported options are not guessed.

    Currency 95 is intentionally unsupported: its frontend branch adds date/hash using an
    algorithm that has not been established. Use separately verified
    raw contracts for that route; this function never substitutes the standard
    endpoint, computes a hash, sends codes, confirms or polls a withdrawal.
    """
    _positive_currency_id(currency_id)
    if currency_id == 95:
        raise ValueError("P2P currency 95 requires an unverified date/hash contract")
    if not isinstance(address, str) or not address.strip():
        raise ValueError("P2P withdrawal address must be a nonblank string")
    if not isinstance(comment, str) or not isinstance(label, str):
        raise ValueError("P2P withdrawal comment and label must be strings")
    _positive_amount_text(amount)
    return P2PWithdrawalPlan(deepcopy({
        "address": address,
        "public": public,
        "comment": comment,
        "label": label,
        "sum": amount,
        "commission_booster_name": commission_booster_name,
        "currency_id": currency_id,
    }))


def prepare_p2p_internal_transfer(currency_id, amount):
    """Prepare the separately observed internal-stock transfer body; no HTTP.

    Primary-source evidence was relayed by the user's public-RAM-GET
    coordinator, not fetched here: manifest-linked
    https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/SpotAssetsTransfer-370f165e27881048.js
    SHA256 f201f8530c9b0e65ecb5269f261d1e543c0b7b0e0881c0391b7ab8ed495efe28,
    offset 16015. The supplied callsite posts currency_id, sum and literal
    internal_request=true to /account/create-withdraw-to-stock. It consumes no
    response fields. No response id, confirmation or financial outcome is
    inferred, and no address, date, hash or code is generated.

    Local policy: positive integer currency_id and positive finite plain ASCII
    decimal amount string, preserved exactly. This distinct callsite is not
    restricted to 95; accepting an ID does not establish currency availability,
    account eligibility or a link to spot currency/transaction identifiers.
    The separate currency-95 withdrawal form still needs its unproven date/hash.
    """
    _positive_currency_id(currency_id)
    _positive_amount_text(amount)
    return P2PInternalTransferPlan({"currency_id": currency_id, "sum": amount,
                                    "internal_request": True})
