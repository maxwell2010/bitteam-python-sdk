"""Opt-in anonymous checks. No account, mail, trade or withdrawal operations."""
import asyncio
import datetime
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitteam_sdk import BitTeamClient, BitTeamAPIError


async def main():
    report = {'date': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'mode': 'anonymous-read-only', 'rest': [], 'history': []}
    cases = [
        ('get_asset', {}), ('get_stats', {}), ('get_currencies', {'params': {'limit': 10, 'offset': 0}}),
        ('get_pairs', {}), ('get_ccxt_pairs', {}), ('get_rates', {}),
        ('get_orders', {'params': {'limit': 2, 'offset': 0}}),
        ('get_trades', {'params': {'limit': 2, 'offset': 0}}),
        ('get_cmc_assets', {}), ('get_cmc_summary', {}), ('get_cmc_ticker', {}),
        ('get_cmc_orderbook_by_pair', {'pair': 'del_usdt'}),
        ('get_cmc_trades_by_pair', {'pair': 'del_usdt'}),
        ('get_orderbooks_by_symbol', {'symbol': 'del_usdt'}),
        ('get_pair_by_name', {'name': 'del_usdt'}), ('get_pairs_precisions', {}),
        ('get_markdown_menu', {}), ('get_altyn_banks', {}), ('get_altyn_client', {}),
    ]
    async with BitTeamClient(timeout=15, max_read_retries=1) as client:
        for name, kwargs in cases:
            entry = {'method': name}
            try:
                if name in ('get_altyn_banks', 'get_altyn_client'):
                    entry['anonymous_probe'] = True
                    entry['sdk_requires_auth'] = True
                    endpoint = '/altyn/banks' if name == 'get_altyn_banks' else '/altyn/client/'
                    value = await client.rest._send('GET', client.rest.base_url + endpoint, headers={})
                else:
                    value = await getattr(client.api, name)(**kwargs)
                entry.update(ok=True, shape=type(value).__name__)
                if isinstance(value, list):
                    entry['count'] = len(value)
                if isinstance(value, dict):
                    entry['keys'] = list(value)[:15]
            except BitTeamAPIError as error:
                # Server error codes may be arbitrary strings containing private
                # data. Export only plain numeric diagnostic metadata.
                entry.update(ok=False,
                             http_status=error.status if type(error.status) is int else None,
                             code=error.code if type(error.code) is int else None)
            except Exception as error:
                entry.update(ok=False, error_type=type(error).__name__)
            report['rest'].append(entry)
            print(name, 'OK' if entry['ok'] else 'FAILED', flush=True)
        for name, call in [
            ('config', client.history.get_config), ('server_time', client.history.get_server_time),
            ('symbol', lambda: client.history.get_symbol('DEL_USDT')),
            ('candles', lambda: client.get_klines('DEL_USDT','15m')),
            ('trade_candles', lambda: client.get_candles_from_trades('DEL_USDT')),
        ]:
            entry = {'method': name}
            try:
                value = await call()
                entry.update(ok=True, shape=type(value).__name__)
                if isinstance(value, list):entry['count'] = len(value)
            except Exception as error:
                entry.update(ok=False, error_type=type(error).__name__)
            report['history'].append(entry)
            print('history.' + name, 'OK' if entry['ok'] else 'FAILED', flush=True)
        try:
            sub = await client.subscribe_kline('DEL_USDT','1m')
            report['history'].append({'method': 'subscribe_kline_ack', 'ok': True})
            await sub.close()
        except Exception as error:
            report['history'].append({'method': 'subscribe_kline_ack', 'ok': False, 'error_type': type(error).__name__})
    destination = Path(__file__).resolve().parents[1] / 'bitteam_sdk' / 'LIVE_CHECKS.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Report:', destination)


if __name__ == '__main__':
    asyncio.run(main())
