"""Conservative inspection of transaction fields observed in the official UI."""
from copy import deepcopy
from dataclasses import dataclass, field


# Primary-source UI trace supplied by the user's RAM-only coordinator, not
# fetched or rehashed by this cloud run. Shared chunk offset 6723 explicitly
# switches withdraw labels -1/0/1/2 to canceled/created/confirmed/done, with a
# raw-status default. These labels are not an exhaustive backend status enum.
P2P_WITHDRAW_UI_SOURCE = "https://bit.team/p2p/_next/static/chunks/3812-633d8d6f222bceb0.js"
P2P_WITHDRAW_UI_SOURCE_SHA256 = "2c0957ed01c7bfd933ba10d0bba968fafb5802f81872c2f9205768b6a0b20107"


@dataclass(frozen=True)
class TransactionEvidence:
    source: str
    identifier: str | None
    state: str
    # UI state is evidence only; it never proves settlement or network finality.
    raw_status: object = field(repr=False)
    tx_hash: str | None = field(default=None, repr=False)
    blockchain: str | None = None
    internal_transfer: bool = False
    raw: dict = field(default_factory=dict, repr=False)
    # Display labels only: confirmed/done never promote state or prove finality.
    ui_state: str = "unknown"
    ui_state_source: str | None = None


def transaction_evidence(row, *, source):
    if not isinstance(row, dict):
        raise ValueError("Transaction must be an object")
    if source not in ("spot_transaction", "p2p"):
        raise ValueError("Unknown transaction source")
    status = row.get("status")
    state = "unknown"
    ui_state, ui_state_source = "unknown", None
    # Do not copy the UI's default-success branch for unknown server values.
    if type(status) is int:
        if source == "p2p" and row.get("type") == "withdraw":
            state = {-1: "cancelled", 0: "created", 1: "pending"}.get(status, "unknown")
            ui_state = {-1: "cancelled", 0: "created", 1: "confirmed", 2: "done"}.get(status, "unknown")
            if ui_state != "unknown":
                ui_state_source = P2P_WITHDRAW_UI_SOURCE
        elif source == "spot_transaction":
            state = {-1: "failed", 0: "pending"}.get(status, "unknown")
    params = row.get("params")
    params = params if isinstance(params, dict) else {}
    internal = bool(params.get("internalTransfer")) if source == "spot_transaction" else False
    tx_hash = params.get("tx_id") if source == "spot_transaction" and not internal else None
    if not isinstance(tx_hash, str) or not tx_hash.strip():
        tx_hash = None
    chain = (row.get("blockChain") or params.get("blockChain")) if source == "spot_transaction" else None
    chain = chain if isinstance(chain, str) else None
    identifier = row.get("id")
    identifier = str(identifier) if isinstance(identifier, (str, int)) and not isinstance(identifier, bool) else None
    return TransactionEvidence(source, identifier, state, deepcopy(status), tx_hash, chain, internal, deepcopy(row),
                               ui_state=ui_state, ui_state_source=ui_state_source)
