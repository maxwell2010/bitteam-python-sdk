"""Fixed journal page props -> shared request contract; fake transport only."""
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import AuthenticationError, BitTeamAPIError
from bitteam_sdk.p2p_api import P2P_CATALOG
from test_p2p_api import Response, auth_with_cookie, client_with


CALLS = [
    ("get_account_transaction_journal", "/transactions/account-transactions", {}),
    ("get_transaction_journal", "/transactions/get-transactions", {"type": "amount"}),
    ("get_transaction_journal", "/transactions/get-transactions", {"type": "system"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,path,params", CALLS)
@pytest.mark.parametrize("data", [[], {"opaque": "raw"}, None])
async def test_journal_chain_routes_fixed_window_and_preserves_data_without_status_guess(operation, path, params, data):
    payload = {"data": data}
    client = client_with(auth_with_cookie(), Response(payload))
    assert await client.call(operation, params=params) is payload
    assert len(client._session.calls) == 1
    method, url, request = client._session.calls[0]
    assert (method, url) == ("GET", client.BASE_URL + path)
    assert request["params"] == {"page": 1, "limit": 999, **params}
    assert request["json"] is None
    assert request["headers"]["Authorization"] == "Bearer synthetic-general-token"
    assert request["allow_redirects"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,params", [
    ("get_account_transaction_journal", {"page": 2}),
    ("get_account_transaction_journal", {"limit": 1000}),
    ("get_account_transaction_journal", {"type": "amount"}),
    ("get_account_transaction_journal", {"currency_id": 44}),
    ("get_transaction_journal", {}),
    ("get_transaction_journal", {"type": None}),
    ("get_transaction_journal", {"type": "other"}),
    ("get_transaction_journal", {"type": ["amount"]}),
    ("get_transaction_journal", {"type": "amount", "offset": 0}),
    ("get_transaction_journal", {"type": "system", "page": 2}),
    ("get_transaction_journal", {"type": "system", "limit": 100}),
])
async def test_journal_contract_rejects_invented_filters_windows_and_types_before_http(operation, params):
    client = client_with(auth_with_cookie())
    with pytest.raises(ValueError):
        await client.call(operation, params=params)
    assert not client._session.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,path,params", CALLS)
@pytest.mark.parametrize("payload,status,error", [
    ({"opaque": "missing-data"}, 200, BitTeamAPIError),
    ({"data": [], "status": False}, 200, BitTeamAPIError),
    ({"data": [], "code": 409}, 200, BitTeamAPIError),
    ({"data": []}, 401, AuthenticationError),
    ({"opaque": "unavailable"}, 503, BitTeamAPIError),
])
async def test_journal_errors_are_not_empty_history_or_automatic_retries(operation, path, params, payload, status, error):
    auth = auth_with_cookie()
    auth.refresh = AsyncMock()
    client = client_with(auth, Response(payload, status))
    with pytest.raises(error):
        await client.call(operation, params=params)
    assert len(client._session.calls) == 1
    auth.refresh.assert_not_awaited()


def test_journal_provenance_records_page_props_and_shared_request_chain_separately():
    for name, _, _ in CALLS:
        entry = P2P_CATALOG[name]
        assert entry["source_sha256"] == "2c0957ed01c7bfd933ba10d0bba968fafb5802f81872c2f9205768b6a0b20107"
        assert entry["source_offsets"] == {"module_import": 5600, "props": 5715, "get_call": 7813, "response_consumer": 7967}
        assert entry["reported_contract"] and "source_excerpt" not in entry
        assert entry["page_prop_sources"]
        assert entry["query_policy"] == "declared"
        assert entry["get_mutation"] is False and entry["private_live_verified"] is False
    assert P2P_CATALOG["get_archive_operations"]["path"] == "/operations/archive"
    assert sum(entry["path"] == "/operations/archive" for entry in P2P_CATALOG.values()) == 1
