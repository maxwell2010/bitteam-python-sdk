> Исторический материал: даты, результаты и состояние сессии ниже относятся только к описанным этапам.
> Это не текущий статус кэша, backend или публикации. Прежний freeze завершён; релиз 1.7.0 опубликован.
> [Руководства](../README.md#руководства) - [архив и исследования](../docs/archive/README.md).


# BitTeam Python SDK 1.6.0

Самостоятельный асинхронный Python SDK на основе наших клиентов trading_terminal_codex, BitTeamBridge, BitTeamApp, прежнего bitteam_sdk и актуальной документации BitTeam. Python 3.10+, aiohttp, проверка TLS.

Расширенные возможности, примеры и ограничения: [FULL_COVERAGE.md](FULL_COVERAGE.md). Каталог методов сайта P2P: [P2P_REFERENCE.md](P2P_REFERENCE.md).

## Установка

Из каталога с pyproject.toml:

```powershell
python -m pip install .
python -m pip install ".[sqlite]"
python -m pip install ".[charts]"
```

Также можно установить готовый wheel `bitteam_python_sdk-1.6.0-py3-none-any.whl`. Пакет не включает пароли, .env, рабочие базы данных, кэш сессии и логи сервисов. Зависимости графиков, SQLite и PostgreSQL подключаются отдельно.

## Что включено

- Публичные пары, валюты, курсы, стаканы, сделки, тикеры и точности.
- API-ключи и пользовательский вход: email/password, Google 2FA, подтверждение устройства кодом из почты или Telegram, cookies, refresh, logout.
- Лимитные, рыночные и условные ордера, отмена одного/всех ордеров, активные ордера, история и сделки пользователя.
- Кошельки, адреса пополнения, транзакции, вывод и отдельные шаги его подтверждения.
- Именованные низкоуровневые методы для профиля, настроек, API-ключей, P2P, верификации, реферальной статистики и остальных клиентских маршрутов Swagger.
- Исторические свечи и подписки через рабочий публичный WebSocket `wss://history.bit.team/api/`, протокол nes v2.
- Построение OHLCV из публичных сделок, точная десятичная арифметика при агрегации, дедупликация, без искусственных свечей в пустых интервалах.
- SQLite/PostgreSQL для свечей; обновление формирующейся свечи и получение последнего окна истории. DataFrame и графики через optional extras.
- Проверка известных параметров, контролируемая пагинация, ограничение частоты и обработка ошибок без вывода секретов.

В каталоге **110 операций** официального Swagger: **106 клиентских** и **4 серверных/dev**, которые перечислены, но недоступны для исполнения из SDK. Наличие маршрута в каталоге означает покрытие схемы, а не подтверждённую работу на реальном аккаунте. Полный список: [API_REFERENCE.md](API_REFERENCE.md).

## Публичные данные без ключей

```python
import asyncio
from bitteam_sdk import BitTeamClient

async def main():
    async with BitTeamClient() as client:
        pairs = await client.get_trading_pairs()
        ticker = await client.get_ticker("DEL/USDT")
        book = await client.get_orderbook("DEL_USDT", limit=20)
        trades = await client.get_trade_history("DEL_USDT", limit=100)
        candles = await client.get_klines("DEL_USDT", "15m")
        # Это свечи, построенные локально из доступных публичных сделок:
        derived = await client.get_candles_from_trades("DEL_USDT", "1m")

asyncio.run(main())
```

`get_ticker()` берёт bid/ask из стакана, а не из последней покупки/продажи. Денежные поля нормализованного тикера имеют тип Decimal. Низкоуровневые методы сохраняют исходные JSON-структуры dict/list.

## API-ключи

```python
from bitteam_sdk import BitTeamClient, ApiKeyAuth

async with BitTeamClient(auth=ApiKeyAuth(api_key, api_secret)) as client:
    await client.init()
    balance = await client.get_balance()
    active = await client.get_open_orders("DEL_USDT")
    history = await client.get_user_orders(limit=100, offset=0, order_type="history")
    trades = await client.get_user_trades(pair="DEL_USDT")
```

Сохранены `BitTeamClient(api_key, api_secret)` и именованный alias `private_key=...` из наших сервисов. `init()` проверяет ключи. Методы `client.api` могут использовать ключи напрямую, без init. Публичные запросы не получают Authorization, режим ключей не использует cookies аккаунта.

## Email/password, 2FA, почта и Telegram

```python
from bitteam_sdk import BitTeamClient, SessionAuth, AuthState

async with BitTeamClient(auth=SessionAuth()) as client:
    result = await client.login(email, password)
    if result.state == AuthState.TWO_FACTOR_REQUIRED:
        result = await client.submit_totp("012345")
    if result.state == AuthState.DEVICE_CONFIRMATION_REQUIRED:
        await client.send_device_code()
        result = await client.confirm_device(device_code, remember=True)
    if result.state == AuthState.READY:
        balance = await client.get_balance()
        await client.logout()
```

Порядок подтверждений зависит от ответа сервера. После 2FA может понадобиться подтверждение устройства. Google-код состоит из шести цифр; device-код из почты или Telegram - из четырёх. Передавайте коды строками; leading zeros TOTP сохраняются. Неправильный код вызывает исключение, текущий шаг остаётся доступен для повторного ввода.

В официальном коде есть шаблон `authorize_new_device_telegram`. Веб-клиент отправляет только uid в `/authorize/send-code`: параметр выбора канала не найден. Канал определяет сервер BitTeam. SDK принимает код из любого канала одним методом, не читает почту/Telegram и не меняет настройки доставки. `LoginResult.delivery_channel` равен None, если сервер не прислал известное значение в optional metadata; наличие этого поля в успешных ответах не подтверждено.

`EMAIL_CONFIRMATION_REQUIRED` означает необходимость подтвердить регистрацию на сайте и начать вход заново. Дополнительные проверки сайта, включая CAPTCHA после неудачных попыток, могут требовать ручного входа. Интерактивные шаги выполняйте последовательно.

Для локальной проверки реального аккаунта без торговли:

```powershell
python -m bitteam_sdk.auth_example
python -m bitteam_sdk.auth_example --api-keys
```

Для полной локальной проверки аккаунта с обычными полями ввода Windows:

```powershell
python -m bitteam_sdk.account_check --window-input --report output-sdk/account-check/report.json
```

У формы есть кнопка вставки, Ctrl+V с учётом русской раскладки, Shift+Insert, счётчик символов и значок глаза для показа/скрытия пароля и кодов. Проверка имеет отдельный allowlist только для входа, подтверждений, чтения баланса, refresh и logout. Баланс читается до и после refresh; секреты и суммы в отчёт не попадают. 2FA запрашивается только если она включена в аккаунте, согласно ответу BitTeam.

Пароль и коды по умолчанию вводятся скрыто и не сохраняются. Вход реального аккаунта, Google 2FA, код из почты, чтение баланса, refresh и logout проверены. Подтверждение через Telegram поддержано тем же методом, но реальная доставка Telegram в этих проверках не использовалась. Общие cookies access_token/refresh_token успешно обмениваются на spot-сессию без переименования.

## Сохранение сессии, восстановление и выход

```python
from bitteam_sdk import BitTeamClient, SessionAuth, SessionCache, AuthState

cache = SessionCache("main")
async with BitTeamClient(auth=SessionAuth(cache=cache)) as client:
    if await client.resume_session():
        balance = await client.get_balance()  # Без ввода почты, пароля и 2FA.
    else:
        result = await client.login(email, password)
        # При необходимости продолжите submit_totp()/confirm_device().
    # close()/выход из async with сохраняет активную сессию, не делает logout.
```

При переданном cache метод init() также пытается восстановить сессию. После login и каждого refresh новая пара токенов автоматически сохраняется. Восстановление по умолчанию проверяется чтением wallets; истёкший access обновляется через refresh. При окончательном отказе авторизации кэш удаляется и resume_session() возвращает False; при временной сетевой/серверной ошибке кэш сохраняется и исключение передаётся вызывающему коду. Учитываются и auth-коды внутри HTTP 200. Logout/clear отменяют незавершённые операции авторизации и validation GET, поэтому поздний ответ не восстанавливает сессию или cookies. Ожидающий такой ответ вызов может завершиться asyncio.CancelledError.

В Windows файл `%LOCALAPPDATA%/BitTeamSDK/sessions/main.bin` шифруется DPAPI текущего пользователя. Пароль, TOTP-секрет и одноразовые коды туда не записываются. Сохраняются токены, email и cookies внутри зашифрованного контейнера. Сроки cookies абсолютные: повторное открытие не продлевает их исходное истечение. Файл не включается в сборки SDK. Для других ОС требуется передать собственный OS-backed protector с protect(bytes)/unprotect(bytes); незашифрованного fallback нет. Основание: [Microsoft DPAPI](https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata).

Для разных аккаунтов/приложений используйте разные профили. Один профиль предназначен для одного активного клиента; межпроцессная координация одновременной ротации токенов не реализована. Сервер всё ещё может потребовать повторный вход при истечении refresh, отзыве сессии или изменении правил аккаунта.

```python
await client.logout()         # Серверный выход + удаление токенов/cookies/кэша.
await client.clear_session()  # Только локальная очистка, без запроса к серверу.
```

Очистка затрагивает данные авторизации этого профиля, не БД приложения или другие профили. Если серверный logout не подтверждён из-за ошибки сети, локальные данные всё равно очищаются, а ошибка передаётся вызывающему коду.

Команды для пользователя:

```powershell
python -m bitteam_sdk.account_check --window-input --cache-profile main --keep-session --report output-sdk/account-check/report.json
python -m bitteam_sdk.session_cli status --profile main
python -m bitteam_sdk.session_cli logout --profile main
python -m bitteam_sdk.session_cli clear --profile main
```

Первая команда сохраняет сессию после успешной проверки и при повторном запуске сначала использует кэш. Команда logout выполняет серверный выход и удаление кэша; clear только удаляет локальный файл. Обычный account_check без keep-session завершает проверку выходом, как раньше.

## Торговля и вывод

Методы SDK выполняют операции только при явном вызове. Пример формы вызова, не часть публичного demo:

```python
order = await client.create_order("DEL_USDT", "buy", type_="limit", price="0.01", amount="1")
await client.cancel_order(order_id)
await client.cancel_all_orders(pair_id=24)  # pair_id=0 означает все пары согласно API.
await client.create_conditional_order(pair_id=24, side="buy", amount="1", price="0.01", slippage=5)
```

Позиционный порядок прежнего SDK сохранён: `symbol, side, type_, price, amount`. В существующих сервисах встречался другой порядок, поэтому для amount/price используйте именованные аргументы. `strategy_id` относится к сервису стратегии и на биржу не отправляется.

Session endpoint требует price даже при type=market согласно текущей схеме; SDK не подставляет за пользователя произвольную цену. Для CCXT market-ордера price можно не передавать. Полные ограничения пары доступны через get_trading_pair_info; минимальный объём, шаги и доступность конкретного режима проверяются биржей.

Для session-вывода есть явные шаги:

```python
request = await client.request_withdrawal(currency_id=9, amount="1", address=address)
await client.send_withdrawal_email_code(order_id)
# Если требуется сервером:
await client.send_withdrawal_phone_code(order_id)
await client.confirm_withdrawal(order_id=order_id, email_code=123456, phone_code=1234, totp="012345")
```

`request_withdrawal` создаёт заявку, а confirm выполняется отдельно. `create_withdrawal(currency, address, amount, currency_id=...)` выбирает `/ccxt/withdraw` для ключей и `/withdraw/create` для session. Выбор network проверяется по актуальному каталогу; для USDT поддержаны ERC-20, TRC-20 и BEP-20. Memo без подтверждённого контракта отклоняется. Живые выводы и торговые операции в ходе тестирования не выполнялись.

Для истории без ограничения первой страницей:

```python
async for order in client.iter_user_orders(page_size=100, order_type="history", pair="DEL_USDT"):
    ...
```

Пагинация прекращается при короткой странице и обнаруживает повтор страниц. Это не атомарный снимок: во время обхода биржа может изменить историю. Ошибки не подменяются пустыми списками или публичными ордерами.

В наших сервисах встречались закрытые частичные ордера с `amount == filled`. Поэтому `marketdata.order_execution(order, original_amount=...)` сравнивает исполнение с исходным объёмом, сохранённым приложением при постановке. Без него partial может быть None; статус executed сам по себе не доказывает полное исполнение.

## Полный низкоуровневый API

```python
# Публичный метод:
payload = await client.api.get_cmc_orderbook_by_pair("del_usdt")
# Приватные методы с данными аккаунта:
payload = await client.api.get_user_stats_all(params={"limit": 100, "offset": 0})
payload = await client.api.post_set_options(data={"language": "RU"})
# Фильтры where/order сериализуются в where[field]/order[field]:
payload = await client.api.get_orders(params={"where": {"pairId": 24}, "order": {"id": "DESC"}})
```

Точные названия и маршруты - в API_REFERENCE.md. API-ответы возвращаются без преобразования формы. Для неоднозначных/неполных контрактов допустимы дополнительные query/body-поля, но SDK не выдумывает их значения. Managed endpoints login-auth/refresh/logout направляются в SessionAuth, чтобы не отправить access вместо refresh. Серверные webhook и `/dev/all-orders/cancel` не исполняются.

## Свечи и подписки

```python
candles = await client.get_klines("DEL_USDT", "15m", start=unix_seconds_from, end=unix_seconds_to)
sub = await client.subscribe_kline("DEL_USDT", "1m")
try:
    async for candle in sub:
        ...
finally:
    await sub.close()
```

Интервалы: 1m, 5m, 15m, 1h, 1d. Границы запроса задаются Unix-секундами, Kline.open_time возвращается в миллисекундах. По умолчанию запрашиваются последние сутки. Поддерживаются nes handshake, request, sub/unsub, heartbeat и фрагменты сообщений. Подтверждение подписки проверено на бирже; получение конкретного следующего события зависит от активности рынка.

При потере соединения/переполнении очереди возвращается ошибка. Автоматического незаметного reconnect нет: приложение должно переподключиться, повторно подписаться и сверить пропущенную историю. В 1.5.0 подтверждён рабочий торговый WebSocket `wss://bit.team/trade/ws/`: публичные цены, пары, стаканы, сделки; приватные подписки балансов, ордеров и сделок пользователя, включая reauth после refresh. Старый адрес `/trade/api/` для WebSocket не работает.

Optional helpers: `get_klines_df()` и `plot_klines()` требуют extras charts. SQLite/Postgres подключаются через `bitteam_sdk.storage.get_storage(...)`; PostgreSQL требует собственный сервер и extra postgres.

## Ошибки, cookies и обновление

Одна HTTP-сессия и cookie jar на аккаунт. JSON-токены spot устанавливаются атомарно вместе; cookies сохраняются с учётом домена/пути. Обычный запрос использует Bearer access; refresh отправляет Bearer refresh. Одновременные истёкшие GET-запросы объединяют refresh, затем повторяются не более одного раза. Подтверждённая auth-ошибка refresh очищает локальную сессию, в том числе при auth-коде внутри HTTP 200. При ошибке транспорта/5xx токены сохраняются.

Для GET на 429/503 выполняются ограниченные повторы с Retry-After/backoff. Количество задаётся `max_read_retries` от 0 до 5. Retry-After поддерживает секунды и HTTP-date. Если сервер требует ждать дольше max_retry_wait (по умолчанию 30 секунд), SDK возвращает ошибку с полным retry_after, не повторяя запрос раньше срока. POST/создание/отмена/вывод автоматически не повторяются. После неоднозначного timeout сначала сверяйте состояние на бирже. GET-операции с побочным эффектом, такие как создание адреса или Sumsub-заявителя, также не повторяются автоматически.

TLS проверяется, HTTP redirects не выполняются, Authorization не пересылается на неизвестный origin. Public WebSocket имеет отдельную сессию без cookies аккаунта. Исключения содержат статус и код без исходного тела с секретами. `logout()` очищает локальную сессию даже при ошибке серверного выхода; `close()` закрывает соединения без серверного logout.

## Проверки и известные ограничения

```powershell
python -m pip install ".[dev]"
python -m pytest -c tests_sdk/pytest.ini tests_sdk -q
python scripts_sdk/live_public.py
python -m build --wheel --sdist --outdir output-sdk
```

Локальные тесты используют HTTPS с проверкой сертификата, разными поддоменами, HTTP и nes-сервером; они не выполняют операции реального аккаунта. Проверяется и соответствие всех 110 операций каталогу Swagger. Отчёт: [TEST_REPORT.md](TEST_REPORT.md). Результаты реальных анонимных проверок: [LIVE_CHECKS.json](LIVE_CHECKS.json).

В реальном API обнаружены расхождения: `/stats` и `/markdown/menu` возвращают 500; Altyn banks/client требуют авторизацию вопреки PUBLIC в Swagger. Последние два SDK считает приватными. У Altyn payment в схеме отсутствует описание path-параметра; имя берётся из самого шаблона URL. Дополнительные недокументированные поля и фактические ограничения приватных методов требуют проверки аккаунтом.

Источники: [официальный Swagger](https://bit.team/trade/api/documentation), официальный JS авторизации и торгового клиента, локальные клиенты трёх сервисов. Snapshot Swagger включён в schemas/openapi.json. Регистрация аккаунтов, внутренний чат поддержки и блокчейн Decimal относятся к отдельным сервисам и не выдаются за API spot-биржи.

## Изменения

1.4.1 - 2026-11-03: независимое ревью тремя агентами и 20 новых регрессионных тестов. Исправлены lifecycle-гонки выхода, auth-коды HTTP 200, потеря кэша в неполной keep-session проверке, валидация ответа баланса и финализация отчёта, повторная подписка после revoke, фильтр get_orders и соблюдение Retry-After. Подробности: AGENT_REVIEW.md.

1.4.0 - 2026-11-03: DPAPI-кэш токенов/cookies, восстановление без пароля и кодов, автосохранение после refresh, logout с удалением кэша, локальная clear_session, CLI управления профилем, Ctrl+V/Shift+Insert и значок глаза. Проверено восстановление реального аккаунта в отдельном процессе.

1.3.1 - 2026-11-03: исправлен маршрут баланса SessionAuth на `/address/wallets`, используемый веб-клиентом; `/stock/balance` отвергает пользовательскую сессию даже после успешного refresh. Добавлена защищённая локальная проверка реального аккаунта с формами Windows, вставкой и счётчиком символов.

1.3.0 - 2026-11-03: полный каталог REST, публичный режим, методы сервисов, история/свечи/подписки nes, пагинация, явный вывод с подтверждениями, Decimal-агрегация, актуальные торговые маршруты, исправления хранения свечей и самостоятельная pip-сборка.

1.2.0 - 2026-11-03: API-key/session auth, 2FA, device-коды, cookies, refresh/logout, исправление блокировки rate limiter и тесты авторизации.


1.5.0 - 2026-11-03: история свечей по диапазону, торговые и приватные потоки, анализ и локальный архив L2, каталог сайта и P2P, новости, подготовка вывода с выбором сети. 479 локальных тестов; реальные проверки чтения и refresh описаны в EXTENDED_CHECKS.json.


1.5.1 - 2026-11-04: чтение существующих записей вывода и ограниченное ожидание с явным условием завершения. Подробности: [WITHDRAWAL_TRACKING.md](WITHDRAWAL_TRACKING.md).


1.6.0 - 2026-11-04: явное восстановление public/private WebSocket, исправления lifecycle и stale subscriptions, ограниченная история транзакций, осторожный разбор статусов и хеша, CI и проверка wheel в чистом окружении. Примеры и границы: [RELIABILITY.md](RELIABILITY.md).
