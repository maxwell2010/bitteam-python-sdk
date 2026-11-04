from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import pytest
from bitteam_sdk import transaction_evidence
from bitteam_sdk.services import ServiceMethods

class Client(ServiceMethods):
    def __init__(self, pages):
        self._require_ready = Mock()
        self.api = SimpleNamespace(get_transactions_by_user=AsyncMock(side_effect=pages))

def page(*rows):
    return {"ok": True, "result": {"transactions": list(rows)}}

@pytest.mark.parametrize("status,state", [(-1,"cancelled"),(0,"created"),(1,"pending"),(2,"unknown"),(200,"unknown"),(True,"unknown"),("1","unknown")])
def test_p2p_status_one_is_not_settled_and_future_status_is_unknown(status,state):
    result = transaction_evidence({"id": 1,"type":"withdraw","status":status},source="p2p")
    assert result.state == state
    assert result.tx_hash is None

@pytest.mark.parametrize("status,state", [(-1,"failed"),(0,"pending"),(1,"unknown"),(99,"unknown"),(True,"unknown"),("success","unknown")])
def test_spot_does_not_inherit_ui_default_success(status,state):
    assert transaction_evidence({"status":status},source="spot_transaction").state == state

def test_chain_hash_internal_transfer_and_secret_repr():
    row={"id":"tx", "params":{"tx_id":"private-hash", "blockChain":"Tron"}}
    result=transaction_evidence(row,source="spot_transaction")
    row["params"]["tx_id"]="changed"
    assert result.tx_hash=="private-hash" and result.blockchain=="Tron"
    assert "private-hash" not in repr(result)
    assert result.raw["params"]["tx_id"]=="private-hash"
    row["params"]["internalTransfer"]=True
    assert transaction_evidence(row,source="spot_transaction").tx_hash is None

@pytest.mark.asyncio
async def test_pagination_deduplicates_overlap_and_passes_time_bounds():
    client=Client([page({"id":1},{"id":2}),page({"id":2},{"id":3}),page()])
    rows=[r async for r in client.iter_transactions(start=10,end=20,page_size=2,max_pages=4)]
    assert [r["id"] for r in rows]==[1,2,3]
    assert client.api.get_transactions_by_user.await_args_list[1].kwargs=={"params":{"limit":2,"offset":2,"from":10,"to":20}}

@pytest.mark.asyncio
async def test_repeated_page_is_not_infinite():
    client=Client([page({"id":1}),page({"id":1})])
    with pytest.raises(RuntimeError,match="repeated"):
        _=[r async for r in client.iter_transactions(page_size=1)]

@pytest.mark.asyncio
async def test_request_bound_raises_rather_than_truncates():
    client=Client([page({"id":1})])
    with pytest.raises(RuntimeError,match="max_pages"):
        _=[r async for r in client.iter_transactions(page_size=1,max_pages=1)]

@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs",[{"limit":True},{"limit":1001},{"offset":-1},{"start":True},{"end":-1},{"start":2,"end":1}])
async def test_bad_filters_never_request(kwargs):
    client=Client([])
    with pytest.raises(ValueError): await client.get_transaction_history(**kwargs)
    client.api.get_transactions_by_user.assert_not_awaited()

@pytest.mark.asyncio
async def test_malformed_response_not_silent_empty():
    client=Client([{"ok":True,"result":{}}])
    with pytest.raises(Exception): await client.get_transaction_history()
