"""Local HTTPS integration tests. Server responses are synthetic contract fixtures."""
import asyncio
import base64
import datetime
import ssl
from collections import Counter

import aiohttp
from aiohttp import web
from aiohttp.abc import AbstractResolver
import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from bitteam_sdk import (BitTeamClient, SessionAuth, ApiKeyAuth, AuthState,
                         AuthenticationError, BitTeamAPIError)
from bitteam_sdk.rest import BitTeamRestAPI
from bitteam_sdk.utils import RateLimiter


class Resolver(AbstractResolver):
    async def resolve(self, host, port=0, family=0):
        return [{"hostname": host, "host": "127.0.0.1", "port": port,
                 "family": family, "proto": 0, "flags": 0}]

    async def close(self):
        pass


@pytest_asyncio.fixture
async def environment(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "BitTeam SDK local test")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("auth.bitteam.test"),
                          x509.DNSName("spot.bitteam.test")]), critical=False)
            .sign(key, hashes.SHA256()))
    certfile, keyfile = tmp_path / "cert.pem", tmp_path / "key.pem"
    certfile.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    server_ssl = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ssl.load_cert_chain(certfile, keyfile)
    client_ssl = ssl.create_default_context(cafile=str(certfile))
    state = {"flow": "direct", "channel": "email", "calls": [], "counts": Counter(),
             "expire": False, "refresh_fail": False, "mutation_fail": False,
             "reject_code": False, "malformed_login": False, "malformed_tokens": False}

    async def handler(request):
        if request.path == "/history":
            ws = web.WebSocketResponse(protocols=["nes"])
            await ws.prepare(request)
            async for message in ws:
                frame = message.json()
                if frame["type"] == "ping":
                    state["counts"]["ws_pongs"] += 1
                    continue
                response = {"type": frame["type"], "id": frame["id"]}
                if frame["type"] == "hello":
                    assert frame["version"] == "2"
                    assert frame["auth"]["headers"]["Authorization"] == "jwt"
                if frame["type"] == "request":
                    path = frame["path"]
                    response["statusCode"] = 200
                    if path == "/api/tw/disconnect":
                        await ws.close()
                        break
                    if path == "/api/tw/timeout":
                        continue
                    if path == "/api/tw/invalid":
                        response.update(statusCode=403, payload={"message": "secret-password", "code": 403001})
                    elif path == "/api/tw/config":
                        response["payload"] = {"supported_resolutions": ["1", "5", "15", "60", "1D"]}
                    elif path.startswith("/api/tw/history/DEL_USDT/15?"):
                        response["payload"] = {"result": {"data": [{"t": 1000, "o": "1.1", "h": "1.3", "l": "1", "c": "1.2", "v": "2.5"}]}}
                    else:
                        response["payload"] = {"result": {"data": []}}
                    if path == "/api/tw/chunked":
                        import json
                        raw = json.dumps(response)
                        await ws.send_str("+" + raw[:20])
                        await ws.send_str("!" + raw[20:])
                        continue
                await ws.send_json(response)
                if frame["type"] == "sub":
                    await ws.send_json({"type": "ping"})
                    await ws.send_json({"type": "pub", "path": frame["path"], "message": {"result": {
                        "time": 1000, "open": "1", "high": "2", "low": "1", "close": "2", "volume": "3"}}})
            return ws
        body = await request.json() if request.can_read_body else None
        path = request.path
        state["counts"][path] += 1
        state["calls"].append({"path": path, "body": body, "headers": dict(request.headers),
                               "cookies": dict(request.cookies), "query": dict(request.query)})
        if path.endswith("/clients/web/login"):
            assert body == {"email": "person@example.test", "password": "secret-password"}
            if state["malformed_login"]:
                return web.json_response({"data": {"uid": "user-1"}})
            result = {"data": {"uid": "user-1", "email_confirm": True,
                     "double_auth_google": state["flow"] == "totp",
                     "is_authorize": state["flow"] == "direct"}}
            response = web.json_response(result)
            response.set_cookie("p2p_access_token", "general-access", domain=".bitteam.test", path="/", secure=True, httponly=True)
            response.set_cookie("p2p_refresh_token", "general-refresh", domain=".bitteam.test", path="/", secure=True)
            return response
        if path.endswith("/login-2fa"):
            assert body == {"uid": "user-1", "google2fa_secret": "012345"}
            return web.json_response({"data": {"uid": "user-1", "is_authorize": False}})
        if path.endswith("/authorize/send-code"):
            assert body == {"uid": "user-1"}
            return web.json_response({"data": {"delivery_channel": state["channel"]}})
        if path.endswith("/authorize/check-code"):
            assert body == {"uid": "user-1", "code": 123, "is_remember": True}
            if state["reject_code"]:
                return web.json_response({"message": "secret-password", "code": 401101}, status=422)
            return web.json_response({"data": True})
        if path.endswith("/login-auth"):
            assert body is None
            assert request.cookies["p2p_access_token"] == "general-access"
            assert request.cookies["p2p_refresh_token"] == "general-refresh"
            assert "Authorization" not in request.headers
            if state["malformed_tokens"]:
                return web.json_response({"result": {"access": "spot-a0"}})
            return web.json_response({"ok": True, "result": {"access": "spot-a0", "refresh": "spot-r0"}})
        if path.endswith("/refresh-token"):
            assert body == {}
            assert request.headers["Authorization"] == "Bearer spot-r0"
            assert request.cookies["refresh"] == "spot-r0"
            await asyncio.sleep(0.02)
            if state.get("refresh_unavailable"):
                return web.json_response({"code": 500000}, status=503)
            if state["refresh_fail"]:
                return web.json_response({"code": 401010}, status=401)
            return web.json_response({"result": {"access": "spot-a1", "refresh": "spot-r1"}})
        if path.endswith("/address/wallets"):
            if state["expire"] and request.headers.get("Authorization") == "Bearer spot-a0":
                return web.json_response({"code": 401000}, status=401)
            assert request.headers["Authorization"] in ("Bearer spot-a0", "Bearer spot-a1")
            return web.json_response({"ok": True, "result": {"balance": []}})
        if path.endswith("/ccxt/balance"):
            expected = "Basic " + base64.b64encode(b"key:secret").decode()
            assert request.headers["Authorization"] == expected
            assert not request.cookies
            return web.json_response({"ok": True, "result": {}})
        if path.endswith("/logout"):
            return web.json_response({"ok": True})
        if path.endswith("/pairs/precisions"):
            assert "Authorization" not in request.headers
            return web.json_response({"ok": True, "result": {"pairs": {"del_usdt": {
                "price": {"decimals": 6}, "amount": {"decimals": 18}}}}})
        if path.endswith("/pairs"):
            return web.json_response({"result": {"pairs": [{"id": 9, "name": "del_usdt"}]}})
        if path.endswith("/pair/del_usdt"):
            return web.json_response({"result": {"pair": {"id": 9, "name": "del_usdt", "lastPrice": "1.23456789",
                "lastBuy": "9", "lastSell": "1", "volume24": "10"}}})
        if path.endswith("/cmc/orderbook/del_usdt"):
            return web.json_response({"bids": [["1.20", "2"], ["1.19", "3"]], "asks": [["1.21", "5"]]})
        if path.endswith("/cmc/trades/del_usdt"):
            return web.json_response([{"trade_id": 1, "timestamp": 1000, "price": "1.2", "base_volume": "2"},
                                      {"trade_id": 2, "timestamp": 2000, "price": "1.3", "base_volume": "4"}])
        if path.endswith(("/ccxt/ordersOfUser", "/ordersByUser")):
            offset = int(request.query.get("offset", 0))
            data = state.get("pages", {}).get(offset, [{"id": 10, "status": "active"}])
            return web.json_response({"ok": True, "result": {"orders": data}})
        if path.endswith(("/ccxt/tradesOfUser", "/tradesByUser")):
            return web.json_response({"ok": True, "result": {"trades": [{"id": 100, "makerOrderId": 10, "takerOrderId": 11}]}})
        if path.endswith("/ccxt/order/10"):
            return web.json_response({"ok": True, "result": {"id": 10, "status": "executed", "amount": "8.714", "filled": "8.714"}})
        if path.endswith(("/order/cancel", "/ccxt/cancelorder", "/all-orders/cancel", "/ccxt/cancel-all-order",
                          "/withdraw/create", "/withdraw/confirm", "/withdraw/confirmation/email")):
            return web.json_response({"ok": True, "result": {"accepted": True}})
        if path.endswith("/flaky"):
            if state["counts"][path] <= 2:
                return web.json_response({"code": 429000}, status=429, headers={"Retry-After": "0"})
            return web.json_response({"ok": True})
        if path.endswith(("/order/create", "/ccxt/ordercreate")):
            assert body["pairId"] == ('9' if path.endswith('/ccxt/ordercreate') else 9)
            if state["mutation_fail"]:
                return web.json_response({"code": 401000}, status=401)
            return web.json_response({"ok": True, "result": {"id": 10}})
        if path.endswith("/broken"):
            return web.Response(text="secret-password", status=502)
        if path.endswith("/redirect"):
            return web.Response(status=302, headers={"Location": "https://untrusted.test"})
        if path.endswith("/restricted"):
            return web.json_response({"code": 403001}, status=403)
        raise web.HTTPNotFound()

    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=server_ssl)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    clients = []

    async def create(key_mode=False):
        auth = ApiKeyAuth("key", "secret") if key_mode else SessionAuth(auth_url=f"https://auth.bitteam.test:{port}/v1")
        client = BitTeamClient(auth=auth, base_url=f"https://spot.bitteam.test:{port}/trade/api")
        client.rest._session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=client_ssl, resolver=Resolver()),
            cookie_jar=aiohttp.DummyCookieJar() if key_mode else aiohttp.CookieJar())
        client.rest._limiter = RateLimiter(1000, 1)
        clients.append(client)
        return client

    yield state, create
    for client in clients:
        await client.close()
    await runner.cleanup()


