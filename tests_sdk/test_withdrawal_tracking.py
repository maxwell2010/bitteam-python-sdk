"""Independent withdrawal polling regressions: synthetic reads, no transport."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bitteam_sdk import BitTeamAPIError
from bitteam_sdk.services import ServiceMethods
from bitteam_sdk.withdrawal_tracking import WithdrawalObservation, WithdrawalWaitTimeout


class ReadOnlyClient(ServiceMethods):
    def __init__(self):
        self._closed = False
        self.p2p = SimpleNamespace(get_withdrawal=AsyncMock(return_value={"data": {"phase": "pending"}}))
        self.api = SimpleNamespace(get_transaction_by_id=AsyncMock(return_value={"result": {"phase": "pending"}}))
        self._require_ready = Mock()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["p2p", "spot_transaction"])
async def test_routes_only_existing_record_reads_and_copies_payload(source):
    client = ReadOnlyClient()
    record = await client.get_withdrawal_record("existing-41", source=source)
    assert isinstance(record, WithdrawalObservation)
    assert record.identifier == "existing-41" and record.source == source
    assert record.received_at > 0
    if source == "p2p":
        client.p2p.get_withdrawal.assert_awaited_once_with(path={"withdraw_id": "existing-41"})
        client.api.get_transaction_by_id.assert_not_awaited()
        client._require_ready.assert_not_called()
        raw = client.p2p.get_withdrawal.return_value
    else:
        client.api.get_transaction_by_id.assert_awaited_once_with("existing-41")
        client.p2p.get_withdrawal.assert_not_awaited()
        client._require_ready.assert_called_once_with()
        raw = client.api.get_transaction_by_id.return_value
    assert record.payload == raw and record.payload is not raw
    next(iter(raw.values()))["phase"] = "changed"
    assert "changed" not in repr(record.payload)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", [None, "spot", "orderId", "p2p/../spot", ""])
async def test_unknown_sources_never_fall_back(source):
    client = ReadOnlyClient()
    with pytest.raises(ValueError):
        await client.get_withdrawal_record("existing-id", source=source)
    client.p2p.get_withdrawal.assert_not_awaited()
    client.api.get_transaction_by_id.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", [None, 4, "", "  ", {}, True])
async def test_existing_identifier_required(identifier):
    client = ReadOnlyClient()
    with pytest.raises(ValueError):
        await client.wait_for_withdrawal(identifier, source="p2p", predicate=lambda _: True)
    client.p2p.get_withdrawal.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["p2p", "spot_transaction"])
async def test_closed_guard_before_read(source):
    client = ReadOnlyClient()
    client._closed = True
    with pytest.raises(RuntimeError, match="closed"):
        await client.wait_for_withdrawal("id", source=source, predicate=lambda _: True)
    client.p2p.get_withdrawal.assert_not_awaited()
    client.api.get_transaction_by_id.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name,value", [
    (name, value) for name in ("timeout", "interval")
    for value in (0, -1, True, "1", None, float("inf"), float("nan"))
] + [("max_requests", value) for value in (0, -1, 10001, True, 1.5, "2")])
async def test_bounds_fail_before_any_request(name, value):
    client = ReadOnlyClient()
    with pytest.raises(ValueError):
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: True, **{name: value})
    client.p2p.get_withdrawal.assert_not_awaited()


@pytest.mark.asyncio
async def test_returns_only_when_explicit_predicate_matches_without_mutations():
    client = ReadOnlyClient()
    client.p2p.get_withdrawal.side_effect = [{"phase": "a"}, {"phase": "b"}, {"phase": "caller-done"}]
    seen = []
    def complete(record):
        seen.append(record)
        return record.payload["phase"] == "caller-done"
    record = await client.wait_for_withdrawal("id", source="p2p", predicate=complete,
                                              timeout=1, interval=0.001, max_requests=3)
    assert record is seen[-1] and len(seen) == 3
    assert client.p2p.get_withdrawal.await_count == 3
    client.api.get_transaction_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_limit_exposes_last_observation_without_extra_request():
    client = ReadOnlyClient()
    with pytest.raises(WithdrawalWaitTimeout) as error:
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False,
                                         timeout=1, interval=0.001, max_requests=2)
    assert client.p2p.get_withdrawal.await_count == 2
    assert error.value.last_observation.payload == {"data": {"phase": "pending"}}


@pytest.mark.asyncio
async def test_deadline_cancels_and_awaits_pending_read():
    client = ReadOnlyClient()
    cancelled = asyncio.Event()
    async def pending(**kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    client.p2p.get_withdrawal.side_effect = pending
    with pytest.raises(WithdrawalWaitTimeout) as error:
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False,
                                         timeout=0.01, interval=1)
    assert cancelled.is_set()
    assert error.value.last_observation is None
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
async def test_deadline_while_sleeping_keeps_last_read():
    client = ReadOnlyClient()
    with pytest.raises(WithdrawalWaitTimeout) as error:
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False,
                                         timeout=0.01, interval=1)
    assert error.value.last_observation is not None
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
async def test_external_cancellation_cleans_pending_read():
    client = ReadOnlyClient()
    started, stopped = asyncio.Event(), asyncio.Event()
    async def pending(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    client.p2p.get_withdrawal.side_effect = pending
    task = asyncio.create_task(client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False))
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stopped.is_set()
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
async def test_api_error_propagates_same_instance_without_retry():
    client = ReadOnlyClient()
    problem = BitTeamAPIError(503)
    client.p2p.get_withdrawal.side_effect = problem
    with pytest.raises(BitTeamAPIError) as caught:
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False)
    assert caught.value is problem
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [None, [], "pending", 42])
async def test_nonobject_response_rejected(result):
    client = ReadOnlyClient()
    client.p2p.get_withdrawal.return_value = result
    with pytest.raises(ValueError, match="object"):
        await client.get_withdrawal_record("id", source="p2p")


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", [None, 1, "done", {}])
async def test_predicate_must_return_real_bool(decision):
    client = ReadOnlyClient()
    with pytest.raises(TypeError, match="bool"):
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: decision)
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
async def test_async_predicate_rejected_and_closed():
    client = ReadOnlyClient()
    async def complete(_):
        return True
    with pytest.raises(TypeError, match="synchronously"):
        await client.wait_for_withdrawal("id", source="p2p", predicate=complete)


@pytest.mark.asyncio
async def test_noncallable_predicate_fails_before_read():
    client = ReadOnlyClient()
    with pytest.raises(ValueError, match="predicate"):
        await client.wait_for_withdrawal("id", source="p2p", predicate=None)
    client.p2p.get_withdrawal.assert_not_awaited()


@pytest.mark.asyncio
async def test_observation_and_timeout_reprs_omit_payload_secrets():
    client = ReadOnlyClient()
    secret = "synthetic-code-address-token-SECRET"
    client.p2p.get_withdrawal.return_value = {"token": secret, "nested": {"address": secret}}
    with pytest.raises(WithdrawalWaitTimeout) as error:
        await client.wait_for_withdrawal("id", source="p2p", predicate=lambda _: False, max_requests=1)
    assert secret not in repr(error.value.last_observation)
    assert secret not in repr(error.value)
    assert secret not in str(error.value)
    assert error.value.last_observation.payload["token"] == secret


@pytest.mark.asyncio
async def test_predicate_failure_propagates_without_retry():
    client = ReadOnlyClient()
    problem = RuntimeError("synthetic predicate failure")
    def complete(_):
        raise problem
    with pytest.raises(RuntimeError) as caught:
        await client.wait_for_withdrawal("id", source="p2p", predicate=complete)
    assert caught.value is problem
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
async def test_closing_between_observations_prevents_next_request():
    client = ReadOnlyClient()
    def complete(_):
        client._closed = True
        return False
    with pytest.raises(RuntimeError, match="closed"):
        await client.wait_for_withdrawal("id", source="p2p", predicate=complete, interval=0.001)
    assert client.p2p.get_withdrawal.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["send_withdrawal_email_code", "send_withdrawal_phone_code", "confirm_withdrawal"])
@pytest.mark.parametrize("order_id", [None, "", "  "])
async def test_invalid_confirmation_order_id_rejected_without_http(method, order_id):
    client = ReadOnlyClient()
    client.api = SimpleNamespace(post_withdraw_confirmation_email=AsyncMock(),
                                 post_withdraw_confirmation_phone=AsyncMock(),
                                 post_withdraw_confirm=AsyncMock())
    with pytest.raises(ValueError):
        if method == "confirm_withdrawal":
            await client.confirm_withdrawal(order_id=order_id, email_code="synthetic-code")
        else:
            await getattr(client, method)(order_id)
    client.api.post_withdraw_confirmation_email.assert_not_awaited()
    client.api.post_withdraw_confirmation_phone.assert_not_awaited()
    client.api.post_withdraw_confirm.assert_not_awaited()
