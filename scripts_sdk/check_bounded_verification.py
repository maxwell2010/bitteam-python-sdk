"""Plan by default; optionally run a fixed, bounded offline regression selection.

No live, profile, account or financial execution mode exists. Offline results
verify fake/local orchestration, not backend availability or financial outcomes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys


TEST_FILES = (
    'tests_sdk/test_history_owner_close_review.py',
    'tests_sdk/test_book_owner_lifecycle_review.py',
    'tests_sdk/test_resume_generation_review.py',
    'tests_sdk/test_recorder_cleanup_review.py',
    'tests_sdk/test_path_schema_review.py',
    'tests_sdk/test_service_timestamp_review.py',
    'tests_sdk/test_auth_step_serialization.py',
    'tests_sdk/test_relogin_refresh_review.py',
    'tests_sdk/test_history_backfill_review.py',
)
TIMEOUT = 60


def plan():
    return {
        'status': 'not_executed', 'max_requests': 0,
        'offline': {'command': '--offline', 'timeout_seconds': TIMEOUT, 'test_files': list(TEST_FILES),
                    'evidence': 'fake/local only; no backend proof'},
        'external_blockers': [
            {'case': 'account_expiry_renewal_revocation', 'requires': 'explicit account authorization and synthetic test account; no profile mode provided'},
            {'case': 'ordered_snapshot_delta_recovery', 'requires': 'primary server sequence/replay contract; local tests cannot establish server ordering'},
            {'case': 'archive_availability_retention', 'requires': 'separately authorized public availability probe and documented bounds; no retention guarantee'},
            {'case': 'financial_outcomes_id_links', 'requires': 'verified primary contract and separate financial-operation authorization; no financial mode provided'},
        ],
        'future_public_plan': {
            'status': 'not_executed', 'requires': 'separate authorization and available public service',
            'methods': ['get_orderbook_snapshot', 'get_klines'],
            'max_calls': 2, 'deadline_seconds_per_call': 8, 'max_events': 0,
            'limits': 'No cookies, profiles or auth; no replay, completeness or retention conclusion. Execution is not implemented here.',
        },
    }


def offline():
    root = Path(__file__).absolute().parents[1]
    arguments = ['-c', 'tests_sdk/pytest.ini', '-q', '-p', 'no:cacheprovider', *TEST_FILES]
    bootstrap = ('import sys; sys.path.insert(0, ' + repr(str(root)) + '); '
                 'import pytest; raise SystemExit(pytest.main(' + repr(arguments) + '))')
    command = [sys.executable, '-I', '-B', '-c', bootstrap]
    try:
        result = subprocess.run(command, cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=TIMEOUT)
        status = 'passed' if result.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired:
        status = 'timed_out'
    except Exception:
        status = 'failed'
    # Child stdout/stderr and exception messages are deliberately not exported.
    return {'status': status, 'mode': 'offline', 'timeout_seconds': TIMEOUT,
            'test_files': list(TEST_FILES), 'evidence': 'fake/local only; no backend proof',
            'network_boundary': 'per-test Python socket guard; not collection/subprocess/native-I/O firewall'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true', help='Run only the fixed offline test selection, with a 60-second deadline')
    args = parser.parse_args(argv)
    result = offline() if args.offline else plan()
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] in ('not_executed', 'passed') else 1


if __name__ == '__main__':
    raise SystemExit(main())
