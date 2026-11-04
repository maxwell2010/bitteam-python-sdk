"""Read-only public example: python -m bitteam_sdk.example."""
import asyncio
from . import BitTeamClient


async def main():
    async with BitTeamClient() as client:
        print('Trading pairs:', len(await client.get_trading_pairs()))
        ticker = await client.get_ticker('DEL_USDT')
        print('DEL_USDT last:', ticker['last_price'], 'bid:', ticker['bid'], 'ask:', ticker['ask'])
        candles = await client.get_klines('DEL_USDT', '15m')
        print('Candles in the last day:', len(candles))


if __name__ == '__main__':
    asyncio.run(main())
