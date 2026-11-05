"""High-level P2P reads use mock APIs and never create a transport session."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk import BitTeamClient, SessionAuth, P2PAccountSnapshot, P2PWithdrawalSnapshot


@pytest.mark.asyncio
async def test_client_p2p_read_facades_keep_namespaces_and_requested_ids_separate():
    client = BitTeamClient(auth=SessionAuth())
    client._p2p = SimpleNamespace(
        get_accounts=AsyncMock(return_value={"account": [{"currency_id": 77}]}),
        get_withdrawal=AsyncMock(return_value={"status": True, "data": {
            "id": "record-id", "type": "withdraw", "status": 1}}),
        close=AsyncMock())
    try:
        accounts = await client.get_p2p_accounts()
        record = await client.inspect_p2p_withdrawal("requested-id")
        assert isinstance(accounts, P2PAccountSnapshot)
        assert isinstance(record, P2PWithdrawalSnapshot)
        assert accounts.accounts[0]["currency_id"] == 77
        assert record.requested_identifier == "requested-id"
        assert record.record_identifier == "record-id"
        assert record.state == "pending"
        assert client.rest._session is None
        client._p2p.get_withdrawal.assert_awaited_once_with(path={"withdraw_id": "requested-id"})
    finally:
        await client.close()
    with pytest.raises(RuntimeError, match="closed"):
        await client.get_p2p_accounts()
