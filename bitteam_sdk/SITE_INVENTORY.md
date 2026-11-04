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

Форма найдена через публичный Next build manifest: `https://bit.team/p2p/_next/static/chunks/pages/Cabinet/WalletAction/Withdraw-56b2a70d301a037a.js`. Она строит сетевые вкладки из `account.token_name/currency_id`, `additional_wallets[{token_name,currency_id}]` и `possible_wallets[id]`. Выбор вкладки сохраняется в selectedCurrency. onSubmit разрешает его в currency_id и передаёт ровно в одну createNewTransaction. Общий helper делает POST `/account/create-withdraw?currency_id=<id>` с body и bearer token. Отдельный network параметр в проверенной форме и wrapper не найден.

Следовательно, для P2P разные сети выбираются разными currency_id; разные токены/сети следует оформлять отдельными заявками. Возможность batch/атомарных или одновременных выводов не подтверждена. Это не основание использовать API-v2 IDs в spot API: namespaces и подтверждения различаются. Приватные wallet/account endpoints и любые выводы не вызывались; доступность конкретной сети, адреса и средства не проверялись.

## Конкретный private call site: P2P кошельки

В актуальном `_app-3772cf9af2d461b9.js` функция обновления Redux-профиля выполняет GET `/auth/user` через API-v2 с general bearer token. Она читает top-level `user`, `account` и `total_usd`. `Wallet-60683eb52b97e281.js` отображает `authReducer.account`; форма Withdraw использует этот же список с additional_wallets и possible_wallets. Поэтому в P2P-каталог добавлен derived-callsite метод `get_accounts()` на точный `/auth/user`. Он возвращает исходный объект; список кошельков находится в поле account. Это не spot address/wallets и не вызов произвольного getRequestCabinet.

У этого маршрута отдельная форма ответа `{user,account,total_usd}`, а не стандартный `{status,data}`. URL и использование подтверждены JS, но HTTP-вызов с аккаунтом не выполнялся. Source URLs, offsets, snippets и SHA записаны в schemas/p2p_site.json. Конкретный журнал транзакций по исследованным callsites не подтверждён; произвольный generic endpoint по-прежнему не предоставляется.

Ещё один конкретный read-only callsite найден в `6034-f2e976244927be8e.js`: GET `/transactions/get-withdraw-by-id/{withdraw_id}` с bearer token; клиент читает response.data.data. Добавлен derived метод `get_withdrawal(path={"withdraw_id": ...})` для чтения существующей заявки. Он не создаёт, не подтверждает и не отменяет вывод. Source/SHA/offset/excerpt сохранены. HTTP-вызов с аккаунтом не выполнялся.


Обновление проверки новостей: HTML блога объявляет WordPress REST discovery. Подтверждены публичные GET `/blog/wp-json/wp/v2/posts`, `/posts/{id}`, `/categories`; SDK предоставляет get_news_posts/get_news_post/get_news_categories. Декларированный RSS `/blog/feed/` при проверке вернул 404.
