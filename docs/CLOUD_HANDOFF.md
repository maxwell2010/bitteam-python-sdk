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

Последний полный локальный результат: **1295 passed, 1 native Windows DPAPI
skip**, 1296 collected, Linux Python 3.12.14; skip audit прошёл.
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
Поздняя точечная spot-selector correction описана ниже. CIqueued снаружи указыватьpending, неsuccess.

Spot-selector correction: неизвестный USDT selector и multi-network non-USDT без доказанного selector отклоняются planner-ом до submit. Метаданные каталога доступны; новые сети/arb/baseSymbol не добавлены. Три подтверждённых USDT mapping и single-native сохранены. Финальный full1295passed1nativeDPAPI skip, skip audit passed;18новых pure/fake-dispatch регрессий, независимый review. CI нового head при внешнем queued отмечать pending.

## Storage/optional/CI follow-up (2026-11-04)

Actual isolated SQLite and PostgreSQL runtime checks now cover memory lifetime,
init cleanup, transactional retention and per-series database serialization.
retention=None explicitly preserves history; rolling default2000 is unchanged.
Real pandas/Plotly checks cover empty OHLCV and headless returned Figure; fresh
core-only venv source smoke confirms optional packages remain optional. Static
tracked-path/link checks repair canonical README without building the SDK.
Detailed versions, evidence and limits: docs/TEST_GAPS.md.

PR/main CI remains enabled, feature push duplication removed, concurrency added;
new independent PostgreSQL-service and fresh-core-source jobs supplement the
8 OS/Python jobs. Old 1cbb855 runs are now completed/failure, not queued: both
Python3.10 jobs used unavailable Task.cancelling in a test; the assertion was
made portable. Old queue cause remains unknown. Use API evidence for the new
exact SHA; do not infer success from local counts or an older run. No versions,
builds, releases, real account calls, user cache reads or SDK installation.

Final targeted real-PG two-pool retention=1 barrier test did not reproduce the
race with current advisory serialization; different-key parallelism and cancel
recovery passed. Standalone runtime:12 checks passed; full pytest:1362 passed,
1 nativeDPAPI skip, skip audit passed. Core-only source smoke passed, not wheel.