@pytest.mark.asyncio
async def test_direct_login_cookie_exchange_and_logout(environment):
    state, create = environment
    client = await create()
    result = await client.login("person@example.test", "secret-password")
    assert result.state == AuthState.READY
    await client.get_balance()
    await client.logout()
    assert client.auth.state == AuthState.NEW
    assert len(client.rest._session.cookie_jar) == 0
    with pytest.raises(RuntimeError):
        await client.get_balance()


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["email", "telegram"])
async def test_totp_then_device_code_both_delivery_channels(environment, channel):
    state, create = environment
    state.update(flow="totp", channel=channel)
    client = await create()
    assert (await client.login("person@example.test", "secret-password")).state == AuthState.TWO_FACTOR_REQUIRED
    with pytest.raises(RuntimeError):
        await client.get_balance()
    assert (await client.submit_totp("012345")).state == AuthState.DEVICE_CONFIRMATION_REQUIRED
    assert (await client.send_device_code()).delivery_channel == channel
    assert (await client.confirm_device("0123", remember=True)).state == AuthState.READY
    await client.get_balance()
    assert state["counts"]["/v1/authorize/check-code"] == 1


@pytest.mark.asyncio
async def test_bad_device_code_can_be_retried_and_does_not_leak_password(environment):
    state, create = environment
    state.update(flow="device", reject_code=True)
    client = await create()
    await client.login("person@example.test", "secret-password")
    with pytest.raises(BitTeamAPIError) as error:
        await client.confirm_device("0123", remember=True)
    assert "secret-password" not in str(error.value)
    assert client.auth.state == AuthState.DEVICE_CONFIRMATION_REQUIRED
    state["reject_code"] = False
    assert (await client.confirm_device("0123", remember=True)).state == AuthState.READY


