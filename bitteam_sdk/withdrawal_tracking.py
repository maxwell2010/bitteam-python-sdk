"""Read-only withdrawal observations. Server statuses are deliberately not guessed."""
import asyncio
import math
from copy import deepcopy
from dataclasses import dataclass, field
from time import time
from .auth import SessionAuth


@dataclass(frozen=True)
class WithdrawalObservation:
    source: str
    identifier: str
    received_at: float
    payload: dict = field(repr=False)


class WithdrawalWaitTimeout(TimeoutError):
    def __init__(self, last_observation=None):
        super().__init__("Withdrawal observation deadline or request limit reached")
        self.last_observation = last_observation


async def read_withdrawal(client, identifier, *, source):
    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError("An existing record identifier is required")
    if getattr(client, "_closed", False):
        raise RuntimeError("Client is closed")
    auth = getattr(client, "auth", None)
    lifecycle = auth._lifecycle if isinstance(auth, SessionAuth) else None
    if source == "p2p":
        payload = await client.p2p.get_withdrawal(path={"withdraw_id": identifier})
    elif source == "spot_transaction":
        client._require_ready()
        payload = await client.api.get_transaction_by_id(identifier)
    else:
        raise ValueError("source must be p2p or spot_transaction; orderId is not a transaction id")
    if getattr(client, "_closed", False):
        raise RuntimeError("Client is closed")
    if lifecycle is not None:
        auth._assert_lifecycle(lifecycle)
    if not isinstance(payload, dict):
        raise ValueError("Expected a withdrawal record object")
    return WithdrawalObservation(source, identifier, time(), deepcopy(payload))


async def wait_for_withdrawal(client, identifier, *, source, predicate,
                              timeout=300, interval=5, max_requests=100):
    """Poll only existing records. Predicate receives an observation, returns bool.

    Caller must use verified server fields to decide completion. This function
    never sends codes, creates, confirms or cancels withdrawals. Errors propagate.
    """
    for name, value in (("timeout", timeout), ("interval", interval)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(name + " must be positive and finite")
    if isinstance(max_requests, bool) or not isinstance(max_requests, int) or not 1 <= max_requests <= 10000:
        raise ValueError("max_requests must be an integer from 1 to 10000")
    if not callable(predicate):
        raise ValueError("A verified completion predicate is required")
    loop = asyncio.get_running_loop()
    deadline, last = loop.time() + timeout, None
    for index in range(max_requests):
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise WithdrawalWaitTimeout(last)
        task = asyncio.ensure_future(read_withdrawal(client, identifier, source=source))
        try:
            done, _ = await asyncio.wait({task}, timeout=remaining)
            if not done:
                raise WithdrawalWaitTimeout(last)
            last = task.result()
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        if loop.time() >= deadline:
            raise WithdrawalWaitTimeout(last)
        decision = predicate(last)
        if not isinstance(decision, bool):
            if asyncio.iscoroutine(decision):
                decision.close()
            raise TypeError("Completion predicate must return bool synchronously")
        if loop.time() >= deadline:
            raise WithdrawalWaitTimeout(last)
        if decision:
            return last
        if index + 1 < max_requests:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise WithdrawalWaitTimeout(last)
            wake_at = min(deadline, loop.time() + interval)
            # Event-loop clocks may wake timers early (notably Windows).
            # Never start another read before the requested poll interval.
            while loop.time() < wake_at:
                await asyncio.sleep(wake_at - loop.time())
            if wake_at >= deadline:
                raise WithdrawalWaitTimeout(last)
    raise WithdrawalWaitTimeout(last)
