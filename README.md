# BitTeam Python SDK - development

Асинхронный Python SDK BitTeam: API-ключи и пользовательский вход, 2FA, cookies, refresh, REST, WebSocket, исторические свечи, стаканы, P2P и отслеживание заявок вывода.

**Проверка продолжается. Выпуск новых версий и сборок заморожен по запросу пользователя.** Публикация исходников не является релизом.

- [Каталог REST API](bitteam_sdk/API_REFERENCE.md)
- [Матрица проверок и открытые вопросы](docs/TEST_GAPS.md)
- [Восстановление потоков и история](bitteam_sdk/RELIABILITY.md)
- [Отслеживание вывода](bitteam_sdk/WITHDRAWAL_TRACKING.md)
- [Сохранённая legacy-документация](bitteam_sdk/LEGACY_README.md)

```sh
python -m pip install -r requirements-sdk-dev.txt
python -m pytest -c tests_sdk/pytest.ini tests_sdk -ra
```

Тесты используют синтетические аккаунтные ответы. Реальные торговые операции и вывод средств не выполняются. Наличие метода в каталоге не доказывает успешную проверку приватного endpoint на бирже. Это независимый SDK, не официальный продукт биржи.


Подготовка P2P payload без HTTP и доступа к аккаунту:

```python
from bitteam_sdk import prepare_p2p_withdrawal, prepare_p2p_internal_transfer

withdrawal = prepare_p2p_withdrawal(44, address="example-destination", amount="1.0000")
internal = prepare_p2p_internal_transfer(7, "2.0000")
assert withdrawal.operation == "create_withdrawal_body"
assert internal.payload["internal_request"] is True
```

Это только чистые планы: они не отправляют заявки и не подтверждают доступность
валюты, сети или адреса. API-v2 currency_id нужно выбирать по отдельно проверенным
данным аккаунта; ID не заменяет spot currencyId. Форма вывода currency_id=95
с неизвестным date/hash не поддерживается стандартным планом.

`python -m bitteam_sdk.example` читает публичные данные при явном запуске.
`python -m bitteam_sdk.auth_example` - интерактивный сценарий с побочными
эффектами входа, отправки device-кода при необходимости и logout. Это не
read-only probe; реальные аккаунтные примеры во время текущей проверки не
запускаются.

Хранилище свечей по умолчанию оставляет последние **2000 строк на точную пару
`(symbol, interval)`**. Для сохранения всей поступающей истории явно задайте
`retention=None`; это не обещание полноты истории биржи. `get_klines(limit=...)`
отдельно ограничивает чтение последних строк и возвращает их по времени.
Пример без HTTP и файлов:

```python
import asyncio
from bitteam_sdk.models import Kline
from bitteam_sdk.storage import get_storage

async def main():
    storage = get_storage("sqlite", path=":memory:", retention=None)
    await storage.init()
    try:
        await storage.save_kline(Kline("SYNTH_USDT", "1m", 0, "1", "2", "1", "1", "1"))
        rows = await storage.get_klines("SYNTH_USDT", "1m", limit=3000)
        assert len(rows) == 1
    finally:
        await storage.close()

asyncio.run(main())
```

SQLite `:memory:` существует до `close()`. PostgreSQL использует отдельный
локальный сервер и зависимость `asyncpg`; runtime-проверка выполняется командой
`python scripts_sdk/check_storage_runtime.py --postgres-dsn <synthetic-loopback-dsn>`
только на изолированной тестовой БД. Скрипт создаёт и удаляет собственную UUID-схему.
Это отдельная реальная интеграция, не mock из общего pytest.

График без браузера и сетевого renderer:

```python
from bitteam_sdk import BitTeamClient
from bitteam_sdk.models import Kline

frame = Kline.to_dataframe([[0, "1", "2", "1", "1.5", "3"]])
figure = BitTeamClient.plot_klines(frame, show=False)
assert figure.data[0].type == "candlestick"
serialized = figure.to_json()
```

Пустая DataFrame сохраняет OHLCV-схему и DatetimeIndex. Индекс остаётся
timezone-naive UTC; порядок и дубликаты входа не исправляются автоматически.
Числовая DataFrame пригодна для анализа/графиков, но может округлять decimal:
для точных денежных значений сохраняйте исходные строки Kline/хранилища.
