> Исторический материал: даты, результаты и состояние сессии ниже относятся только к описанным этапам.
> Это не текущий статус кэша, backend или публикации. Прежний freeze завершён; релиз 1.7.0 опубликован.
> [Руководства](../README.md#руководства) - [архив и исследования](../docs/archive/README.md).

# Расширенное покрытие биржи и сайта - SDK 1.5.0

Исследование от 2026-11-03: официальный Swagger, актуальные Nuxt/Next JS главной, spot и P2P, WordPress REST index блога. JS не исполнялся. Публичные маршруты проверялись чтением; приватные проверки ограничены восстановлением сессии, балансами, ордерами/уведомлениями и ACK подписок. Торговые заявки, P2P-сделки, платежи и выводы при проверке не создавались.

## Карта возможностей

| Область | SDK | Проверка и ограничения |
|---|---|---|
| Официальный spot REST | client.api, 110 операций каталога | 106 клиентских + 4 заблокированных server/dev callbacks; покрытие схемы не означает 110 живых проверок |
| Пары/валюты/курсы/точности | get_trading_pairs, get_currencies, get_ticker, get_precisions | Реальный API |
| Стакан L2 | get_orderbook_snapshot, OrderBookSnapshot | Полный ответ endpoint с уровнями price/amount, не индивидуальные L3-ордера |
| Глубина/спред | snapshot.depth, spread, mid_price, imbalance | Decimal; cumulative sums не зависят от внешнего Decimal precision; imbalance является десятичным приближением отношения |
| Публичные ордера/сделки | get_public_orders/trades, iter_public_orders/trades | Доступные серверу страницы с дедупликацией/ограничениями; не атомарный снимок и не гарантия вечного хранения |
| Свечи | get_klines, fetch_klines, iter_klines | Рабочий history WSS; выгрузка ограниченного диапазона чанками, строго [start,end) |
| Свечи из сделок | get_candles_from_trades | Только из доступного набора сделок; пустые бары не выдумываются |
| Live market | client.market или subscribe_orderbook/subscribe_trades | Реальные pub по /prices,/pairs,/orderbooks/{pairId},/trades/{pairId} |
| Live account | client.account_streams | Балансы, ордера, userTrades, notifications, chat; SessionAuth и отдельный Bearer socket |
| История стакана | MarketDataRecorder | Только записанные локально наблюдения начиная с запуска; готовый серверный исторический L2 не найден |
| История аккаунта | get_user_orders/trades, iter_user_orders/trades, get_transactions | Рабочий spot REST; исходный объём ордера должен храниться приложением |
| Старый archive | client.archive | Контракты сайта /trades,/ordersByUser,/tradesByUser реализованы; публичный backend сейчас давал timeout |
| Профиль/вывод/верификация/настройки | client.api + удобные методы | Контракты Swagger; финансовые изменения не исполнялись в live-тестах |
| P2P/API-v2 | client.p2p | Каталог helper-операций сайта и конкретных cabinet callsites; отдельные IDs и общий access_token |
| Публичные P2P данные | client.site | Валюты, методы оплаты, объявления, лимиты, курсы; реальные GET |
| Новости/статические страницы | client.site.get_news_posts/post/categories и static menu/page | First-party WordPress JSON index и API-v2; новости реально прочитаны |
| Market rankings/монеты | client.site.get_crypto_* | Контракты найдены; market-back отвечал redirect/HTML/timeout, рабочие данные не обещаются |
| Документация | client.site.get_docs_pages | Контракт найден; docs backend давал 502 |

Это карта известных клиентских контрактов и фактически доступных источников. SDK не заявляет доступ к данным, которые сервер не предоставляет, и не подменяет ошибки пустыми/синтетическими историями.

## История свечей и сделок

```python
from datetime import datetime, timezone
from bitteam_sdk import BitTeamClient

async with BitTeamClient() as client:
    candles = await client.fetch_klines(
        "DEL_USDT", "1m",
        start=datetime(2026, 11, 1, tzinfo=timezone.utc),
        end=datetime(2026, 11, 2, tzinfo=timezone.utc),
        chunk_bars=1000, limit=100000, max_requests=1000,
    )
    async for candle in client.iter_klines("DEL_USDT", "15m", start=unix_from, end=unix_to):
        ...
    async for trade in client.iter_public_trades("DEL_USDT", page_size=100, max_pages=100):
        ...
```

start/end - UTC Unix seconds или aware datetime; open_time - миллисекунды. Сырая history-служба включает конечную свечу, но range-helper её исключает. Превышение лимитов вызывает ошибку вместо тихого обрезания. Пропуски/пустые диапазоны сервера не заполняются. При прекращении async generator до конца вызовите aclose(); caller-owned history socket живёт до client.close().

На бирже проверена выгрузка 1440 уникальных минутных свечей за полные UTC-сутки через три запроса по 500 баров. Ответ сырого сервера за 7 суток содержал 10081 свечу с включительной границей. Глубина хранения до листинга и полнота отсутствующих баров сервером не гарантированы.

## Стаканы, события и локальная история

```python
from bitteam_sdk import BitTeamClient, MarketDataRecorder

recorder = MarketDataRecorder("market-observations.db")
async with BitTeamClient() as client:
    book = await client.get_orderbook_snapshot("DEL_USDT")
    print(book.spread, book.depth("bids", levels=20))
    await recorder.record_snapshot(book)
    sub = await client.subscribe_orderbook("DEL_USDT")
    try:
        async for event in sub:
            await recorder.record_event(event, symbol="DEL_USDT")
    finally:
        await sub.close()
```

Для периодических полных снимков: `await recorder.capture_orderbook(client, symbol, duration=60, interval=1)`. duration ограничивает получение новых снимков; уже начатая атомарная SQLite-запись завершается перед возвратом. max_samples ограничивает ресурсы. `await recorder.load(symbol, kind="l2_snapshot", start_ms=..., end_ms=..., limit=...)` читает локальный диапазон. Для сырых событий kind="raw_orderbook".

Raw publications имеют is_snapshot=False. Без доказанного начального sequence ID и правил пропусков SDK не объявляет полученный delta полным стаканом. Он не восстанавливает прошлое состояние из сегодняшнего snapshot и не превращает raw-записи в выдуманную server-side историю. При overflow/disconnect требуется новый snapshot и resubscribe.

## WebSocket сайта

Рабочий адрес: `wss://bit.team/trade/ws/`, nes v2. Старый `wss://bit.team/trade/api/` из части конфигурации возвращал 404. Market GET RPC также возвращал 404, поэтому snapshots остаются HTTP-методами.

```python
tickers = await client.market.subscribe_tickers()
pairs = await client.market.subscribe_pairs()
balances = await client.account_streams.subscribe_balances()
orders = await client.account_streams.subscribe_orders()
deals = await client.account_streams.subscribe_user_trades(pair_id)
notifications = await client.account_streams.subscribe_notifications(user_id)
```

Market socket анонимный и не содержит cookies аккаунта. Private socket берёт spot Bearer, проверяет owner origin, состояние и lifecycle; client.refresh выполняет reauth открытого socket. После автоматического refresh в другом REST-вызове можно явно вызвать account_streams.reauthenticate(); итератор также проверяет поколение перед ожиданием. Logout/clear через client закрывают account socket.

Найдены также chat GET/POST RPC и notification read RPC. Они реализованы как явные методы account_streams, но при live-проверке сообщения не отправлялись и уведомления не менялись. ACK приватной подписки не доказывает получение события, если аккаунт в этот момент не совершает операций.

## P2P и дополнительные сервисы

```python
coins = await client.site.get_coins()
adverts = await client.site.get_advertisements(type_="buy", coin="BTC", fiat="RUB", limit=10)
rates = await client.site.get_rates_by_period(coin_id, currency_id, type_="day", period=1)
news = await client.site.get_news_posts(page=1, per_page=20)
payload = await client.p2p.get_accounts()
```

`client.p2p.call(operation, path={}, params={}, data={})` и именованные wrappers используют schemas/p2p_site.json. Общая API-v2 cookie access_token не заменяется spot access или Basic. Автоматический refresh общей P2P-авторизации не выдуман: при её истечении вызывающий код должен пройти новый вход, если сервер этого потребует.

Некоторые GET P2P принимают сделки, подтверждают вывод, отправляют монеты, создают кошельки или меняют настройки. Поэтому ни один такой вызов не выполняется автоматически или как generic read-only smoke, и P2P-запросы никогда не повторяются. Неизвестные body-схемы остаются explicit raw dict, а не считаются полностью проверенной спецификацией. Публичные объявления могут содержать платёжные реквизиты - SDK их не логирует.

Блог содержит опубликованный discovery link `https://bit.team/blog/wp-json/`; его index подтвердил posts/categories. RSS-ссылка присутствует, но feed отвечал 404, поэтому новости получаются через проверенный JSON API.

## Разные токены и сети вывода

```python
networks = await client.get_withdrawal_networks("USDT")
plan = await client.prepare_withdrawal("USDT", amount="10", address=destination, network="TRC-20")
# plan только готовит данные; запрос к withdraw endpoint ещё не отправлялся.
# Явная отправка заявки, если она нужна приложению:
request = await client.request_network_withdrawal("USDT", amount="10", address=destination, network="TRC-20")
```

Проверенный spot-контракт USDT: один currencyId=3; ERC-20 ->currency="eth", TRC-20 ->"trx", BEP-20 ->"bnb". SDK берёт актуальный id/сети/комиссии/лимиты из /currencies, а не фиксирует id в коде. Для мультисетевого токена выбор network обязателен. Native-токену не придумываются сети, которых нет в каталоге. Отдельные токены/сети - отдельные заявки; атомарный batch не подтверждён.

P2P использует другой механизм: currency_id выбранного дочернего кошелька. USDT parent38/child44/63 из P2P нельзя отправлять как spot currencyId. Дополнительные P2P-сети могут быть скрыты в общем каталоге; актуальная доступность определяется кошельками и ограничениями аккаунта. Catalog-active не означает per-account withdraw-enabled. Memo/tag и произвольные сети не подставляются без подтверждённого контракта.

Проверена только подготовка сетевых payload и чтение каталогов. Реальные заявки вывода и подтверждения не отправлялись.

## Проверки

EXTENDED_CHECKS.json содержит обезличенный результат нового live-прогона. SITE_INVENTORY.md и API_REFERENCE.md описывают источники и недоступные области. Локальные тесты используют HTTPS/fakes, проверяют новые протоколы, пути, точность Decimal, лимиты, isolated auth и отсутствие скрытых финансовых вызовов. Число локальных тестов не является числом живых проверок приватных endpoint.
