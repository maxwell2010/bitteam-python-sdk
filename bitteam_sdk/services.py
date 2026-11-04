"""Convenience methods mapped from the existing trading services."""
from decimal import Decimal
from datetime import datetime, timezone
import asyncio
from .auth import BitTeamAPIError, SessionAuth


def private_read_guard(client):
    """Bind a multi-read operation to one account, allowing token refresh."""
    auth = getattr(client, "auth", None)
    lifecycle = auth._lifecycle if isinstance(auth, SessionAuth) else None
    def check():
        if getattr(client, "_closed", False):
            raise RuntimeError("Client is closed")
        if lifecycle is not None:
            if getattr(client, "auth", None) is not auth:
                raise asyncio.CancelledError("Authentication operation was invalidated")
            auth._assert_lifecycle(lifecycle)
    return check


def symbol_name(symbol):
    value = symbol.strip().replace("/", "_").replace("-", "_").lower()
    if value.count("_") != 1 or not all(part.isalnum() for part in value.split("_")):
        raise ValueError("Expected a BASE_QUOTE trading pair")
    return value


def rows(payload, key):
    result = payload.get("result", payload) if isinstance(payload, dict) else payload
    if isinstance(result, dict):
        result = result.get(key)
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise BitTeamAPIError(502)
    return result


