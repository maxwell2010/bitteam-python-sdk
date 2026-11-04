# Продолжение проверки в Codex Cloud

Repository: https://github.com/maxwell2010/bitteam-python-sdk
Branch: main. Read AGENTS.md before making changes.

Пользователь запретил новые версии, релизы и выпуск сборок до завершения проверки. Не меняйте версию, не создавайте теги, GitHub Releases, PyPI publications либо distributions. Push/PR CI запускает только tests+JUnit. Не запускайте manual verify_distribution.

## Подготовка

Из корня репозитория:

```sh
python -m pip install -r requirements-sdk-dev.txt
python -m pytest -c tests_sdk/pytest.ini tests_sdk -ra --junitxml=sdk-test-results.xml
python scripts_sdk/check_test_skips.py sdk-test-results.xml
```

CI на Windows/Linux Python3.10-3.13 прошёл, run41847439819. Локально 707passed после текущего аудита. Следуйте docs/TEST_GAPS.md: неизвестные статусы не означают успех, каталоги endpoint не равны live verification.

## Ограничения аккаунта

Пароли, cookies и токены в репозитории отсутствуют. Локальный DPAPI profile main удалён по запросу пользователя. WindowsDPAPI не переносится в LinuxCloud. Автоматически восстанавливать credentials или запрашивать их в публичном issue нельзя. Не выполнять реальные ордера/выводы/подтверждения, не отправлять коды и не менять настройки аккаунта. Допустимы synthetic tests и отдельно ограниченные public read-only проверки.

## Оставшиеся внешние проверки

- Связь spot withdrawal orderId с transaction.id не доказана.
- Delivery Telegram device-login и долгосрочное истечение/отзыв refresh не проверены в реальном аккаунте.
- Некоторые market/docs/archive endpoints ранее были недоступны. Не выдавать зарегистрированный контракт за успешный live endpoint.
- Private financial routes требуют отдельного пользовательского сценария; offline tests не доказывают исполнение биржей.
- Reconnect показывает gap, не обещает replay либо атомарную L2-синхронизацию без доказанного sequence-id.

Продолжайте исправлять только воспроизводимые ошибки с независимыми регрессиями и обновляйте матрицу evidence. Не объявляйте отсутствие всех ошибок по количеству тестов.
