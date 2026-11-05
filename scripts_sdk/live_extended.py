"""Opt-in extended checks; never call financial mutation methods.

Public mode performs bounded reads. --account-profile is STATEFUL: encrypted
cache restore, token refresh and cache persistence/invalidation may occur.
It is not a pure read-only account check and must not run during offline audits.
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bitteam_sdk import BitTeamClient, SessionAuth, SessionCache


async def main(profile=None):
    report = {'date': datetime.now(timezone.utc).isoformat(), 'public': [], 'account': []}

    async def check(group, name, call):
        item = {'operation': name}
        try:
            value = await call()
            item.update(ok=True, shape=type(value).__name__)
            if isinstance(value, list):
                item['count'] = len(value)
        except Exception as error:
            status = getattr(error, 'status', None)
            item.update(ok=False, error_type=type(error).__name__,
                        status=status if type(status) is int else None)
            report[group].append(item)
            return False, None
        report[group].append(item)
        return True, value

    async def public_checks():
        async with BitTeamClient(timeout=15, max_read_retries=0) as client:
            for name, call in [('site_coins', client.site.get_coins),
                ('site_currencies', client.site.get_currencies),
                ('p2p_adverts', lambda: client.site.get_advertisements(type_='buy', coin='BTC', fiat='RUB', limit=2)),
                ('news', lambda: client.site.get_news_posts(per_page=2)),
                ('network_catalog', lambda: client.get_withdrawal_networks('USDT')),
                ('l2_snapshot', lambda: client.get_orderbook_snapshot('DEL_USDT'))]:
                await check('public', name, call)
            end = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
            await check('public', 'full_day_candles', lambda: client.fetch_klines('DEL_USDT', start=end-86400, end=end, chunk_bars=500))
            acquired, sub = await check('public', 'orderbook_subscribe', lambda: client.subscribe_orderbook('DEL_USDT'))
            if acquired:
                try:
                    await check('public', 'orderbook_push', lambda: asyncio.wait_for(anext(sub), 20))
                finally:
                    await check('public', 'orderbook_close', sub.close)

    async def account_checks():
        async with BitTeamClient(auth=SessionAuth(cache=SessionCache(profile)), timeout=15, max_read_retries=0) as client:
            restored, available = await check('account', 'session_resume', client.resume_session)
            if not restored:
                return
            if not available:
                report['account'].append({'operation': 'session_required', 'ok': False,
                                          'error_type': 'SavedSessionUnavailable', 'status': None})
                return
            for name, call in [('balances_ack', client.account_streams.subscribe_balances),
                ('orders_ack', client.account_streams.subscribe_orders), ('wallets', client.get_balance),
                ('p2p_wallets', client.p2p.get_accounts), ('refresh', client.refresh),
                ('wallets_after_refresh', client.get_balance)]:
                await check('account', name, call)

    # Context construction/entry/exit belong to the same diagnostic boundary.
    # Cancellation still propagates; no retry or authentication recovery added.
    await check('public', 'public_transport', public_checks)
    if profile:
        await check('account', 'account_transport', account_checks)
    destination = Path(__file__).resolve().parents[1] / 'output-sdk' / 'extended-smoke.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-profile', help='STATEFUL existing encrypted profile: restore/refresh/cache updates; no login/OTP prompts')
    asyncio.run(main(parser.parse_args().account_profile))
