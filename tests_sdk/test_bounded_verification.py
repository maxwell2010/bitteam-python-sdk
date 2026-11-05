"""The bounded harness has no live/profile execution path or raw diagnostics."""
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
SECRET = 'SYNTHETIC-driver-secret-never-export'


def load():
    spec = importlib.util.spec_from_file_location('bounded_verification', ROOT / 'scripts_sdk/check_bounded_verification.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_plan_never_starts_child_or_account_io(monkeypatch, capsys):
    module = load()
    def forbidden(*args, **kwargs): raise AssertionError('No execution in plan mode')
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    assert module.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'not_executed' and result['max_requests'] == 0
    assert result['future_public_plan']['status'] == 'not_executed'
    assert result['future_public_plan']['max_calls'] == 2


@pytest.mark.parametrize('mode,status,exit_code', [('success', 'passed', 0), ('failed', 'failed', 1), ('timeout', 'timed_out', 1), ('setup_error', 'failed', 1)])
def test_offline_is_fixed_bounded_and_sanitized(monkeypatch, capsys, mode, status, exit_code):
    module = load()
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        if mode == 'timeout': raise subprocess.TimeoutExpired(command, 60, output=SECRET, stderr=SECRET)
        if mode == 'setup_error': raise OSError(SECRET)
        return SimpleNamespace(returncode=0 if mode == 'success' else 1, stdout=SECRET, stderr=SECRET)
    monkeypatch.setattr(module.subprocess, 'run', run)
    assert module.main(['--offline']) == exit_code
    output = capsys.readouterr()
    assert SECRET not in output.out + output.err
    result = json.loads(output.out)
    assert result['status'] == status and result['mode'] == 'offline'
    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command[1:4] == ['-I', '-B', '-c']
    assert "sys.path.insert(0," in command[4]
    assert "'no:cacheprovider'" in command[4]
    assert kwargs == {'cwd': ROOT, 'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL, 'timeout': 60}
    for name in module.TEST_FILES:
        assert name in command[4] and (ROOT / name).is_file()


@pytest.mark.parametrize('argument', ['--live', '--account-profile', '--financial'])
def test_no_external_execution_mode(argument):
    with pytest.raises(SystemExit) as error:
        load().main([argument])
    assert error.value.code == 2
