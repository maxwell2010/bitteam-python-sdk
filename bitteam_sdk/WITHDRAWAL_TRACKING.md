# Отслеживание вывода - SDK 1.5.1

Создание заявки, подтверждение пользователем, обработка биржей и включение транзакции в блокчейн - отдельные этапы. HTTP 200/ok после create или confirm не доказывает окончательный вывод. API-ключи используют /ccxt/withdraw; пользовательская сессия /withdraw/create и /withdraw/confirm. Нельзя автоматически переносить подтверждение сессии на API-ключи.

## Чтение существующей заявки

```python
record = await client.get_withdrawal_record(withdrawal_id, source="p2p")
# record.payload содержит исходный ответ. Не выводите его в общие логи.

transaction = await client.get_withdrawal_record(transaction_id, source="spot_transaction")
```

P2P использует GET /transactions/get-withdraw-by-id/{withdraw_id}. Спот использует GET /transaction/{id}. Для spot_transaction требуется известный ID транзакции из истории, а не orderId заявки. Автоматическое сопоставление этих идентификаторов пока не подтверждено. Чтение не создаёт, не подтверждает и не отменяет заявку. Чувствительный payload исключён из repr объекта наблюдения.

## Ожидание результата

```python
# is_finished должен проверять реальные поля ответа вашего контракта.
# SDK не задаёт вымышленные числовые коды статусов или txid-поля.
record = await client.wait_for_withdrawal(
    withdrawal_id,
    source="p2p",
    predicate=is_finished,
    timeout=300,
    interval=5,
    max_requests=60,
)
```

predicate - синхронная функция WithdrawalObservation -> bool. Она должна учитывать и отказ, если задача - дождаться любого конечного результата. True означает выполнение условия вызывающего кода, а не автоматически одобрение биржей. Истечение срока или лимита запросов даёт WithdrawalWaitTimeout с last_observation; ошибка сервера передаётся вызывающему коду без автоматического повтора. Отмена ожидания отменяет текущий запрос. Всё ожидание привязано к исходной сессии аккаунта: logout/login или замена auth прерывают его, включая проверку после predicate; обновление токена в той же сессии допустимо. При таймауте нельзя автоматически повторять создание заявки: исходная могла быть принята.

## Подтверждение пользователем

Для сессии существуют send_withdrawal_email_code(order_id), send_withdrawal_phone_code(order_id), confirm_withdrawal(order_id=..., email_code=..., phone_code=..., totp=...). Эти методы имеют побочные эффекты и не вызываются наблюдателем. TOTP используется, если этого требует аккаунт. Подтверждение логина через Telegram не доказывает поддержку Telegram при выводе.

Для P2P confirm_new_withdraw(path={"code": code}) - отдельный GET с побочным эффектом. Он никогда не применяется как проверка статуса. get_withdrawal_permission(currency_id) проверяет разрешение на вывод валюты, а не одобрение конкретной заявки.

Проверки 1.5.1 не отправляют реальных заявок, кодов или подтверждений. Точные production-статусы и связь spot orderId с transaction id не объявляются проверенными на аккаунте. Для подтверждения в сети нужен хеш из реального ответа и проверка в выбранной сети; SDK пока не выполняет проверку через обозреватель блокчейна.

Источник orderId подтверждён клиентом сайта: /withdraw/create возвращает response["result"]["orderId"]. В UI успешный confirm означает передачу заявки на рассмотрение; локальный success не является статусом блокчейна.

## Поля спотовой истории в клиенте сайта

Публичный archive chunk https://bit.team/_nuxt/b939415.js содержит UI parseStatus: строка передаётся как есть; числовой -1 отображается failed, 0 pending, остальные success. Это логика отображения, а не полный перечень кодов сервера. SDK не считает любой неизвестный числовой статус успешным.

UI строит ссылку обозревателя из links[].tx и params.tx_id. Для USDT дополнительно сопоставляет links[].blockChain с row.blockChain либо params.blockChain. При params.internalTransfer хеш скрывается: внутренний перевод может не иметь блокчейн-транзакции. Наличие tx_id само по себе ещё не доказывает нужное число подтверждений сети. В строках истории используется row.id; равенство этого ID и orderId заявки не доказано.


## P2P: статус 1 означает ожидание

Публичный компонент https://bit.team/p2p/_next/static/chunks/pages/Cabinet/Transaction-eb8de68add8165df.js для type=withdraw отображает -1 как cancelled, 0 как created, 1 как expect; остальные значения показывает success. Это UI mapping, не полный серверный enum: неизвестные значения нельзя автоматически принимать за успех. Детали используют id,type,status,created,sum,percent,coin. Хеш транзакции в этом компоненте не найден. Status=1 для P2P-вывода не является подтверждением завершения.

## Read-only P2P snapshot

client.inspect_p2p_withdrawal(existing_p2p_id) читает только доказанный payload.data. Requested ID и record ID доступны отдельно; неизвестный статус не означает успех. client.get_p2p_accounts() сохраняет account/user/total_usd без догадок о типах и валютах. Источники и offline-границы: docs/P2P_READ_WORKFLOWS.md.


## Отдельные новые frontend-контракты

Legacy create_new_withdraw с querycurrency_id не подменяется body-callsite
формы. prepare_p2p_withdrawal строит стандартный body безHTTP и отклоняет95;
поля public/commission_booster_name не трактуются. У другой формы
SpotAssetsTransfer отдельный bodycurrency_id,sum,internal_request:true для того
же stock endpoint: prepare_p2p_internal_transfer не ограничен95, не добавляет
address/date/hash и не требует/не придумывает response.data.id. Доступность и
результат перевода не проверены. Источники/ограничения: SITE_INVENTORY/schema.

Явный journal UI switch в3812-633d8d6f222bceb0.js offset6723 даёт метки
cancelled/created/confirmed/done для-1/0/1/2. TransactionEvidence.ui_state
хранит их отдельно от основного state:1pending,2unknown. Поле ui_state_source
содержит URL; raw_status и raw сохраняются. Unknown не повышается до success.
Это метки интерфейса, не exhaustivebackendenum и не blockchainfinality.
Фиксированные журналы имеют доказанное export-окно page1/limit999 и типы
amount/system; общая пагинация/retention/полнота истории не доказаны.
