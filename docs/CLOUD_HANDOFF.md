# Продолжение проверки BitTeam SDK в Cloud

Repository: https://github.com/maxwell2010/bitteam-python-sdk
Base: main. Единственная рабочая ветка: fix/cloud-lifecycle-timeouts.
Единственный draft PR: https://github.com/maxwell2010/bitteam-python-sdk/pull/1
Не merge и не включать auto-merge. Сначала читать AGENTS.md и docs/TEST_GAPS.md.

## Заморозка и безопасная проверка

До нового явного указания пользователя запрещены версии, теги, релизы,
wheel/sdist и публикации. Не запускать manual verify_distribution.
Не выполнять реальные аккаунтные/финансовые запросы, подтверждения, отправку
кодов или изменение настроек. Реальные cookies/токены/profile main удалены;
не восстанавливать и не запрашивать их. Пользовательский cache не трогать.
Тесты используют синтетические данные, fake RAM cache/HTTP/WS и локальный HTTPS.

```sh
source /workspace/venvs/bitteam-sdk/bin/activate
python -m pytest -c tests_sdk/pytest.ini tests_sdk -ra --junitxml=work/sdk-test-results.xml
python scripts_sdk/check_test_skips.py work/sdk-test-results.xml
```

Последний полный локальный результат: **1277 passed, 1 native Windows DPAPI
skip**, 1278 collected, Linux Python 3.12.14; skip audit прошёл.
Обычный sandbox запрещает локальные sockets; для HTTPS-фикстур нужен только
доступ исполнителя к локальным тестовым сокетам, без расширения HTTP allowlist.
Точный финальный SHA/run/наблюдённый статус CI записываются в описании PR после
проверки GitHub API. Старые успешные runs не заменяют проверку нового head.
Push/PR запускает tests/JUnit/skip audit, сборки должны быть skipped.

## Основные изменения и границы

- SessionAuth проверяет реального владельца до save/load/login/logout/refresh,
  cookie/token/cache side effects и внутри scheduled операций. Stale A может
  очистить свою память, но не jar и потенциально общий cache/profile B.
- Замена REST.auth отменяет старую tracked работу и отделяет HTTP session/jar;
  поздний Set-Cookie остаётся в старом jar. Retired cleanup защищён от отмены,
  concurrent close ждёт завершения, ошибки закрытия не превращаются в success.
- Held P2P/account-stream/archive ссылки проверяют owner identity, включая
  queued dispatch и iterator resume. Same-owner refresh и anonymous public
  resources сохранены; legacy duck transport tests не ослабляют real-owner guard.
- HTTP401 в P2P - ошибка конкретного запроса, без blacklist/clear/spot refresh/
  replay. Same-cookie независимый read допустим. General renewal не доказан.
- Standard form body, legacy query-helper и internal stock transfer - разные
  callsites. Pure планы не делают HTTP. Internal_request transfer не только95;
  другая95/date/hash форма остаётся raw, её hash не вычисляется.
- Каталог содержит84операции (61helper+23derived), а не весь сайт.16 RAM fixed
  callsites, internal-transfer и2journal пути имеют source/offset/chain provenance
  от локального reviewer. Public SiteAPI дубли не считаются новыми.
- Journal export ограничен page1/limit999, type amount/system; произвольные
  фильтры, general pagination и retention не доказаны. ui_state отражает UI
  labels отдельно: основной state1 pending, state2 unknown, не finality.
- Market/history malformed envelopes, timestamp truncation и ambient Decimal
  rounding исправлены; reconnect не обещает replay или atomic L2.

## Внешние блокеры

Первичные frontend-факты переданы пользователем от локального static/RAM review;
cloud не скачивал полные JS/не пересчитывал hashes. Ограниченная10-JS выборка и
последующий targeted trace не означают all-site coverage. Public-only локальные
probes дали timeouts/HTML502, не постоянную недоступность и не валидность параметров.
Не проверены live account expiry/renewal/revocation/delivery, права и финансовые
исходы, полные body-схемы raw mutations,95-form date/hash, связь orderId и spot
transaction.id, blockchain finality, journal retention и replay. Подробная
матрица, источники и red/green: docs/TEST_GAPS.md, SITE_INVENTORY.md,
WITHDRAWAL_TRACKING.md и docs/P2P_READ_WORKFLOWS.md.


Последний targeted epoch review: A -> B -> A действительно оживлял старые
ответы/подписки при неизменном lifecycle. Успешный detach теперь увеличивает
lifecycle прежнего SessionAuth до cancel, не очищая token/cache/generation и
не копируя jar. Identity guards сохранены; fresh запросы/refresh/подписки
вернувшегося A допустимы в новой эпохе. Шесть новых регрессий и независимый
review прошли. Финальный полный результат1277passed1DPAPI skip, skip auditpassed.
После этого новых направлений нет. CIqueued снаружи указыватьpending, неsuccess.