@pytest.mark.asyncio
async def test_concurrent_expired_reads_share_one_refresh(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    state["expire"] = True
    await asyncio.gather(*(client.get_balance() for _ in range(12)))
    assert state["counts"]["/trade/api/refresh-token"] == 1
    assert client.auth.headers() == {"Authorization": "Bearer spot-a1"}
    assert all("Bearer spot-r0" != c["headers"].get("Authorization") for c in state["calls"] if c["path"].endswith(("balance", "wallets")))


@pytest.mark.asyncio
async def test_failed_refresh_expires_and_clears_cookies(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    state.update(expire=True, refresh_fail=True)
    with pytest.raises(AuthenticationError):
        await client.get_balance()
    assert client.auth.state == AuthState.EXPIRED
    assert len(client.rest._session.cookie_jar) == 0


@pytest.mark.asyncio
async def test_mutation_is_never_replayed(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    state["mutation_fail"] = True
    with pytest.raises(AuthenticationError):
        await client.create_order("DEL/USDT", "buy", "limit", "1.1234567", "10")
    assert state["counts"]["/trade/api/order/create"] == 1
    assert state["counts"]["/trade/api/refresh-token"] == 0


@pytest.mark.asyncio
async def test_basic_mode_compatibility_and_public_no_authorization(environment):
    state, create = environment
    client = await create(key_mode=True)
    assert (await client.init()).state == AuthState.READY
    assert client.rest._precisions["del_usdt"] == {"price": 6, "amount": 18}
    await client.get_balance()
    with pytest.raises(RuntimeError):
        await client.login("person@example.test", "secret-password")
    await client.create_order("DEL/USDT", "buy", "limit", "1", "10")
    assert state["counts"]["/trade/api/ccxt/ordercreate"] == 1
    assert state["counts"]["/trade/api/refresh-token"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["broken", "redirect", "restricted"])
async def test_bad_responses_no_refresh_no_secret_echo(environment, path):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    with pytest.raises(BitTeamAPIError) as error:
        await client.rest._request("GET", "/" + path)
    assert "secret-password" not in str(error.value)
    assert state["counts"]["/trade/api/refresh-token"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["malformed_login", "malformed_tokens"])
async def test_malformed_success_is_not_authenticated(environment, case):
    state, create = environment
    state[case] = True
    client = await create()
    with pytest.raises(AuthenticationError):
        await client.login("person@example.test", "secret-password")
    assert client.auth.state != AuthState.READY


@pytest.mark.asyncio
async def test_origin_and_cookie_scope_isolation(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    with pytest.raises(ValueError):
        await client.rest._send("GET", "https://untrusted.test", headers=client.auth.headers())
    cookies = client.rest._session.cookie_jar
    assert not cookies.filter_cookies(__import__("yarl").URL("https://untrusted.test"))
    assert "access" not in cookies.filter_cookies(__import__("yarl").URL(client.auth.auth_url))
    second = await create()
    assert len(second.rest._session.cookie_jar) == 0


@pytest.mark.asyncio
async def test_limiter_does_not_deadlock():
    limiter = RateLimiter(1, 0.01)
    await asyncio.wait_for(asyncio.gather(*(limiter.acquire() for _ in range(5))), 1)


@pytest.mark.asyncio
async def test_refresh_server_failure_preserves_session(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    state["refresh_unavailable"] = True
    with pytest.raises(BitTeamAPIError):
        await client.refresh()
    assert client.auth.state == AuthState.READY
    assert client.auth.headers() == {"Authorization": "Bearer spot-a0"}
    assert len(client.rest._session.cookie_jar) > 0


@pytest.mark.asyncio
async def test_logout_waits_for_refresh_then_clears_session(environment):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    refresh = asyncio.create_task(client.refresh())
    await asyncio.sleep(0.005)
    logout = asyncio.create_task(client.logout())
    await asyncio.gather(refresh, logout)
    assert client.auth.state == AuthState.NEW
    assert len(client.rest._session.cookie_jar) == 0
    with pytest.raises(AuthenticationError):
        client.auth.headers()


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["12345", "1234567", "１２３４５６", "abcdef"])
async def test_invalid_totp_is_not_sent(environment, code):
    state, create = environment
    state["flow"] = "totp"
    client = await create()
    await client.login("person@example.test", "secret-password")
    with pytest.raises(ValueError):
        await client.submit_totp(code)
    assert state["counts"]["/v1/clients/web/login-2fa"] == 0


@pytest.mark.asyncio
async def test_mutation_timeout_is_not_replayed(environment, monkeypatch):
    state, create = environment
    client = await create()
    await client.login("person@example.test", "secret-password")
    calls = 0
    async def timeout(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise asyncio.TimeoutError()
    monkeypatch.setattr(client.rest, "_send", timeout)
    with pytest.raises(asyncio.TimeoutError):
        await client.rest._request("POST", "/order/create", data={})
    assert calls == 1


def test_credentials_hidden_and_configuration_validated():
    assert "secret" not in repr(ApiKeyAuth("key", "secret"))
    with pytest.raises(ValueError):
        BitTeamRestAPI("key", "secret", auth=SessionAuth())
    with pytest.raises(ValueError):
        BitTeamRestAPI(auth=SessionAuth(), base_url="http://bit.team/trade/api")
