# Примеры использования

[Установка и авторизация](../bitteam_sdk/ACCOUNT_CHECK.md) - [главная](../README.md).
Каждый блок Python ниже - отдельный скрипт. Публичные запросы при запуске
обращаются к бирже; account-примеры используют только локально введённые данные.
Заменяйте символы и диапазоны по доступному каталогу. Наличие метода не доказывает
доступность backend или права аккаунта. Все времена диапазона - UTC.

## Публичные тикер, стакан и свечи

Core достаточно. `get_ticker` и snapshot используют REST, свечи - history WSS.
Для публичных методов `init()` не нужен; context manager закрывает соединения.

```python
import asyncio
from bitteam_sdk import BitTeamClient

async def main():
    async with BitTeamClient() as client:
        ticker = await client.get_ticker("DEL_USDT")
        book = await client.get_orderbook_snapshot("DEL_USDT")
        candles = await client.get_klines("DEL_USDT", "15m")
        print("Last:", ticker["last_price"])
        print("Best bid/ask:", book.best_bid, book.best_ask)
        print("Candles:", len(candles))

asyncio.run(main())
```

Свечи содержат `open_time` в миллисекундах; цены/объёмы сохраняются строками.
Пустой стакан допустим: лучшие цены могут быть `None`.

## Баланс по API-ключам

Используйте ключ с подходящими правами чтения. Пример не создаёт ордера, переводы
или заявки вывода. Ключи вводятся скрыто, баланс не печатается.

```python
import asyncio
import getpass
from bitteam_sdk import BitTeamClient, ApiKeyAuth, BitTeamAPIError

async def main():
    auth = ApiKeyAuth(getpass.getpass("API key: "), getpass.getpass("API secret: "))
    async with BitTeamClient(auth=auth) as client:
        try:
            await client.init()
            await client.get_balance()
            print("API-key balance read succeeded.")
        except (BitTeamAPIError, ValueError) as error:
            print("Balance read failed:", type(error).__name__)

asyncio.run(main())
```

Для входа с TOTP/device challenge, сохранения, resume/logout см.
[полные SessionAuth-примеры](../bitteam_sdk/ACCOUNT_CHECK.md).
У пользовательской сессии баланс читается через address/wallets, у ключей -
ccxt/balance; общие API-v2/P2P токены и spot токены не взаимозаменяемы.

## Ограниченное чтение истории

`fetch_klines` читает полуоткрытый диапазон `[start, end)` кусками. `start/end` -
Unix-секунды или timezone-aware datetime без микросекунд. Поддержаны интервалы
`1m`, `5m`, `15m`, `1h`, `1d`. Лимиты - предохранители: при превышении исключение
`HistoryLimitError`, а не молчаливое усечение списка.

```python
import asyncio
from datetime import datetime, timezone
from bitteam_sdk import BitTeamClient, HistoryLimitError

async def main():
    async with BitTeamClient() as client:
        try:
            rows = await client.fetch_klines(
                "DEL_USDT", "1m",
                start=datetime(2026, 11, 1, tzinfo=timezone.utc),
                end=datetime(2026, 11, 2, tzinfo=timezone.utc),
                chunk_bars=500, limit=1440, max_requests=3,
            )
            print("Returned candles:", len(rows))
        except HistoryLimitError:
            print("Narrow the range or explicitly increase resource bounds.")

asyncio.run(main())
```

Для обработки без накопления списка есть `client.iter_klines()` с теми же bounds.
Пустые/редкие окна не заполняются выдуманными свечами; полнота архива биржи не
гарантируется. `limit` не означает число последних свечей.

## Подписка и явное восстановление свечей

Храните последнюю обработанную UTC-границу в приложении. Пример ограничивает
ожидание события и делает не более одной попытки recovery при gap. После
восстановления исторические свечи и live-итератор остаются отдельными.

```python
import asyncio
import time
from bitteam_sdk import BitTeamClient, KlineStreamGap

async def main():
    async with BitTeamClient() as client:
        subscription = await client.subscribe_kline("DEL_USDT", "1m")
        end = int(time.time()) // 60 * 60
        start = max(0, end - 600)
        try:
            try:
                candle = await asyncio.wait_for(anext(subscription), timeout=20)
                print("Candle open time:", candle.open_time)
            except KlineStreamGap:
                recovery = await client.recover_klines(
                    subscription, start=start, end=end,
                    chunk_bars=100, limit=100, max_requests=1,
                )
                subscription = recovery.subscription
                print("History to reconcile:", len(recovery.candles))
                candle = await asyncio.wait_for(anext(subscription), timeout=20)
                print("Replacement candle open time:", candle.open_time)
        except asyncio.TimeoutError:
            print("No event within the local deadline.")
        finally:
            await subscription.close()

asyncio.run(main())
```

