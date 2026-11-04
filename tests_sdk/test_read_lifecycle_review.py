"""Synthetic account boundaries; no network, credentials or financial operations."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bitteam_sdk.auth import BitTeamAPIError, SessionAuth
from bitteam_sdk.services import ServiceMethods


class Client(ServiceMethods):
    def __init__(self):
        self.auth = SessionAuth()
        self._closed = False
        self._require_ready = Mock()
        self.p2p = SimpleNamespace(get_withdrawal=AsyncMock(return_value={"phase": "pending"}))
        self.api = SimpleNamespace(get_transaction_by_id=AsyncMock(return_value={"phase": "pending"}))
        self.get_transaction_history = AsyncMock(side_effect=[[{"id": 1}, {"id": 2}], []])
        self.get_user_trades = AsyncMock(side_effect=[[{"id": 1}, {"id": 2}], []])
        self.get_user_orders = AsyncMock(side_effect=[[{"id": 1}, {"id": 2}], []])


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["p2p", "spot_transaction"])
@pytest.mark.parametrize("decision", [False, True])
async def test_wait_does_not_cross_account_boundary(source, decision):
    client = Client()
    def predicate(_):
        client.auth._lifecycle += 1
        return decision
    with pytest.raises(asyncio.CancelledError):
        await client.wait_for_withdrawal("existing", source=source, predicate=predicate,
                                         interval=0.001, max_requests=2)
    method = client.p2p.get_withdrawal if source == "p2p" else client.api.get_transaction_by_id
    assert method.await_count == 1


@pytest.mark.asyncio
async def test_wait_allows_token_refresh_within_same_account():
    client = Client()
    def predicate(_):
        client.auth._generation += 1
        return True
    assert (await client.wait_for_withdrawal("existing", source="p2p", predicate=predicate)).identifier == "existing"


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["iter_transactions", "iter_user_trades", "iter_user_orders"])
@pytest.mark.parametrize("boundary", ["lifecycle", "replacement"])
async def test_private_iterator_never_yields_buffered_rows_from_previous_account(method, boundary):
    client = Client()
    iterator = getattr(client, method)(page_size=2)
    assert await anext(iterator) == {"id": 1}
    if boundary == "replacement":
        client.auth = SessionAuth()
    else:
        client.auth._lifecycle += 1
    with pytest.raises(asyncio.CancelledError):
        await anext(iterator)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,fetch", [("iter_transactions", "get_transaction_history"),
    ("iter_user_trades", "get_user_trades"), ("iter_user_orders", "get_user_orders")])
async def test_private_iterator_checks_boundary_before_next_page(method, fetch):
    client = Client()
    iterator = getattr(client, method)(page_size=1)
    getattr(client, fetch).side_effect = [[{"id": 1}], [{"id": 2}]]
    assert await anext(iterator) == {"id": 1}
    client.auth._lifecycle += 1
    with pytest.raises(asyncio.CancelledError):
        await anext(iterator)
    assert getattr(client, fetch).await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("row", [{"orderId": "order-only"}, {"trade_id": 7},
    {"id": True}, {"id": {}}, {"id": []}, {"id": ""}, {"id": "  "}, {"id": 1.5}])
async def test_transaction_iterator_requires_transaction_id(row):
    client = Client()
    client.get_transaction_history.side_effect = [[row]]
    with pytest.raises(BitTeamAPIError):
        await anext(client.iter_transactions())


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["p2p", "spot_transaction"])
async def test_single_read_rejects_auth_replacement_while_waiting(source):
    client = Client()
    async def read(*args, **kwargs):
        client.auth = SessionAuth()
        return {"phase": "pending"}
    method = client.p2p.get_withdrawal if source == "p2p" else client.api.get_transaction_by_id
    method.side_effect = read
    with pytest.raises(asyncio.CancelledError):
        await client.get_withdrawal_record("existing", source=source)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,fetch", [("iter_transactions", "get_transaction_history"),
    ("iter_user_trades", "get_user_trades"), ("iter_user_orders", "get_user_orders")])
async def test_private_iterator_rejects_account_boundary_during_fetch(method, fetch):
    client = Client()
    async def read(*args, **kwargs):
        client.auth._lifecycle += 1
        return [{"id": 1}]
    getattr(client, fetch).side_effect = read
    with pytest.raises(asyncio.CancelledError):
        await anext(getattr(client, method)())


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["iter_transactions", "iter_user_trades", "iter_user_orders"])
async def test_private_iterator_checks_boundary_after_last_yield(method):
    client = Client()
    iterator = getattr(client, method)(page_size=3)
    assert await anext(iterator) == {"id": 1}
    assert await anext(iterator) == {"id": 2}
    client.auth._lifecycle += 1
    with pytest.raises(asyncio.CancelledError):
        await anext(iterator)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["iter_transactions", "iter_user_trades", "iter_user_orders"])
async def test_private_iterator_allows_refresh_within_same_account(method):
    client = Client()
    iterator = getattr(client, method)(page_size=2)
    assert await anext(iterator) == {"id": 1}
    client.auth._generation += 1
    assert await anext(iterator) == {"id": 2}
    with pytest.raises(StopAsyncIteration):
        await anext(iterator)
