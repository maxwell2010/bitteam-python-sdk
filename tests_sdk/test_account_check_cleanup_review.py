"""RAM-only diagnostics failures must not strand the account-check transport."""
import asyncio
from types import SimpleNamespace

import pytest

from bitteam_sdk import AuthState, LoginResult
from bitteam_sdk.account_check import AccountCheck, run_check


class Client:
    def __init__(self, *, keep=False, cleanup_error=None):
        self.cleanup_error = cleanup_error
        self.closed = False
        self.auth = SimpleNamespace(
            cache=SimpleNamespace(exists=True) if keep else None,
            _access="synthetic", _refresh="synthetic", generation=0,
            save_session=self.save_session,
        )
        self.rest = SimpleNamespace(_send=None, _session=None)

    def save_session(self):
        if self.cleanup_error:
            raise self.cleanup_error

    async def resume_session(self):
        return True

    async def login(self, *args):
        return LoginResult(AuthState.READY)

    async def get_balance(self):
        return {"result": {}}

    async def refresh(self):
        self.auth.generation += 1

    async def logout(self):
        if self.cleanup_error:
            raise self.cleanup_error

    async def close(self):
        self.closed = True


async def prompt(*args, **kwargs):
    return "synthetic"


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
async def test_cleanup_diagnostics_failure_still_closes_transport(monkeypatch, keep):
    client = Client(keep=keep)
    reports = []

    def save(check):
        reports.append(check.report["status"])
        if any(step["step"] in {"session_cleanup", "encrypted_session_cache"}
               for step in check.report["steps"]):
            raise OSError("synthetic diagnostics failure")

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(OSError, match="synthetic diagnostics failure"):
        await run_check("unused-RAM-only", client=client, prompt=prompt, keep_session=keep)
    assert client.closed
    assert reports[-1] == "incomplete"


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
async def test_cleanup_original_failure_survives_broken_diagnostics(monkeypatch, keep):
    original = OSError("synthetic original cleanup failure")
    client = Client(keep=keep, cleanup_error=original)

    def save(check):
        if any(step["step"] == "session_cleanup" for step in check.report["steps"]):
            raise OSError("secondary diagnostic failure")

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(OSError) as caught:
        await run_check("unused-RAM-only", client=client, prompt=prompt, keep_session=keep)
    assert caught.value is original
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
async def test_cleanup_cancellation_survives_final_diagnostics_failure(monkeypatch, keep):
    cancellation = asyncio.CancelledError("synthetic cancellation")
    client = Client(keep=keep, cleanup_error=cancellation)

    def save(check):
        if "finished_at_utc" in check.report:
            raise OSError("secondary diagnostic failure")

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(asyncio.CancelledError) as caught:
        await run_check("unused-RAM-only", client=client, prompt=prompt, keep_session=keep)
    assert caught.value is cancellation
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
@pytest.mark.parametrize("broken_diagnostics", [False, True])
async def test_body_cancellation_is_not_swallowed_or_masked(monkeypatch, keep, broken_diagnostics):
    cancellation = asyncio.CancelledError("synthetic body cancellation")
    client = Client(keep=keep, cleanup_error=OSError("secondary cleanup failure"))

    async def balance():
        raise cancellation

    client.get_balance = balance
    reports = []

    def save(check):
        reports.append(check.report["status"])
        if broken_diagnostics and any(step["step"] == "check" for step in check.report["steps"]):
            raise OSError("secondary diagnostic failure")

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(asyncio.CancelledError) as caught:
        await run_check("unused-RAM-only", client=client, prompt=prompt, keep_session=keep)
    assert caught.value is cancellation
    assert client.closed
    assert reports[-1] == "incomplete"


@pytest.mark.asyncio
async def test_body_failure_is_preserved_when_failure_reporting_also_fails(monkeypatch):
    original = ValueError("synthetic body failure")
    client = Client(cleanup_error=OSError("secondary cleanup failure"))

    async def balance():
        raise original

    client.get_balance = balance

    def save(check):
        if any(step["step"] == "check" for step in check.report["steps"]):
            raise OSError("secondary diagnostic failure")

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(ValueError) as caught:
        await run_check("unused-RAM-only", client=client, prompt=prompt)
    assert caught.value is original
    assert client.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("keep", [False, True])
async def test_initial_report_failure_still_closes_existing_transport(monkeypatch, keep):
    original = OSError("synthetic initial report failure")
    client = Client(keep=keep)
    reports = []

    def save(check):
        reports.append(check.report["status"])
        raise original

    monkeypatch.setattr(AccountCheck, "save", save)
    with pytest.raises(OSError) as caught:
        await run_check("unused-RAM-only", client=client, prompt=prompt, keep_session=keep)
    assert caught.value is original
    assert client.closed
    assert reports[-1] == "incomplete"
