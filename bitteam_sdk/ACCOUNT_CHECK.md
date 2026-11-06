# Вход, проверка аккаунта и сохранение сессии

Это руководство по SDK. Для публичных котировок аккаунт не нужен:
[начало работы и примеры](../docs/EXAMPLES.md).

## Установка и выбор авторизации

Нужен Python 3.10 или новее. Из корня клонированного репозитория:

```sh
python -m venv .venv
```

Активируйте окружение: `.venv\Scripts\Activate.ps1` в PowerShell или
`source .venv/bin/activate` в bash. Затем:

```sh
python -m pip install .
```

Core устанавливает aiohttp и certifi. Дополнения независимы от способа входа:

```sh
python -m pip install ".[charts,sqlite,postgres]"
```

`charts` - pandas/plotly, `sqlite` - aiosqlite, `postgres` - asyncpg;
для PostgreSQL нужен отдельный сервер. Готовые wheel/sdist доступны в
[GitHub Release 1.7.0](https://github.com/maxwell2010/bitteam-python-sdk/releases/tag/v1.7.0).
Публикация в PyPI не предполагается этими командами.

| Режим | Для чего | Как начать |
|---|---|---|
| PublicAuth (по умолчанию) | Публичные рынок/история | `BitTeamClient()` |
| ApiKeyAuth | Приватный spot API с API-ключами | `BitTeamClient(auth=ApiKeyAuth(key, secret))`, затем `await client.init()` |
| SessionAuth | Пользовательский вход и доступные ему spot/API-v2/P2P методы | `login()` и необходимые подтверждения либо `resume_session()` |

API-ключи не заменяют пользовательскую сессию P2P. Права ключа и доступность
конкретного метода определяет сервер. Не выводите ключи, cookies, токены и
полный ответ баланса в журналы. [Пример API-key balance](../docs/EXAMPLES.md#баланс-по-api-ключам).

## Проверка через терминал или локальные окна

Запускайте только на своём компьютере и только если намерены войти в аккаунт.
Это stateful-сценарий: login, отправка device-кода при запросе сервера,
подтверждение, чтение баланса, spot refresh и logout. Торговых операций нет.
Отчёт содержит обезличенные этапы и атрибуты cookies, а не их значения;
храните его локально вне репозитория.

```sh
python -m bitteam_sdk.account_check --help
python -m bitteam_sdk.account_check --report ./private-reports/account-check.json
```

Для окон ввода нужен Tk и локальный графический desktop:

```sh
python -m bitteam_sdk.account_check --window-input --report ./private-reports/account-check.json
```

Ввод не передаётся агенту. Не запускайте эти команды в чужом или общем runtime.
Обычная проверка завершает сессию через logout. Чтобы сохранять её в Windows
DPAPI и при следующих запусках сначала пробовать resume:

```sh
python -m bitteam_sdk.account_check --window-input --cache-profile main --keep-session --report ./private-reports/account-check.json
```

`--keep-session` требует `--cache-profile`; при неполной проверке кэш может быть
сохранён, если авторизация уже дошла до READY. Проверяйте статус отчёта и явно
завершайте ненужную сессию. Оконный ввод не является отдельным способом шифрования.

## TOTP и код устройства

- Если сервер вернул `TWO_FACTOR_REQUIRED`, введите текущие 6 цифр из своего
  приложения TOTP (Google Authenticator или совместимого). SDK не генерирует
  код и не включает 2FA. При ошибке проверьте время устройства и актуальность кода.
- `EMAIL_CONFIRMATION_REQUIRED` означает необходимость подтвердить регистрацию
  на официальном сайте. Это другой этап, не device-код.
- При `DEVICE_CONFIRMATION_REQUIRED` вызов `send_device_code()` запрашивает
  отправку, а `confirm_device()` принимает 4 цифры. Сам вызов отправки не
  доказывает доставку.
- Параметра выбора email/Telegram у SDK нет. Канал определяется сервером и
  настройками аккаунта. `LoginResult.delivery_channel` сообщает только `email`
  или `telegram`, если сервер явно вернул это поле; иначе это `None`. Проверяйте
  фактическое получение в настроенном канале, не считайте текст приглашения
  доказательством Telegram-доставки. Исторически наблюдался email; гарантии
  backend-доставки, повторной отправки и сроков действия кода нет.

Cookies SDK получает из HTTP-ответов и передаёт с учётом домена/path. Вручную
копировать cookies из браузера или переименовывать общие токены в spot/P2P не нужно.
После общей авторизации методы `BitTeamClient.login/submit_totp/confirm_device`
сами открывают spot-сессию, когда это требуется.

## Полный пример входа с обработкой challenge

Пример выполняет вход и может отправить device-код, только когда вы явно
запускаете его. Он не создаёт кэш и в конце делает logout. Пароль и коды
вводятся скрыто. Не логируйте результат `get_balance()`.

```python
import asyncio
import getpass
from bitteam_sdk import BitTeamClient, SessionAuth, AuthState, BitTeamAPIError

async def main():
    async with BitTeamClient(auth=SessionAuth()) as client:
        try:
            result = await client.login(input("Email: ").strip(), getpass.getpass("Password: "))
            if result.state == AuthState.TWO_FACTOR_REQUIRED:
                result = await client.submit_totp(getpass.getpass("TOTP (6 digits): ").strip())
            if result.state == AuthState.DEVICE_CONFIRMATION_REQUIRED:
                delivery = await client.send_device_code()
                print("Server channel:", delivery.delivery_channel or "not specified")
                result = await client.confirm_device(
                    getpass.getpass("Received device code (4 digits): ").strip(),
                    remember=False,
                )
            if result.state != AuthState.READY:
                print("Complete this step on the official site:", result.state.value)
                return
            await client.get_balance()
            print("Balance read succeeded; values are not printed.")
        except BitTeamAPIError as error:
            print("API error:", type(error).__name__, "HTTP status:", error.status)
        finally:
            await client.logout()

asyncio.run(main())
```

`client.refresh()` обновляет **spot** пару токенов и сохраняет обновлённый кэш,
если он настроен. Это не подтверждение общего API-v2/P2P renewal, реальных
сроков expiry/revocation или бессрочности сессии. При недействительной общей
сессии нужен новый вход; не повторяйте login/отправку кодов бесконечным циклом.

## Кэш, resume и завершение работы

Штатный `SessionCache` использует DPAPI **текущего пользователя Windows**.
Файл по умолчанию: `%LOCALAPPDATA%\BitTeamSDK\sessions\<profile>.bin`.
Пароль и OTP в нём не сохраняются, но токены/cookies/email являются приватными.
Не переносите файл между пользователями, в Git, облачный runtime или отчёты.
На Linux/macOS стандартный конструктор выдаёт `SessionCacheError`: встроенного
переносимого protector нет. Используйте сессию без кэша или отдельно реализованный
OS-backed protector; plaintext/test protector не подходит для рабочего аккаунта.

Следующий полный пример для Windows восстанавливает **существующий** профиль,
проверяет его чтением баланса (стандартное `validate=True`), читает баланс и
обновляет spot токены. Если кэша нет/он истёк, пример завершится без нового login:

```python
import asyncio
from bitteam_sdk import BitTeamClient, SessionAuth, SessionCache, SessionCacheError, BitTeamAPIError

async def main():
    try:
        auth = SessionAuth(cache=SessionCache("main"))
        async with BitTeamClient(auth=auth) as client:
            if not await client.resume_session():
                print("No valid session. Run an explicit login on your computer.")
                return
            await client.get_balance()
            await client.refresh()
            print("Session restored; spot refresh succeeded.")
    except SessionCacheError:
        print("Cache unavailable, incompatible or damaged; inspect the profile locally.")
    except BitTeamAPIError as error:
        print("API error:", type(error).__name__, "HTTP status:", error.status)

asyncio.run(main())
```

`close()` закрывает transport и сохраняет READY-сессию при настроенном кэше;
он **не** равен logout. `resume_session(validate=False)` загружает кэш без
проверки его серверной действительности и не доказывает авторизацию.

Управление профилем на Windows:

```sh
python -m bitteam_sdk.session_cli --help
python -m bitteam_sdk.session_cli status --profile main
python -m bitteam_sdk.session_cli logout --profile main
python -m bitteam_sdk.session_cli clear --profile main
```

- `status` проверяет наличие файла, не валидность токенов.
- `logout` пытается завершить spot-сессию на сервере и очищает локальные данные.
  Если серверный logout не подтверждён, CLI сообщает об этом и возвращает ошибку.
- `clear` удаляет только локальный файл без серверного запроса. В уже работающем
  клиенте используйте `await client.clear_session()` для токенов/cookies/кэша
  либо `await client.logout()` для попытки серверного завершения и очистки.

При повреждённом файле, другом Windows-пользователе или несовместимой API
конфигурации resume может поднять `SessionCacheError`. Не редактируйте файл и
не извлекайте из него токены. После осознанной локальной очистки выполните новый
вход. `False` от resume не означает сетевую ошибку: кэш мог отсутствовать или
сервер мог признать сессию истёкшей; транспортные/прочие API-ошибки могут подняться.
Не выдавайте успешный refresh за подтверждение финансовых операций.

## Дальше

[Рабочие сценарии](../docs/EXAMPLES.md) - [REST](API_REFERENCE.md) -
[P2P read-only](../docs/P2P_READ_WORKFLOWS.md) - [границы восстановления](RELIABILITY.md).
[Исторический отчёт 2026-11-03](../docs/archive/ACCOUNT_CHECK_2026-11-03.md)
не является инструкцией и не сообщает о текущем наличии кэша.
