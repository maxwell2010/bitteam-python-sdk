"""Independent probe regressions. Fake clients only, no network or OS cache."""
import json
from types import SimpleNamespace

import pytest

from bitteam_sdk import BitTeamAPIError
from bitteam_sdk.account_check import balance_shape, run_check


class FakeAuth:
    def __init__(self):
        self.cache = SimpleNamespace(exists=True)
        self._access = "synthetic-private-access"
        self._refresh = "synthetic-private-refresh"
        self.generation = 1
        self.saves = 0

    def save_session(self):
        self.saves += 1


class FakeClient:
    def __init__(self, *, resume_error=None, close_error=None):
        self.auth = FakeAuth()
        self.rest = SimpleNamespace(_send=self.no_network, _session=None)
        self.resume_error = resume_error
        self.close_error = close_error
        self.logout_calls = 0
        self.close_calls = 0

    async def no_network(self, *args, **kwargs):
        raise AssertionError("Probe regression tests must not use a transport")

    async def resume_session(self):
        if self.resume_error is not None:
            raise self.resume_error
        return True

    async def get_balance(self):
        return {"ok": True, "result": {"balance": {}}}

    async def refresh(self):
        self.auth._access = "synthetic-private-new-access"
        self.auth._refresh = "synthetic-private-new-refresh"
        self.auth.generation += 1

    async def logout(self):
        self.logout_calls += 1
        self.auth.cache.exists = False

    async def close(self):
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


async def forbidden_prompt(*args, **kwargs):
    raise AssertionError("Restored-session tests must not request credentials")


@pytest.mark.asyncio
async def test_keep_session_preserves_cache_after_resume_503(tmp_path):
    client = FakeClient(resume_error=BitTeamAPIError(503))
    path = tmp_path / "report.json"

    result = await run_check(path, client=client, prompt=forbidden_prompt, keep_session=True)

    assert result is False
    assert client.logout_calls == 0
    assert client.auth.cache.exists is True
    assert client.close_calls == 1
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["status"] == "incomplete"
    assert report["finished_at_utc"]


@pytest.mark.parametrize("result", [None, [], "not a balance", False, 0])
def test_balance_probe_rejects_non_dictionary_result(result):
    with pytest.raises(ValueError):
        balance_shape({"ok": True, "result": result})


def test_empty_dictionary_balance_remains_valid():
    assert balance_shape({"ok": True, "result": {}}) == {"response_type": "dict"}


@pytest.mark.asyncio
async def test_close_failure_finalizes_report_without_exception_or_secret(tmp_path, capsys):
    secret = "synthetic-password-must-not-appear"
    client = FakeClient(close_error=OSError(secret))
    path = tmp_path / "report.json"

    result = await run_check(path, client=client, prompt=forbidden_prompt)

    assert result is False
    assert client.close_calls == 1
    report_text = path.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["status"] == "incomplete"
    assert report["finished_at_utc"]
    output = capsys.readouterr()
    for value in (secret, "synthetic-private-access", "synthetic-private-refresh"):
        assert value not in report_text
        assert value not in output.out
        assert value not in output.err
