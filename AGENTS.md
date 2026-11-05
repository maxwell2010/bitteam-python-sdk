# BitTeam SDK development

User requirements:
- Continue implementation and fix reproducible errors; distinguish offline contracts from actual live verification.
- Release authorization (2026-11-05) supersedes the earlier verification freeze: version/changelog changes, isolated wheel/sdist/source builds and install checks, PR #1 merge after checks, tag and GitHub release with reviewed public assets are authorized. No PyPI publishing or Telegram sending. Never bypass network/approval/security denials.
- Publish only after concrete blockers are resolved, exact-head PR checks and main checks pass, artifacts/installs are inspected and notes preserve external limitations. Do not invent a license; currently unspecified.
- Public repository: never commit credentials, cookies, session caches, account responses, databases, logs or legacy service config files.
- Never perform real trades, withdrawals, financial confirmations, send verification codes, or change account settings during tests. Synthetic tests are authorized.
- Real account sessions were removed locally at the user's request. Never reconstruct or upload them.
- Use Russian for user-facing progress; use short hyphens.

Validation:
python -m pip install -r requirements-sdk-dev.txt
python -m pytest -c tests_sdk/pytest.ini tests_sdk -ra --junitxml=sdk-test-results.xml
python scripts_sdk/check_test_skips.py sdk-test-results.xml

Read docs/TEST_GAPS.md, bitteam_sdk/RELIABILITY.md and bitteam_sdk/WITHDRAWAL_TRACKING.md before claiming full coverage. Linux/3.13 jobs must be verified in GitHub CI. Cloud cannot use Windows DPAPI cache. Do not claim unknown transaction statuses as success or assume orderId equals transaction ID.
