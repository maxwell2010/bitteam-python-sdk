"""Anonymous read-only APIs discovered in the public BitTeam site clients.

No account cookie jar, auth headers, financial actions, or redirect following.
Responses preserve the server's JSON envelope; unavailable services raise.
"""
from decimal import Decimal, InvalidOperation
from contextlib import asynccontextmanager
import asyncio
import re
import ssl
from urllib.parse import quote

import aiohttp

from .auth import BitTeamAPIError
from .utils import RateLimiter


class BitTeamSiteAPI:
    BASES = {
        "v2": "https://api-v2.bit.team/api/v2",
        "market": "https://bitteam-market-back.bit.team/api",
        "docs": "https://docs-api.bit.team/api/v1",
        "blog": "https://bit.team/blog/wp-json/wp/v2",
    }
    ROUTES = {
        "coins": ("v2", "/public/coins/list"),
        "currencies": ("v2", "/public/currencies/list"),
        "rates": ("v2", "/public/rates-by-period"),
        "static_menu": ("v2", "/public/static-page/{project_id}/get-all-menu"),
        "static_page": ("v2", "/public/static-page/{project_id}/{category_id}/{page_id}"),
        "p2p_currencies": ("v2", "/get/data-init-currency"),
        "payments": ("v2", "/get/data-init-payment-method"),
        "adverts": ("v2", "/anunt/get"),
        "advert_limits": ("v2", "/anunt/get-limit-percent"),
        "crypto_map": ("market", "/cryptocurrency/map"),
        "crypto_category": ("market", "/cryptocurrency/map/categories/{category}"),
        "crypto": ("market", "/cryptocurrency/one/{alias}"),
        "crypto_history": ("market", "/cryptocurrency/historical/{coin}"),
        "market_pairs": ("market", "/market_pairs/coin/{coin}"),
        "crypto_meta": ("market", "/page/coin-meta/{coin}"),
        "cryptos": ("market", "/core/common/cryptos"),
        "markets": ("market", "/core/common/markets"),
        "docs_pages": ("docs", "/pages"),
        "news_posts": ("blog", "/posts"),
        "news_post": ("blog", "/posts/{post_id}"),
        "news_categories": ("blog", "/categories"),
    }

    def __init__(self, *, timeout=20, locale="en"):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 60:
            raise ValueError("timeout must be between 1 and 60 seconds")
        if locale not in ("en", "ru"):
            raise ValueError("locale must be en or ru")
        self.timeout, self.locale = timeout, locale
        self._session = None
        self._closed = False
        self._limiter = RateLimiter(5, 1)

    @staticmethod
    def _integer(value, name, *, minimum=1, maximum=2 ** 53 - 1):
        if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
            raise ValueError(f"Invalid {name}")
        return value

    @staticmethod
    def _segment(value):
        if isinstance(value, bool) or not isinstance(value, (str, int)):
            raise ValueError("Invalid path identifier")
        value = str(value)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value):
            raise ValueError("Invalid path identifier")
        return quote(value, safe="")

    @classmethod
    def _pagination(cls, limit, page=None, offset=None):
        result = {"limit": cls._integer(limit, "limit", maximum=1000)}
        if page is not None:
            result["page"] = cls._integer(page, "page", maximum=1000000)
        if offset is not None:
            result["offset"] = cls._integer(offset, "offset", minimum=0, maximum=1000000)
        return result

    async def _get_session(self):
        if self._closed:
            raise RuntimeError("Site client is closed")
        if self._session is None:
            try:
                import certifi
                context = ssl.create_default_context(cafile=certifi.where())
            except ImportError:
                context = ssl.create_default_context()
            self._session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=context), cookie_jar=aiohttp.DummyCookieJar(),
                trust_env=False, timeout=aiohttp.ClientTimeout(total=self.timeout))
        return self._session

    @staticmethod
    @asynccontextmanager
    async def _redacted_errors():
        try:
            yield
        except asyncio.TimeoutError:
            raise asyncio.TimeoutError("Public site request timed out; operation was not retried") from None
        except aiohttp.ClientError:
            raise BitTeamAPIError(0) from None

    async def _get(self, operation, *, path=None, params=None):
        if operation not in self.ROUTES:
            raise ValueError("Unknown public site operation")
        service, route = self.ROUTES[operation]
        placeholders = set(re.findall(r"\{([^}]+)\}", route))
        path = path or {}
        if set(path) != placeholders:
            raise ValueError("Invalid path parameters")
        for key, value in path.items():
            route = route.replace("{" + key + "}", self._segment(value))
        session = await self._get_session()
        await self._limiter.acquire()
        if self._closed:
            raise RuntimeError("Site client is closed")
        language = ({"en": "en-US", "ru": "ru-RU"}[self.locale] if service == "market" else self.locale)
        # Never log request or response payloads: adverts may contain payment details.
        async with self._redacted_errors(), session.get(self.BASES[service] + route, params=params,
                               headers={"Accept": "application/json", "Accept-Language": language},
                               allow_redirects=False) as response:
            if not 200 <= response.status < 300:
                raise BitTeamAPIError(response.status)
            try:
                payload = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise BitTeamAPIError(502) from None
            if not isinstance(payload, (dict, list)):
                raise BitTeamAPIError(502)
            if isinstance(payload, dict):
                if payload.get("status") is False or payload.get("ok") is False or payload.get("errors"):
                    raise BitTeamAPIError(response.status, payload.get("code"))
            if service == "v2":
                if (not isinstance(payload, dict) or payload.get("status") is not True
                        or "data" not in payload or payload.get("code", 200) != 200):
                    raise BitTeamAPIError(502)
            return payload

    async def get_coins(self):
        return await self._get("coins")

    async def get_news_posts(self, *, page=1, per_page=20, search=None, after=None, before=None):
        params = {"page": self._integer(page, "page", maximum=1000000),
                  "per_page": self._integer(per_page, "per_page", maximum=100)}
        for name, value in (("search", search), ("after", after), ("before", before)):
            if value is not None:
                if not isinstance(value, str) or not 1 <= len(value) <= 200:
                    raise ValueError("Invalid news filter")
                params[name] = value
        return await self._get("news_posts", params=params)

    async def get_news_post(self, post_id):
        return await self._get("news_post", path={"post_id": self._integer(post_id, "post_id")})

    async def get_news_categories(self, *, page=1, per_page=100):
        return await self._get("news_categories", params={"page": self._integer(page, "page"),
                                "per_page": self._integer(per_page, "per_page", maximum=100)})

    async def get_crypto_chart(self, coin_id, period):
        """Observed read-only POST contract; backend availability is not assumed."""
        if isinstance(coin_id, bool) or not isinstance(coin_id, (int, str)) or not str(coin_id) or len(str(coin_id)) > 100:
            raise ValueError("Invalid chart coin id")
        if isinstance(period, bool) or not isinstance(period, (int, str)) or not str(period) or len(str(period)) > 30:
            raise ValueError("Invalid chart period")
        session = await self._get_session()
        await self._limiter.acquire()
        if self._closed:
            raise RuntimeError("Site client is closed")
        async with self._redacted_errors(), session.post(self.BASES["market"] + "/cryptocurrency/chart", json={"id": coin_id, "period": period},
                                headers={"Accept": "application/json", "Accept-Language": {"en": "en-US", "ru": "ru-RU"}[self.locale]},
                                allow_redirects=False) as response:
            if not 200 <= response.status < 300:
                raise BitTeamAPIError(response.status)
            try:
                result = await response.json()
            except (ValueError, aiohttp.ContentTypeError):
                raise BitTeamAPIError(502) from None
            if not isinstance(result, (dict, list)) or (isinstance(result, dict) and
                    (result.get("ok") is False or result.get("status") is False or result.get("errors"))):
                raise BitTeamAPIError(502)
            return result

    async def get_currencies(self):
        return await self._get("currencies")

    async def get_rates_by_period(self, coin_id, currency_id, *, type_="day", period=1):
        if not isinstance(type_, str) or not re.fullmatch(r"[a-zA-Z]{1,20}", type_):
            raise ValueError("Invalid period type")
        return await self._get("rates", params={"coin_id": self._integer(coin_id, "coin_id"),
            "currency_id": self._integer(currency_id, "currency_id"), "type": type_,
            "period": self._integer(period, "period", maximum=10000)})

    async def get_static_menu(self, project_id=2):
        return await self._get("static_menu", path={"project_id": self._integer(project_id, "project_id")})

    async def get_static_page(self, project_id, category_id, page_id):
        return await self._get("static_page", path={key: self._integer(value, key) for key, value in
            (("project_id", project_id), ("category_id", category_id), ("page_id", page_id))})

    async def get_p2p_currencies(self, type_="coin,token"):
        if type_ not in ("coin,token", "valute"):
            raise ValueError("type must be coin,token or valute")
        return await self._get("p2p_currencies", params={"type": type_})

    async def get_payment_methods(self, fiat):
        return await self._get("payments", params={"fiat_short_name": self._segment(fiat).upper()})

    async def get_advertisement_limits(self):
        return await self._get("advert_limits")

    async def get_advertisements(self, *, type_, coin, fiat, limit=20, offset=0,
                                 payment_name=None, sum_=None, order_by=None, sorted_by=None,
                                 online_only=False):
        if type_ not in ("buy", "sell"):
            raise ValueError("Advertisement type must be buy or sell")
        params = dict(self._pagination(limit, offset=offset), type=type_,
                      coin_short_name=self._segment(coin), fiat_short_name=self._segment(fiat))
        for name, value in (("payment_name", payment_name), ("orderBy", order_by), ("sortedBy", sorted_by)):
            if value is not None:
                params[name] = self._segment(value)
        if sum_ is not None:
            try:
                value = Decimal(str(sum_))
            except InvalidOperation:
                raise ValueError("Invalid advertisement sum") from None
            if not value.is_finite() or value <= 0:
                raise ValueError("Invalid advertisement sum")
            params["sum"] = str(value)
        if not isinstance(online_only, bool):
            raise ValueError("online_only must be boolean")
        if online_only:
            params["filter[strict][users.is_online]"] = 1
        return await self._get("adverts", params=params)

    async def get_crypto_map(self, *, limit=50, page=1, category=None, tag=None):
        if category is not None and tag is not None:
            raise ValueError("Choose a category or tag")
        params = self._pagination(limit, page=page)
        if category is not None:
            return await self._get("crypto_category", path={"category": category}, params=params)
        if tag is not None:
            params["tag"] = self._segment(tag)
        return await self._get("crypto_map", params=params)

    async def get_crypto(self, alias):
        return await self._get("crypto", path={"alias": alias})

    async def get_crypto_history(self, coin, *, limit=50, page=1):
        return await self._get("crypto_history", path={"coin": coin}, params=self._pagination(limit, page=page))

    async def get_market_pairs(self, coin, *, limit=50, page=1):
        return await self._get("market_pairs", path={"coin": coin}, params=self._pagination(limit, page=page))

    async def get_crypto_metadata(self, coin):
        return await self._get("crypto_meta", path={"coin": coin})

    async def get_common_cryptos(self):
        return await self._get("cryptos")

    async def get_common_markets(self):
        return await self._get("markets")

    async def get_docs_pages(self, *, locale=None, search=None):
        locale = locale or self.locale
        if locale not in ("en", "ru"):
            raise ValueError("locale must be en or ru")
        params = {"locale": locale, "include": "parent"}
        if search is not None:
            if not isinstance(search, str) or not 1 <= len(search) <= 200:
                raise ValueError("Search must contain 1 to 200 characters")
            params.update({"filter[name]": search, "fields[pages]": "slug,name,parent"})
        return await self._get("docs_pages", params=params)

    async def close(self):
        if not self._closed:
            self._closed = True
            if self._session is not None:
                await self._session.close()

    async def __aenter__(self):
        await self._get_session()
        return self

    async def __aexit__(self, *exc):
        await self.close()
