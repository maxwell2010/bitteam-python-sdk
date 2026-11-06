# BitTeam Python SDK 1.7.0

Асинхронный независимый SDK BitTeam для Python 3.10+: публичный рынок,
REST/WebSocket, история свечей, API-ключи и пользовательская SessionAuth,
локальное хранение и графики. Это не официальный продукт биржи.

## Установка

Из корня клонированного репозитория, в своём virtualenv:

```sh
python -m pip install .
```

Core: aiohttp и certifi. По необходимости добавьте независимые extras:

```sh
python -m pip install ".[charts,sqlite,postgres]"
```

Готовые wheel/sdist и исходный архив:
[GitHub Release 1.7.0](https://github.com/maxwell2010/bitteam-python-sdk/releases/tag/v1.7.0).
[Изменения](CHANGELOG.md). Лицензия не задана (license unspecified).

## Первый пример без сети

Подготовка демонстрационного P2P payload не обращается к аккаунту и не отправляет
заявку. ID и адрес здесь условные, они не подтверждают доступность валюты/сети:

```python
from bitteam_sdk import prepare_p2p_withdrawal

plan = prepare_p2p_withdrawal(44, address="example-destination", amount="1.0000")
assert plan.operation == "create_withdrawal_body"
```

[Первый публичный запрос: тикер, стакан и свечи](docs/EXAMPLES.md#публичные-тикер-стакан-и-свечи)
не требует аккаунта или API-ключей и выполняет сетевые чтения при явном запуске.

## Руководства

- [Вход, TOTP/device challenge, CLI/GUI, кэш, resume и logout](bitteam_sdk/ACCOUNT_CHECK.md)
- [Примеры: тикер/стакан/свечи, API-key balance, history/recovery, storage/charts, read-only tracking](docs/EXAMPLES.md)
- [Каталог REST API](bitteam_sdk/API_REFERENCE.md)
- [Каталог P2P/API-v2](bitteam_sdk/P2P_REFERENCE.md)
- [P2P read-only сценарии и подготовка payload](docs/P2P_READ_WORKFLOWS.md)
- [Восстановление потоков и его ограничения](bitteam_sdk/RELIABILITY.md)
- [Чтение и отслеживание существующего вывода](bitteam_sdk/WITHDRAWAL_TRACKING.md)

API-ключи и SessionAuth имеют разные права и маршруты. Штатный зашифрованный
session cache привязан к текущему пользователю Windows DPAPI. SDK не обещает
общий API-v2 renewal, доставку OTP, replay, атомарный L2 или финансовую finality.
Наличие endpoint в каталоге не означает его live-проверку. Не храните ключи,
токены, cookies, профили, приватные ответы и отчёты в Git.

## Для разработчиков

```sh
python -m pip install -r requirements-sdk-dev.txt
python -m pytest -c tests_sdk/pytest.ini tests_sdk -ra --junitxml=sdk-test-results.xml
python scripts_sdk/check_test_skips.py sdk-test-results.xml
python scripts_sdk/check_source_docs.py
```

Обычный pytest использует synthetic/fake/loopback данные с runtime guard против
внешних Python socket операций. Он не является ограничителем collection,
subprocess или native I/O. Реальный account login и финансовые операции для
проверки примеров не требуются.

[Исторические отчёты, исследования и CI-хронология](docs/archive/README.md)
отделены от руководств. [Фактическая матрица ограничений](docs/TEST_GAPS.md)
сохраняет provenance прежних наблюдений.
`python scripts_sdk/package_source.py` печатает публичный inventory без создания
архива. Manifest и planner включают Markdown из `docs/`, включая новые руководства.
