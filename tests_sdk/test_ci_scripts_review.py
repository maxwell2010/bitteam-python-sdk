"""Offline CLI regressions; no package builds or pip installation occurs."""
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest


def load_script(name):
    source = Path(__file__).resolve().parents[1] / "scripts_sdk" / (name + ".py")
    spec = importlib.util.spec_from_file_location("sdk_review_" + name, source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("count", [0, 2])
def test_wheel_smoke_rejects_missing_or_ambiguous_wheels_before_pip(tmp_path, monkeypatch, count):
    script = load_script("check_wheel")
    for i in range(count):
        (tmp_path / f"fake-{i}.whl").touch()
    runner = Mock()
    monkeypatch.setattr(script.subprocess, "run", runner)
    monkeypatch.setattr(script.sys, "argv", ["check_wheel", "--dist-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        script.main()
    assert error.value.code == 2
    runner.assert_not_called()


def test_wheel_install_isolated_from_pip_environment_and_source_checkout(tmp_path, monkeypatch):
    script = load_script("check_wheel")
    wheel = tmp_path / "fake.whl"
    wheel.touch()
    runner = Mock()
    builder = Mock()
    monkeypatch.setenv("PIP_TARGET", str(tmp_path / "must-not-be-used"))
    monkeypatch.setattr(script.venv, "EnvBuilder", Mock(return_value=builder))
    monkeypatch.setattr(script.subprocess, "run", runner)
    monkeypatch.setattr(script.sys, "argv", ["check_wheel", "--wheel", str(wheel)])
    script.main()
    install, smoke = runner.call_args_list
    assert install.args[0][1:] == ["-I", "-m", "pip", "--isolated", "install", str(wheel)]
    assert smoke.args[0][1] == "-I" and smoke.args[0][-1] == "--installed"
    assert install.kwargs["cwd"] == smoke.kwargs["cwd"]
    assert install.kwargs["check"] and smoke.kwargs["check"]
    assert not (tmp_path / "must-not-be-used").exists()


@pytest.mark.parametrize("platform,classname,name,allowed", [
    ("linux", "tests_sdk.test_session_cache", "test_real_windows_dpapi_roundtrip_and_integrity", True),
    ("win32", "tests_sdk.test_session_cache", "test_real_windows_dpapi_roundtrip_and_integrity", False),
    ("linux", "tests_sdk.test_site_api", "some_portable_test", False),
    ("linux", "tests_sdk.test_site_api", "test_real_windows_dpapi_roundtrip_and_integrity", False),
])
def test_skip_audit_does_not_hide_portability_failures(tmp_path, platform, classname, name, allowed):
    script = load_script("check_test_skips")
    report = tmp_path / "junit.xml"
    report.write_text(f'<testsuites><testsuite><testcase classname="{classname}" name="{name}"><skipped /></testcase></testsuite></testsuites>')
    if allowed:
        script.check_report(report, platform=platform)
    else:
        with pytest.raises(ValueError, match="Unexpected skipped"):
            script.check_report(report, platform=platform)


def test_skip_audit_rejects_empty_report(tmp_path):
    script = load_script("check_test_skips")
    report = tmp_path / "junit.xml"
    report.write_text("<testsuites />")
    with pytest.raises(ValueError, match="no test cases"):
        script.check_report(report)
