"""Bundled OpenAPI path constraints apply before any fake dispatch."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bitteam_sdk.api import BitTeamAPI


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, True, False, 'a', 'a' * 14, 'bad:pair', ['del_usdt'], 1.5])
async def test_pair_path_rejects_schema_invalid_values_without_dispatch(value):
    send = AsyncMock()
    api = BitTeamAPI(SimpleNamespace(_request=send))
    with pytest.raises(ValueError):
        await api.get_pair_by_name(value)
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_pair_path_preserves_route_and_public_flag():
    send = AsyncMock(return_value={'result': {}})
    await BitTeamAPI(SimpleNamespace(_request=send)).get_pair_by_name('del_usdt')
    send.assert_awaited_once_with('GET', '/pair/del_usdt', params={}, data=None, public=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['get_trade_by_id', 'get_transaction_by_id', 'get_ccxt_order_by_id'])
@pytest.mark.parametrize('value', [9, '9'])
async def test_documented_identifier_paths_keep_integer_and_string_compatibility(method, value):
    send = AsyncMock()
    await getattr(BitTeamAPI(SimpleNamespace(_request=send)), method)(value)
    assert send.await_count == 1
    assert send.await_args.args[1].endswith('/9')


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [9, '9', '009'])
async def test_documented_integer_currency_path_accepts_decimal_string_ids(value):
    send = AsyncMock()
    await BitTeamAPI(SimpleNamespace(_request=send)).get_withdraw_by_currency_id_check(value)
    assert send.await_args.args[1] == f'/withdraw/{value}/check'


@pytest.mark.asyncio
@pytest.mark.parametrize('value', [None, True, False, 'not-an-id', '1.5', -1, '0', 0, 1.5])
async def test_integer_currency_path_rejects_noninteger_or_nonpositive_values(value):
    send = AsyncMock()
    with pytest.raises(ValueError):
        await BitTeamAPI(SimpleNamespace(_request=send)).get_withdraw_by_currency_id_check(value)
    send.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,value', [('get_markdown_content_by_slug', 'abc'),
    ('get_trade_by_id', 'a' * 14), ('get_orderbooks_by_symbol', 'bad:pair')])
async def test_other_bundled_path_constraints_are_not_skipped(method, value):
    send = AsyncMock()
    with pytest.raises(ValueError):
        await getattr(BitTeamAPI(SimpleNamespace(_request=send)), method)(value)
    send.assert_not_awaited()