`KlineStreamGap` требует решения приложения, а не означает replay. Неполная
текущая свеча может изменяться; сверяйте пересечения по времени самостоятельно.
После `client.close()` его потоки не переподключаются.

## Стакан: snapshot отдельно от raw events

Этот пример получает raw-подписку и новый snapshot через helper reconciliation,
затем закрывает подписку. Он **не** строит атомарный live L2.

```python
import asyncio
from bitteam_sdk import BitTeamClient

async def main():
    async with BitTeamClient() as client:
        subscription = await client.subscribe_orderbook("DEL_USDT")
        try:
            result = await client.reconcile_book("DEL_USDT", subscription)
            subscription = result.subscription
            print("Snapshot best bid:", result.snapshot.best_bid)
            assert result.continuity_guaranteed is False
            assert result.events_applied is False
        finally:
            await subscription.close()

asyncio.run(main())
```

Серверные sequence/replay, порядок delta и atomic snapshot+delta не подтверждены.
Не применяйте raw events как доказанные дельты. [Подробные границы](../bitteam_sdk/RELIABILITY.md).

## SQLite и график без сети

Установите extras `sqlite,charts`. Полный пример использует синтетическую свечу,
in-memory SQLite и Plotly Figure без браузера, файлов и HTTP:

```python
import asyncio
from bitteam_sdk import BitTeamClient
from bitteam_sdk.models import Kline
from bitteam_sdk.storage import get_storage

async def main():
    storage = get_storage("sqlite", path=":memory:", retention=None)
    await storage.init()
    try:
        await storage.save_kline(Kline("SYN_USDT", "1m", 0, "1", "2", "1", "1.5", "3"))
        rows = await storage.get_klines("SYN_USDT", "1m", limit=100)
        frame = Kline.to_dataframe(rows)
        figure = BitTeamClient.plot_klines(frame, show=False)
        assert figure.data[0].type == "candlestick"
        assert "candlestick" in figure.to_json()
        print("Stored candles:", len(rows))
    finally:
        await storage.close()

asyncio.run(main())
```

По умолчанию storage сохраняет последние 2000 строк на `(symbol, interval)`.
`retention=None` отключает это удаление, но не загружает историю автоматически.
`limit` у storage ограничивает чтение последних строк, возвращаемых по времени.
SQLite memory живёт до `close()`. `MarketDataRecorder` требует файловый SQLite,
`:memory:` для него не поддерживается. PostgreSQL выбирается через
`get_storage("postgres", dsn=..., retention=None)` с extra `postgres` и своим
сервером; это отдельная интеграция, не свойство in-memory примера.
DataFrame имеет timezone-naive UTC индекс; преобразование decimal в числовые
колонки может округлять, для денежных значений храните исходные строки.

## Вывод: только план и чтение существующей записи

Подготовка P2P payload полностью локальна и не отправляет заявку:

```python
from bitteam_sdk import prepare_p2p_withdrawal

plan = prepare_p2p_withdrawal(44, address="example-destination", amount="1.0000")
assert plan.operation == "create_withdrawal_body"
```

`44` и адрес здесь демонстрационные. Рабочий API-v2 currency_id выбирайте из
проверенных данных аккаунта; он не равен spot currencyId. Поддержка всех сетей
не обещается. Не отправляйте этот пример как реальную заявку.

Для уже существующей записи P2P используйте следующий Windows-пример с ранее
созданным профилем. Он не входит заново, не отправляет коды и не создаёт,
не подтверждает и не отменяет вывод. Resume проверяет сессию и может менять кэш.

```python
import asyncio
from bitteam_sdk import BitTeamClient, SessionAuth, SessionCache

async def main():
    identifier = input("Existing P2P withdrawal record ID: ").strip()
    async with BitTeamClient(auth=SessionAuth(cache=SessionCache("main"))) as client:
        if not await client.resume_session():
            print("An explicit login is required first.")
            return
        observation = await client.get_withdrawal_record(identifier, source="p2p")
        print("Record received from:", observation.source)
        # Inspect observation.payload only in your private application.
        # No generic numeric status is treated as financial success here.

asyncio.run(main())
```

Для spot укажите `source="spot_transaction"` и **известный ID транзакции**,
а не orderId заявки. Ограниченное ожидание `wait_for_withdrawal` требует вашего
синхронного predicate по проверенным полям сервера; общего критерия finality нет.
[Семантика read-only tracking](../bitteam_sdk/WITHDRAWAL_TRACKING.md).

## Ошибки и границы

`BitTeamAPIError.status` содержит HTTP-статус. `error.code` может быть
произвольной строкой сервера, поэтому не печатайте его или приватные payload.
Сетевой timeout не означает, что операция на сервере не происходила.
Здесь нет примеров создания ордеров/вывода или отправки финансовых подтверждений.
OTP delivery, general renewal, archive completeness, replay и финансовая finality
не подтверждаются этими примерами. [Матрица фактов и ограничений](TEST_GAPS.md).
