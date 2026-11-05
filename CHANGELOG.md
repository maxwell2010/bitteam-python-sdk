# Changelog

## 1.7.0 - 2026-11-05

First prepared GitHub release. The repository previously carried unpublished
version 1.6.0; no earlier release or tag was found during release preparation.

- Add explicit bounded candle recovery and L2 snapshot reconciliation. History
  and replacement streams remain separate; raw book updates are not applied.
  `continuity_guaranteed` and `events_applied` remain false.
- Guard client-owned stream/recovery lifetimes, stale auth owners and request
  generations; retain cancellation and cleanup across concurrent operations.
- Serialize login challenge steps; reject explicit device denial; preserve the
  current challenge after malformed responses and newer credentials after stale
  validation failures.
- Enforce bundled OpenAPI path constraints and whole-millisecond trade timestamps.
- Fix SQLite memory lifetime for candle storage, PostgreSQL retention/init/worker
  behavior and recorder cleanup. Recorder requires a file-backed database;
  `:memory:` is explicitly unsupported there. Add full-history retention mode.
- Support empty OHLCV DataFrames and headless returned Plotly Figures. Validate
  core-only imports without optional extras and real optional runtimes.
- Keep observed P2P legacy/body/internal-transfer contracts distinct, provide
  pure preparation/read helpers, fail closed for unknown withdrawal selectors,
  and preserve unknown financial states instead of declaring success.
- Add sanitized diagnostics, a fail-on-external-network pytest guard, bounded
  offline verification tooling and synthetic Tk checks on disposable desktops.
- Align canonical README, manifest and standalone source inventories; preserve
  historical/legacy documentation without including private service data.

### Verification and important limits

Fake/local runtime tests, isolated PostgreSQL, synthetic SQLite/Pandas/Plotly,
core-only smoke and disposable Windows Tk checks are distinct evidence. Release
wheel/sdist build and installed-environment checks must be recorded separately
from source imports. Exact release-head/main CI and asset checksums belong in
GitHub release notes; no PyPI publication is included.

No real BitTeam account, user cache, credentials, OTP delivery, trade or withdrawal
was used in this audit. General API-v2/P2P renewal, actual expiry/revocation/delivery,
server sequence/replay, atomic snapshot+delta L2, archive retention/availability,
financial finality and orderId-to-transaction identity remain unverified. Bounded
recovery cannot guarantee missing candles, completeness or an atomic handoff.
See [the factual matrix](docs/TEST_GAPS.md) and [recovery limits](bitteam_sdk/RELIABILITY.md).

### Licensing

License unspecified. No license grant or SPDX identifier is invented by this
release preparation. Public visibility is not a substitute for an explicit license.