class ServiceMethods:
    async def get_withdrawal_record(self, identifier, *, source):
        from .withdrawal_tracking import read_withdrawal
        return await read_withdrawal(self, identifier, source=source)

    async def wait_for_withdrawal(self, identifier, *, source, predicate, timeout=300, interval=5, max_requests=100):
        from .withdrawal_tracking import wait_for_withdrawal
        return await wait_for_withdrawal(self, identifier, source=source, predicate=predicate,
                                         timeout=timeout, interval=interval, max_requests=max_requests)

    async def get_trading_pairs(self):
        result = rows(await self.api.get_pairs(), "pairs")
        return [dict(pair, symbol=pair["name"].upper(),
            base=pair.get("baseAssetTicker") or pair.get("base") or pair["name"].split("_")[0].upper(),
            quote=pair.get("quoteAssetTicker") or pair.get("quote") or pair["name"].split("_")[-1].upper()) for pair in result]

    async def get_symbols(self):
        return [pair["name"].upper() for pair in await self.get_trading_pairs()]

    async def get_currencies(self, *, limit=100, offset=0):
        return rows(await self.api.get_currencies(params={"limit": limit, "offset": offset}), "currencies")

    async def get_withdrawal_networks(self, symbol):
        from .withdrawal import withdrawal_networks
        return withdrawal_networks(await self._withdrawal_catalog(), symbol)

    async def _withdrawal_catalog(self):
        result, seen = [], set()
        for page in range(100):
            payload = await self.api.get_currencies(params={"limit": 1000, "offset": page * 1000})
            batch = rows(payload, "currencies")
            if any(c.get("id") in seen for c in batch):
                raise RuntimeError("Currency pagination repeated rows")
            seen.update(c.get("id") for c in batch)
            result.extend(batch)
            count = payload.get("result", {}).get("count")
            if len(batch) < 1000 or (isinstance(count, int) and len(result) >= count):
                return result
        raise RuntimeError("Currency catalog exceeded pagination bound")

    async def prepare_withdrawal(self, symbol, *, amount, address, network=None):
        from .withdrawal import prepare_withdrawal
        return prepare_withdrawal(await self._withdrawal_catalog(), symbol, amount=amount, address=address, network=network)

    async def request_network_withdrawal(self, symbol, *, amount, address, network=None):
        self._require_ready()
        plan = await self.prepare_withdrawal(symbol, amount=amount, address=address, network=network)
        return await self.rest._request("POST", "/withdraw/create" if self.rest._session_mode else "/ccxt/withdraw", data=plan["payload"])

    async def get_withdrawal_permission(self, currency_id):
        self._require_ready()
        return await self.api.get_withdraw_by_currency_id_check(currency_id)

    async def get_active_notifications(self, *, limit=10, offset=0):
        self._require_ready()
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid pagination")
        return await self.rest._request("GET", "/notification/message/active/all", params={"limit": limit, "offset": offset})

    async def get_notifications(self, category, *, limit=100, offset=0):
        import re
        self._require_ready()
        if not isinstance(category, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", category):
            raise ValueError("Invalid notification category")
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid pagination")
        return await self.rest._request("GET", "/notification/message/all/" + category, params={"limit": limit, "offset": offset})

    async def mark_all_notifications_read(self):
        self._require_ready()
        return await self.rest._request("POST", "/notification/message/read-all")

    async def get_trading_pair_info(self, symbol):
        response = await self.api.get_pair_by_name(symbol_name(symbol))
        result = response.get("result", response)
        if not isinstance(result, dict):
            raise BitTeamAPIError(502)
        pair = result.get("pair", result)
        if not isinstance(pair, dict):
            raise BitTeamAPIError(502)
        return dict(pair, symbol=symbol_name(symbol).upper())

    async def get_ticker(self, symbol):
        pair = await self.get_trading_pair_info(symbol)
        book = await self.get_orderbook(symbol, 1)
        return {"symbol": symbol_name(symbol).upper(),
            "last_price": Decimal(str(pair.get("lastPrice") or 0)),
            "bid": Decimal(str(book["bids"][0][0])) if book["bids"] else None,
            "ask": Decimal(str(book["asks"][0][0])) if book["asks"] else None,
            "change24": pair.get("change24"), "volume24": pair.get("volume24"),
            "change_24h": pair.get("change24"), "volume": pair.get("volume24"),
            "volume24USD": pair.get("volume24USD", pair.get("quoteVolume24")), "raw": pair}

    async def get_orderbook(self, symbol, limit=1000):
        if not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        payload = await self.api.get_cmc_orderbook_by_pair(symbol_name(symbol))
        if not isinstance(payload, dict) or not all(isinstance(payload.get(k), list) for k in ("bids", "asks")):
            raise BitTeamAPIError(502)
        return {"bids": payload["bids"][:limit], "asks": payload["asks"][:limit]}

    async def get_trade_history(self, symbol, limit=100):
        if not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise ValueError("limit must be between 1 and 10000")
        trades = rows(await self.api.get_cmc_trades_by_pair(symbol_name(symbol)), "trades")
        result = []
        for trade in sorted(trades, key=lambda trade: int(trade.get("timestamp", 0)), reverse=True)[:limit]:
            amount = trade.get("base_volume", trade.get("amount"))
            created_at = datetime.fromtimestamp(int(trade["timestamp"]) / 1000, tz=timezone.utc).isoformat() if trade.get("timestamp") is not None else None
            result.append(dict(trade, id=trade.get("trade_id", trade.get("id")), symbol=symbol_name(symbol).upper(),
                side=trade.get("type", trade.get("side")), status="filled", amount=amount,
                executed=amount, createdAt=created_at))
        return result

    async def get_public_orders(self, symbol=None, *, limit=100, offset=0):
        params = {"limit": limit, "offset": offset, "order": {"id": "ASC"}}
        if symbol:
            params["where"] = {"pairId": await self.rest._pair_id(symbol_name(symbol))}
        return rows(await self.api.get_orders(params=params), "orders")

    async def get_public_trades(self, symbol=None, *, limit=100, offset=0):
        params = {"limit": limit, "offset": offset, "order": {"id": "ASC"}}
        if symbol:
            params["pairId"] = await self.rest._pair_id(symbol_name(symbol))
        return rows(await self.api.get_trades(params=params), "trades")

    async def _iter_rows(self, fetch, *, page_size=100, max_pages=1000,
                         private=False, identity_fields=("id", "trade_id", "orderId")):
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("Invalid page_size")
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or max_pages < 1:
            raise ValueError("Invalid max_pages")
        guard = private_read_guard(self) if private else lambda: None
        seen = set()
        for page in range(max_pages):
            guard()
            batch = await fetch(page_size, page * page_size)
            guard()
            fresh = []
            for row in batch:
                identity = next((row[key] for key in identity_fields if key in row), None)
                if (isinstance(identity, bool) or not isinstance(identity, (str, int))
                        or isinstance(identity, str) and not identity.strip()):
                    raise BitTeamAPIError(502)
                if str(identity) not in seen:
                    seen.add(str(identity))
                    fresh.append(row)
            if batch and not fresh:
                raise RuntimeError("Exchange repeated a pagination page")
            for row in fresh:
                guard()
                yield row
                guard()
            if len(batch) < page_size:
                return
        raise RuntimeError("Pagination reached max_pages; narrow the query")

    def iter_public_orders(self, symbol=None, *, page_size=100, max_pages=1000):
        return self._iter_rows(lambda limit, offset: self.get_public_orders(symbol, limit=limit, offset=offset),
                               page_size=page_size, max_pages=max_pages)

    def iter_public_trades(self, symbol=None, *, page_size=100, max_pages=1000):
        return self._iter_rows(lambda limit, offset: self.get_public_trades(symbol, limit=limit, offset=offset),
                               page_size=page_size, max_pages=max_pages)

    def iter_user_trades(self, *, pair=None, page_size=100, max_pages=1000):
        return self._iter_rows(lambda limit, offset: self.get_user_trades(limit, offset, pair=pair),
                               page_size=page_size, max_pages=max_pages, private=True)

    async def get_candles_from_trades(self, symbol, interval="1m", *, limit=10000):
        from .marketdata import aggregate_trades
        return aggregate_trades(await self.get_trade_history(symbol, limit), symbol, interval=interval)

    async def get_precisions(self):
        return await self.rest.get_precisions()

    async def get_balances(self):
        payload = await self.get_balance()
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise BitTeamAPIError(502)
        return result

    async def get_user_orders(self, limit=10, offset=0, order_type="history", *, pair=None):
        self._require_ready()
        params = {"limit": limit, "offset": offset, "type": order_type}
        if self.rest._session_mode:
            if pair:
                params["where"] = {"pairId": await self.rest._pair_id(symbol_name(pair))}
            payload = await self.api.get_orders_by_user(params=params)
        else:
            if pair:
                params["pair"] = symbol_name(pair)
            payload = await self.api.get_ccxt_orders_of_user(params=params)
        return rows(payload, "orders")

    async def get_open_orders(self, symbol=None):
        return await self.get_user_orders(limit=1000, order_type="active", pair=symbol)

    async def get_user_trades(self, limit=100, offset=0, *, pair=None):
        self._require_ready()
        params = {"limit": limit, "offset": offset}
        if self.rest._session_mode:
            if pair:
                params["pairId"] = await self.rest._pair_id(symbol_name(pair))
            payload = await self.api.get_trades_by_user(params=params)
        else:
            if pair:
                params["pair"] = symbol_name(pair)
            payload = await self.api.get_ccxt_trades_of_user(params=params)
        return rows(payload, "trades")

    async def iter_user_orders(self, *, page_size=100, order_type="history", pair=None, max_pages=1000):
        async for row in self._iter_rows(
                lambda limit, offset: self.get_user_orders(limit, offset, order_type, pair=pair),
                page_size=page_size, max_pages=max_pages, private=True,
                identity_fields=("id", "orderId")):
            yield row

    async def get_order_info(self, order_id):
        self._require_ready()
        payload = await self.api.get_ccxt_order_by_id(order_id)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise BitTeamAPIError(502)
        return result

    async def order_info(self, order_id):
        return await self.get_order_info(order_id)

    async def get_order_status(self, order_id):
        return (await self.get_order_info(order_id)).get("status")

    async def cancel_all_orders(self, *, pair_id):
        self._require_ready()
        method = self.api.post_all_orders_cancel if self.rest._session_mode else self.api.post_ccxt_cancel_all_order
        return await method(data={"pairId": pair_id})

    async def create_conditional_order(self, *, pair_id, side, amount, price, slippage):
        self._require_ready()
        return await self.api.post_order_conditional_create(data={"pairId": pair_id, "side": side,
            "amount": str(amount), "price": str(price), "type": "conditional", "slippage": slippage})

    async def get_wallets(self, *, limit=100, offset=0):
        self._require_ready()
        return await self.api.get_address_wallets(params={"limit": limit, "offset": offset})

    async def get_transaction_history(self, *, limit=100, offset=0, start=None, end=None):
        """Read /transactionsByUser. Passes documented integer from/to filters unchanged."""
        self._require_ready()
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("limit must be an integer from 1 to 1000")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a nonnegative integer")
        params = {"limit": limit, "offset": offset}
        for key, value in (("from", start), ("to", end)):
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError("Time bounds must be nonnegative integers")
                params[key] = value
        if start is not None and end is not None and start > end:
            raise ValueError("start must not exceed end")
        return rows(await self.api.get_transactions_by_user(params=params), "transactions")

    def iter_transactions(self, *, start=None, end=None, page_size=100, max_pages=1000):
        """Bounded, deduplicated reads; offsets are not a server snapshot."""
        return self._iter_rows(lambda limit, offset: self.get_transaction_history(
            limit=limit, offset=offset, start=start, end=end), page_size=page_size, max_pages=max_pages,
            private=True, identity_fields=("id",))

    async def get_transactions(self, *, limit=100, offset=0, currency=None):
        self._require_ready()
        params = {"limit": limit, "offset": offset}
        if currency:
            params["currency"] = currency
        return await self.api.get_transactions_of_user(params=params)

    async def create_deposit_address(self, currency_id):
        self._require_ready()
        return await self.api.get_address_by_currency_id_create(currency_id)

    async def request_withdrawal(self, *, currency_id, amount, address, currency=None):
        self._require_ready()
        from .withdrawal import decimal_value
        quantity = decimal_value(amount)
        if quantity is None or quantity <= 0:
            raise ValueError("Withdrawal amount must be positive and finite")
        if isinstance(currency_id, bool) or not isinstance(currency_id, int) or currency_id <= 0:
            raise ValueError("currency_id must be a positive integer")
        if not isinstance(address, str) or not address.strip() or any(c.isspace() for c in address.strip()):
            raise ValueError("Withdrawal address must not contain whitespace")
        payload = {"currencyId": currency_id, "amount": format(quantity, "f"), "to": address.strip()}
        if currency:
            payload["currency"] = currency
        return await self.api.post_withdraw_create(data=payload)

    @staticmethod
    def _withdrawal_order_id(order_id):
        if not isinstance(order_id, str) or not order_id.strip():
            raise ValueError("A nonempty withdrawal orderId string is required")
        return order_id

    async def send_withdrawal_email_code(self, order_id):
        self._require_ready()
        return await self.api.post_withdraw_confirmation_email(data={"orderId": self._withdrawal_order_id(order_id)})

    async def send_withdrawal_phone_code(self, order_id):
        self._require_ready()
        return await self.api.post_withdraw_confirmation_phone(data={"orderId": self._withdrawal_order_id(order_id)})

    async def confirm_withdrawal(self, *, order_id, email_code, phone_code=None, totp=None):
        self._require_ready()
        data = {"orderId": self._withdrawal_order_id(order_id), "withdrawCodeEmail": email_code}
        if phone_code is not None:
            data["withdrawCodePhone"] = phone_code
        if totp is not None:
            data["token2FA"] = totp
        return await self.api.post_withdraw_confirm(data=data)

    async def test_connection(self):
        await self.get_trading_pairs()
        return True
