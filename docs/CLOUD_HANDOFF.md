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

Последний полный локальный результат: **1592 passed, 1 native Windows DPAPI
skip**, 1593 collected, Linux Python 3.12.14; skip audit прошёл (bounded reconciliation follow-up 2026-11-05).
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

CI at0e25d0c passed Linux4+PG+core; Windows found README-test default-codepage
UnicodeDecodeError. Explicit UTF-8 read fixes the test; Windows checks stay
unconditional. See PR for replacement SHA and actual final CI status.

Post20e230 static packaging review: MANIFEST now includes canonical rootREADME,
AGENTS and docs; legacy text retained. package_source.py now only plans public
paths/printsJSON, with main guard and no SDKimport/archivewriter/checksums.
Oldscriptneverexecuted. Setuptools FileList checks manifest without any build.
Standalone documentation checks use pure public inventory without Git and pass
on a plain copied tree/-I CLI. Focused30checks passed; finalfull/CI evidence for
replacementSHA belongs in PR#1. No archives/distributions/version changes.

Final source inventory fullsuite1388passed1DPAPIskip; skip auditpassed.
Focused30checks also passed from copiedstandalonetree without.git, noarchives.
See draftPR#1 for finalexactSHA and10-jobCI result; no merge/release.

## Возобновлённый audit 2026-11-05

Baselinef8ae6e0:1388passed1DPAPIskip+skipaudit; предыдущий10jobCI success.
Подтверждённые RAM-only исправления: гарантированный account_check transport
cleanup при save/step/cancel; WS SUB/UNSUB ACK lifecycle и old-ref identity;
session cleanup при socket-close error; общий awaitable Archive.close;
REST API-key owner epoch; очищенные transport/script/CLI diagnostics.
Actual Tk9.0/Xorgdummy:6syntheticGUI casespassed, productionGUIbugне найден;
Windows/RU-layout и аккаунтный2FA/logout не проверены. Xorg остановлен.
Подробная evidence matrix в TEST_GAPS. No successfulnewBitTeamliveverification/cache/account/finance;
freeze ZIP/wheel/sdist/SDKinstall/version/releases сохраняется. Новый exactSHA
и полный10jobCI проверять по PR#1, не подменять прежним f8ae6e0 success.

Финальный resumed full:1458passed1nativeDPAPIskip,1459collected;
skipauditpassed.70новыхрегрессий+independentcrossreview;actualGUI6 отдельно.
Старый failed-ACK fakefixture обновлён на явный replacement fake socket после
retirement,51relatedpassed; никаких liveгарантий из этого не выводить.

CI9822c15 matrix found fake script tests imported asyncpg before mocking;
actualPG12/corepassed. Teststubs now installedbeforeimport, no optionaldependency
added. Finalfull1458pass1skip with asyncpg explicitlyblocked+skipauditpassed;
independentreview14focusedpassed. ReplacementexactSHA/10jobs inPR#1.

## Authorization/recovery follow-up baseline772ee11

Guardedbaseline1458passed1DPAPIskip+skipaudit. Confirmedfixes: device numeric0
failclosed; atomicUID transition; retainedparentcancel when authchild ignores
cancel; closedhistoryref race; primaryerror preservation during hello/reconnect
cleanup; terminalaccountiterator no hiddenconnect. Newexplicit history.reconnect
returns pathmap andKlineStreamGap, no replay/boundsfetch/sequence promise.
Private secondSUBcancel/cleanup/originalrefsretry and generationreauthordering
passed as existingbehavior, notnewbackendcontracts. Defaultpytest nowruntime
Python DNS/TCP/UDP loopback-only guard+teardown detection; collection/nativeI/O/
subprocess limits explicit. Detailedmatrix TEST_GAPS and RELIABILITY.
No usercache/BitTeamlive/accounts/finance/OTP/build/install/version/release.
Finalfull/skip/newexactSHA10jobs must be checked separately in same draftPR#1.

Finalauth/recoveryfull1524passed1nativeDPAPIskip (1525collected),skipaudit and
sourcechecks passed. Permanentruntimeguard active throughout pytest,66newcases
plusindependentcrossreviews. Core-onlysource-I smoke34exports/4optionalsabsent
passed;no installedSDK/wheel. NewexactSHA10jobs inPR#1, don'treuse oldheadCI.

## Backfill/L2/auth follow-up baseline2bb21f1

Baseline1524pass1DPAPIskip+audit. Newexplicit recover_klines returns bounded
historytuple+newiterator separately;reconcile_book returns freshsnapshot+rawref,
continuity_guaranteed/events_applied bothFalse. No merge/completeness/replay/
atomicL2/serversequence claim. Reconnect invalidates all refs sharedconnection.
Fixedconfirmed latechallenge downgrade, ownedhistory/context errorprecedence,
ambientDecimalEmax/traps and live_extended diagnosticphase boundaries. Relogin
refresh/logout negativeprobes preserve newstate without productionchange.
GUI requires explicitdisposable-desktop; realglobalclipboard syntheticonly,
Windowsstep onlygithub-hosted existingmatrix (10jobs); actualCI stillseparate.
Stateful --account-profile mayrestore/refresh/persist/invalidatecache, neverrun
it duringaudit. No realcache/account/OTP/finance/live/install/build/release.

Final boundedreconciliationfull1592passed1nativeDPAPIskip (1593collected),
skipaudit/sourcepassed;core-I38exports/4optionalsabsent passed. LinuxactualGUI6
explicitflagpassed; verifyWindowsGUIstep/logs separately from overall10jobstatus.
Independentcrossreviewcomplete. Exactnewhead/CI remainsinPR#1; no build/merge.

c6f64e8 CIWindowsGUI reallyran andfailedfirstCtrlV (pytest1593passed each,
Linux4/PG/corepassed). Driver-onlyfocus/update/queuedkey +realclipboardreadback
added, no fakepaste/prodGUIchange;Linuxactual6+full1592pass1skip/audit passed.
ReplacementWindowsGUIstep/logs mustproveoutcome, notoldoveralljobassumptions.
