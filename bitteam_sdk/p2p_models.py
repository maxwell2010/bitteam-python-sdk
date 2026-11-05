"""Conservative snapshots of the observed frontend P2P read contracts.

Field names do not establish financial semantics, enabled withdrawal networks,
terminal status enums or a link to spot transaction identifiers.
"""
from dataclasses import dataclass, field

from .transactions import TransactionEvidence
from .withdrawal_tracking import WithdrawalObservation


@dataclass(frozen=True)
class P2PAccountSnapshot:
    """API-v2 account rows, not spot wallets. Nested fields remain raw."""

    accounts: tuple[dict, ...] = field(repr=False)
    user: dict | None = field(repr=False)
    total_usd: object = field(repr=False)
    raw: dict = field(repr=False)


@dataclass(frozen=True)
class P2PWithdrawalSnapshot:
    """One existing record and conservative evidence; no settlement inference."""

    observation: WithdrawalObservation = field(repr=False)
    evidence: TransactionEvidence = field(repr=False)

    @property
    def requested_identifier(self) -> str:
        return self.observation.identifier

    @property
    def record_identifier(self) -> str | None:
        return self.evidence.identifier

    @property
    def state(self) -> str:
        return self.evidence.state
