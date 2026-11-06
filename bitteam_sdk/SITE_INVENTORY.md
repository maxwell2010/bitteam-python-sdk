> Исторический материал: даты, результаты и состояние сессии ниже относятся только к описанным этапам.
> Это не текущий статус кэша, backend или публикации. Прежний freeze завершён; релиз 1.7.0 опубликован.
> [Руководства](../README.md#руководства) - [архив и исследования](../docs/archive/README.md).

# Дополнительные API сайта BitTeam - 2026-11-03

Исследованы публичные HTML и текущие JS главной, trade и P2P. JS не исполнялся. Все проверки анонимные GET с включённой TLS-проверкой, без .env, аккаунта, cookies пользователя, торговых операций и перебора неизвестных URL. JSON содержит SHA-256 исходников, фрагменты и смещения, параметры тестов и формы ответов. Полные ответы объявлений и платёжные реквизиты не сохранялись.

## Рабочие публичные HTTP API, доступные для реализации

База: `https://api-v2.bit.team/api/v2`. Успешный envelope: `{status:true,data:...,message,code:200,errors:[],meta:...}`. Это другой контракт, чем spot `{ok,result}`. HTTP 200 сам по себе недостаточен: проверять status/code. Для локали использовать `Accept-Language: en` или `ru`; en-US на static menu дал 422.

| GET path | Проверенные параметры | Ответ data | Источник / статус |
|---|---|---|---|
| `/public/coins/list` | без параметров | list, 14 записей; key, base_currency_id, name, display_short_name, text, token_name, order, value, icon, is_visible, childrens, payment_details | trade JS, HTTP 200 |
| `/public/currencies/list` | без параметров | list, 13 записей; аналогичные поля | trade JS, HTTP 200 |
| `/public/rates-by-period` | coin_id=3, currency_id=2, type=day, period=1 | object с rates | main bc33dd8.js + trade store, HTTP 200; без type 422 |
| `/public/static-page/{project_id}/get-all-menu` | project_id=2; Accept-Language=en | list категорий id,name,slug,pages[]; внутри pages есть id/category_id/project_id/slug/title | trade store PROJECTID=2, HTTP 200; en-US дал 422 |
| `/public/static-page/{project_id}/{category_id}/{page_id}` | 2/1/41; IDs получены из меню | object id,lang,slug,title,description,keywords,link,content,project_id,category_id,status,created_at,updated_at,meta | trade JS, HTTP 200 |
| `/get/data-init-currency` | type=coin,token | list 15; key,name,display_short_name,text,order,value,additional | P2P _app JS, HTTP 200 |
| `/get/data-init-currency` | type=valute | list 11 fiat-валют, те же поля | P2P _app JS, первый GET200, повтор ReadTimeout |
| `/get/data-init-payment-method` | fiat_short_name=RUB | list43; key,text,value,type,code,photo,color,placeholder,regex,mask,validators | P2P _app JS, HTTP 200 |
| `/anunt/get-limit-percent` | без параметров | object sell_rate_percent_min/max, buy_rate_percent_min/max | P2P _app JS, HTTP 200 |
| `/anunt/get` | type=buy, limit=2, offset=0, coin_short_name=BTC, fiat_short_name=RUB | list2; user,type,advert_link_id,coin_id,coin,payment_id,payment_details,price_advert,currency_id,currency,limit_min,max,status,favorite,top; meta.count/meta.avg_price | P2P _app JS, HTTP 200 |

У `/anunt/get` в JS также есть payment_name, sum, orderBy, sortedBy и `filter[strict][users.is_online]=1`. Их значения/границы отдельно не проверены. Списки объявлений возвращают публичные данные продавцов и payment_details, в которых могут быть реквизиты. Не логировать полный ответ. Никакие объявления не принимались и сделки не создавались.

## Market, рейтинги и страницы монет

База, явно заданная в trade JS: `https://bitteam-market-back.bit.team/api/`.

| Метод и path | Контракт JS | Текущая проверка |
|---|---|---|
| GET `cryptocurrency/map` | limit=50/page=1 по умолчанию | limit=2/page=1 перенаправлен в `/chart.html`, вернулся HTML; это не успешный JSON API |
| GET `cryptocurrency/map/categories/{category}` | limit,page | найдено в JS, не вызывалось |
| GET `cryptocurrency/map` | tag,limit,page | найдено в JS, не вызывалось |
| GET `cryptocurrency/one/{alias}` | alias из страницы монеты | sample bitcoin: ReadTimeout; валидность alias не подтверждена ответом map |
| GET `cryptocurrency/historical/{coin}` | limit=50/page=1 defaults | sample bitcoin, limit2/page1: ReadTimeout |
| GET `market_pairs/coin/{coin}` | limit,page | sample bitcoin: ReadTimeout |
| GET `page/coin-meta/{coin}` | Accept-Language=en-US или ru-RU именно для этого backend | sample bitcoin: ReadTimeout |
| GET `core/common/cryptos` | без параметров | ReadTimeout |
| GET `core/common/markets` | без параметров | ReadTimeout |
| POST `cryptocurrency/chart` | JSON id,period | только обнаружено, не вызывалось по ограничению GET-only |

Сайт ссылается на `/price`, `/price/gainers`, `/price/losers`, `/price/most-visited`, `/price/trending`, `/currency/{alias}`. Прямой GET `/price/gainers` также завершился таймаутом. Эти страницы и JS-контракты не доказывают работоспособность backend. Не объявлять market HTTP методы рабочими до положительного JSON-ответа; не использовать status200 после redirect как успех.

## Документация, archive и новости

- GET `https://docs-api.bit.team/api/v1/pages?locale=ru&include=parent` - найден в trade JS, текущий ответ HTTP502 HTML. Search-вариант там же добавляет `filter[name]` и `fields[pages]=slug,name,parent`; отдельно не вызывался.
- GET `https://archive.bit.team/api/trades?limit=2&offset=0` - trade JS archive helper, ReadTimeout. Там же описаны private ordersByUser/tradesByUser, они не вызывались.
- `https://bit.team/blog/` - публичный HTML HTTP200. В навигации сайта новости ведут в этот блог (RU `/blog/ru`). Рабочий first-party JSON API новостей в проверенных файлах не подтверждён; WordPress-подобные или другие скрытые пути не перебирались.
- Главная и P2P ссылаются на `https://bit.team/docs` и legal/P2P страницы. Содержимое статических страниц доступно через проверенный API-v2 static-page menu/content выше.

## Источники и границы покрытия

1. `https://bit.team/_nuxt/9126db0.js` - общая конфигурация backend origins; coins/currencies, rates, статические страницы, market, docs и archive stores.
2. `https://bit.team/_nuxt/bc33dd8.js` - фактический вызов ratesByPeriod: coin_id,currency_id,type=day,period=1.
3. `https://bit.team/p2p/_next/static/chunks/pages/_app-3772cf9af2d461b9.js` - API-v2 baseURL, public P2P data-init и объявления.
4. HTML `https://bit.team/`, `/trade`, `/p2p`, `/blog/` - входные JS и навигация.

Сохранена форма ответов, не содержимое аккаунтов. Не проверены приватные API-v2/P2P, delivery/auth, P2P операции, платежи, выводы, новости JSON, пределы пагинации и неизвестные enum values. Особенно важно: в P2P есть GET с побочными эффектами `/operations/accept-operation`, pay-operation, send-coin-operation, cancel-operation и удаления/изменения объявлений. Они не вызывались и не должны попадать в generic read-only smoke suite.

## Уточнение: вывод в разных сетях

Публичный API-v2 coins/list подтверждает сетевые дочерние валюты. USDT: parent key/base_currency_id=38, token_name=ERC-20; children OMNI key29, TRC-20 key44, BEP-2 key62, BEP-20 key63. BNB: parent key53/token_name=BNB, child BNB(BSC) key61. У children есть дополнительные minimal/commission/digit/withdraw, но is_visible=false. Нельзя обещать доступность старой сети на основании одной записи каталога.

Форма найдена через публичный Next build manifest: `https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/Withdraw-56b2a70d301a037a.js`. Она строит сетевые вкладки из `account.token_name/currency_id`, `additional_wallets[{token_name,currency_id}]` и `possible_wallets[id]`. Выбор вкладки сохраняется в selectedCurrency. onSubmit разрешает его в currency_id и передаёт ровно в одну createNewTransaction. Прежнее приписывание этой форме legacy query-helper было ошибочным. По свежему public static-read локального координатора (2026-11-04) конкретный createNewTransaction callsite делает POST с currency_id в JSON body: `/account/create-withdraw`, а для числового currency_id=95 - `/account/create-withdraw-to-stock`. Legacy createNewWithdraw helper с query currency_id существует отдельно; это другой подтверждённый контракт, он сохранён без подмены. Отдельный network-параметр не установлен.

Следовательно, для P2P разные сети выбираются разными currency_id; разные токены/сети следует оформлять отдельными заявками. Возможность batch/атомарных или одновременных выводов не подтверждена. Это не основание использовать API-v2 IDs в spot API: namespaces и подтверждения различаются. Приватные wallet/account endpoints и любые выводы не вызывались; доступность конкретной сети, адреса и средства не проверялись.

## Конкретный private call site: P2P кошельки

В актуальном `_app-3772cf9af2d461b9.js` функция обновления Redux-профиля выполняет GET `/auth/user` через API-v2 с general bearer token. Она читает top-level `user`, `account` и `total_usd`. `Wallet-60683eb52b97e281.js` отображает `authReducer.account`; форма Withdraw использует этот же список с additional_wallets и possible_wallets. Поэтому в P2P-каталог добавлен derived-callsite метод `get_accounts()` на точный `/auth/user`. Он возвращает исходный объект; список кошельков находится в поле account. Это не spot address/wallets и не вызов произвольного getRequestCabinet.

У этого маршрута отдельная форма ответа `{user,account,total_usd}`, а не стандартный `{status,data}`. URL и использование подтверждены JS, но HTTP-вызов с аккаунтом не выполнялся. Source URLs, offsets, snippets и SHA записаны в schemas/p2p_site.json. Конкретный журнал транзакций по исследованным callsites не подтверждён; произвольный generic endpoint по-прежнему не предоставляется.

Ещё один конкретный read-only callsite найден в `6034-f2e976244927be8e.js`: GET `/transactions/get-withdraw-by-id/{withdraw_id}` с bearer token; клиент читает response.data.data. Добавлен derived метод `get_withdrawal(path={"withdraw_id": ...})` для чтения существующей заявки. Он не создаёт, не подтверждает и не отменяет вывод. Source/SHA/offset/excerpt сохранены. HTTP-вызов с аккаунтом не выполнялся.


Обновление проверки новостей: HTML блога объявляет WordPress REST discovery. Подтверждены публичные GET `/blog/wp-json/wp/v2/posts`, `/posts/{id}`, `/categories`; SDK предоставляет get_news_posts/get_news_post/get_news_categories. Декларированный RSS `/blog/feed/` при проверке вернул 404.


## Исправление callsite формы P2P: body и internal95

Источник нового подтверждения - public static GET локального координатора,
без cookies/auth: HTTP200 для
`https://bit.team/p2p/_next/static/chunks/6034-f2e976244927be8e.js`,
SHA256 `3b46ec340896bc7fa2673c9b710798220aad5e83fd822515b12c8c027cdec685`
(совпадает с сохранённым hash этого chunk). Около offset5295, функция Z:
маршрут выбирается выражением95===t.currency_id, POST получает bodyt и Bearer,
затем клиент читает response.data.data и возвращает p.id. Этот id не
отождествляется со spot transaction.id или spot withdrawal orderId.

Координатор также сообщил HTTP200 для актуального статического form bundle
`https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/Withdraw-56b2a70d301a037a.js`,
41423bytes, SHA256
`cbffa511c29dcfeba14c4fa5f7c24a4b3dc47a4ab75761dd3e51745b246eee86`.
Около offset16625 form defaults: address/public/comment/label/sum - пустые
строки, commission_booster_name - null. Около offset21434 форма добавляет
selected-wallet currency_id; только95 добавляет date/hash. Семантика public,
commission booster и алгоритм hash95 этим не установлены.

В облаке проверены сохранённый schema/excerpt и переданная точная выдержка;
полные JS не скачивались заново. Это primary frontend source evidence,
сообщённое координатором, а не успешный финансовый endpoint или наша cloud-live
проверка. Стандартный prepare-план чистый и не делаетHTTP; internal95 остаётся
явным raw low-level контрактом без генерации date/hash и без обещания валидного
production body. Никаких POST, отправки кодов или подтверждений не выполнялось.


## Ограниченная RAM-инвентаризация прямых API-v2 callsites

Источник - переданная пользователем RAM-инвентаризация локального reviewer:
10 реально подключённых публичных JS, homepage buildR5BL6q2trcHZtSUYGbF3M,
manifest SHA5520c22a65c8cfc9076ed7e780071c0f41a6dc92cf51d2e0293d7a69fbc62c5f.
Это ограниченный набор, не полное покрытие всех JS/сайта. Общий source
`https://bit.team/p2p/_next/static/chunks/pages/_app-3772cf9af2d461b9.js`,
SHA2316cc9e89475e17ce2a2fae1378c40cb7e0eed706e80dc8f72925a7ff37ab49;
module77016 околоoffset121387 создаёт baseURLhttps://api-v2.bit.team/api/v2.
В schema сохранены16 новых фиксированных операций с offsets начала method и
reported_contract; текст полного JS для них не выдумывается. Ответы raw,
проверяются только наблюдённые поля; значения/типы/enum/права не додумываются.
GET/user/read-all-notification имеет побочный эффект и помечен mutating GET.
POSTnull, explicitbody/type и разные response shapes разделены. Публичные
/anunt/get, /anunt/get-limit-percent, /get/data-init-payment-method уже покрыты
SiteAPI и не считаются новыми. /auth/login и /oauth/token другого auth-client
не включены и не используются как доказательство general-token refresh.

Отдельный внутренний transfer: manifest-linked
`https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/SpotAssetsTransfer-370f165e27881048.js`,
SHAf201f8530c9b0e65ecb5269f261d1e543c0b7b0e0881c0391b7ab8ed495efe28,
offset16015 POST/account/create-withdraw-to-stock с bodycurrency_id,sum,
internal_request:true. Поля ответа не читаются. Это отдельный raw-контракт и
pure prepare-план, не только95/date/hash и не требование data.id. Доступность
валют/аккаунта и результат перевода не проверены.

## Targeted trace: журнал и chain-provenance

Новых API-запросов при этом локальном RAM trace не было. Общий module71801:
`https://bit.team/p2p/_next/static/chunks/3812-633d8d6f222bceb0.js`,
SHA2c0957ed01c7bfd933ba10d0bba968fafb5802f81872c2f9205768b6a0b20107.
Offset5600 импортирует77016; offset5715 читает props url/type; offset7813 делает
GET url?page=1&limit=999 с optionaltype и generalBearer; offset7967 читает
response.data.data. Base77016 доказан выше отдельно.

Page props под `https://bit.team/p2p/_next/static/chunks/pages/Cabinet/`:

| Page / SHA | Offset | Fixed prop |
|---|---|---|
| Archive-729a89b5478b2127.js / ef412159bdc563869b4abc3e120573d2e8d08250e276e443e89dd92cbf8f66bd |6614| /transactions/account-transactions |
| Trader-ac27c0d669bfbe6a.js /109db258fd8c687717a0a5e8682bc484a14798dc9a438ec8626db5c9d015f535 |7383| /transactions/get-transactions, type amount |
| Any-1009ae0797d3db0d.js /463884550e670cee4fd5000b26a657970416e10a2f607373b18252f4ee9d45be |3982| /transactions/get-transactions, type system |
| Deals-a303fa114036a6ac.js /f1daaa5fb69b09728fbcccf47ebdf0d885e03f9143092fd5c7b46359ede27c05 |5956| /operations/archive, уже существующая операция |

Добавлены только два недостающих fixed journal пути; произвольный url или
фильтры generic helper не открываются. Подтверждены exportpage1/limit999 и
amount/system, не общая пагинация/retention. Тот же3812 offset6723 содержит
явный UI withdraw switch-1/0/1/2 на cancelled/created/confirmed/done;
default возвращает исходное значение. ui_state отражает эти метки отдельно:
mainstate1 pending,2unknown. Это UI, не exhaustivebackend enum или finality.
Все hash/offset/source факты в этом разделе - provenance локального reviewer,
не cloud-refetch/hash recomputation или live финансовый результат.
