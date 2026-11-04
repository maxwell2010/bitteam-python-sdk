"""Bounded read-only extended smoke. Financial mutation methods are never called."""
import argparse,asyncio,json
from datetime import datetime,timezone
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bitteam_sdk import BitTeamClient,SessionAuth,SessionCache,MarketDataRecorder

async def main(profile=None):
    report={'date':datetime.now(timezone.utc).isoformat(),'public':[],'account':[]}
    async def check(group,name,call):
        item={'operation':name}
        try:
            value=await call();item.update(ok=True,shape=type(value).__name__)
            if isinstance(value,list):item['count']=len(value)
        except Exception as error:
            item.update(ok=False,error_type=type(error).__name__,status=getattr(error,'status',None))
        report[group].append(item)
    async with BitTeamClient(timeout=15,max_read_retries=0) as client:
        for name,call in [('site_coins',client.site.get_coins),('site_currencies',client.site.get_currencies),
            ('p2p_adverts',lambda:client.site.get_advertisements(type_='buy',coin='BTC',fiat='RUB',limit=2)),
            ('news',lambda:client.site.get_news_posts(per_page=2)),
            ('network_catalog',lambda:client.get_withdrawal_networks('USDT')),
            ('l2_snapshot',lambda:client.get_orderbook_snapshot('DEL_USDT'))]:
            await check('public',name,call)
        end=int(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
        await check('public','full_day_candles',lambda:client.fetch_klines('DEL_USDT',start=end-86400,end=end,chunk_bars=500))
        sub=await client.subscribe_orderbook('DEL_USDT')
        try:
            await check('public','orderbook_push',lambda:asyncio.wait_for(anext(sub),20))
        finally:await sub.close()
    if profile:
        async with BitTeamClient(auth=SessionAuth(cache=SessionCache(profile)),timeout=15,max_read_retries=0) as client:
            if not await client.resume_session():raise RuntimeError('A saved session is required; this smoke does not request credentials')
            for name,call in [('balances_ack',client.account_streams.subscribe_balances),
                ('orders_ack',client.account_streams.subscribe_orders),('wallets',client.get_balance),
                ('p2p_wallets',client.p2p.get_accounts),('refresh',client.refresh),('wallets_after_refresh',client.get_balance)]:
                await check('account',name,call)
    destination=Path(__file__).resolve().parents[1]/'output-sdk'/'extended-smoke.json'
    destination.parent.mkdir(exist_ok=True)
    destination.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-profile',help='Optional existing encrypted profile, no login/OTP prompts')
    asyncio.run(main(parser.parse_args().account_profile))
