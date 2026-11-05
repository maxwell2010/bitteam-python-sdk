"""OpenAPI contract coverage and validation, without external side effects."""
import inspect
import pytest
from bitteam_sdk.api import BitTeamAPI
from bitteam_sdk.endpoints import CATALOG, SPEC, endpoint_name, snake
from bitteam_sdk.auth import PublicAuth


class Recorder:
    def __init__(self):
        self.calls = []
        self.auth = PublicAuth()

    async def _request(self, method, endpoint, **kwargs):
        self.calls.append((method, endpoint, kwargs))
        return {"contract_response": True}


def sample(schema):
    if schema.get("enum"):
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "integer":
        return int(schema.get("minimum", 1))
    if kind == "number":
        return schema.get("minimum", 1)
    if kind == "boolean":
        return True
    if kind == "array":
        return [sample(schema.get("items", {}))]
    if kind == "object":
        return {}
    return "A" * max(10, schema.get("minLength", 0)) if schema.get("pattern") else "x" * max(1, schema.get("minLength", 1))


@pytest.mark.asyncio
@pytest.mark.parametrize("name", sorted(CATALOG))
async def test_every_documented_endpoint_has_named_callable_and_contract(name):
    entry = CATALOG[name]
    api, recorder = None, Recorder()
    api = BitTeamAPI(recorder)
    method = getattr(api, name)
    assert inspect.iscoroutinefunction(method)
    params, data, path = {}, {}, {}
    for parameter in entry["operation"].get("parameters", []):
        if parameter["in"] == "path":
            path[snake(parameter["name"])] = sample(parameter)
        elif parameter["in"] == "query" and parameter.get("required"):
            params[parameter["name"]] = sample(parameter)
        elif parameter["in"] == "body":
            schema = parameter.get("schema", {})
            data = {key: sample(schema.get("properties", {}).get(key, {})) for key in schema.get("required", [])}
    kwargs = dict(path, params=params, data=data or None)
    if entry["server_only"]:
        with pytest.raises(NotImplementedError):
            await method(**kwargs)
        assert not recorder.calls
    elif entry["path"] in ("/login-auth", "/refresh-token", "/logout", "/refresh-logout"):
        with pytest.raises(RuntimeError):
            await method(**kwargs)
        assert not recorder.calls
    else:
        assert await method(**kwargs) == {"contract_response": True}
        verb, url, values = recorder.calls[0]
        assert verb == entry["method"]
        assert "{" not in url
        assert values["public"] == entry["public"]
        assert url.startswith("/")


@pytest.mark.asyncio
async def test_filters_are_encoded_as_exchange_bracket_parameters():
    recorder = Recorder()
    api = BitTeamAPI(recorder)
    await api.get_orders(params={"where": {"pairId": 24}, "order": {"id": "DESC"}})
    assert recorder.calls[0][2]["params"] == {"where[pairId]": 24, "order[id]": "DESC"}


@pytest.mark.asyncio
@pytest.mark.parametrize("identity", ["../profile", "%2fsecret", "x?token=y", "..", "a\\b", ""])
async def test_path_values_cannot_escape_route(identity):
    recorder = Recorder()
    with pytest.raises(ValueError):
        await BitTeamAPI(recorder).get_ccxt_order_by_id(identity)
    assert not recorder.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {}, {"pairId": 1},
    {"pairId": 1, "side": "invalid", "type": "conditional", "amount": "1", "price": "1", "slippage": 2},
    {"pairId": 1, "side": "buy", "type": "conditional", "amount": "1", "price": "1", "slippage": 100},
    {"pairId": 1, "side": "buy", "type": "conditional", "amount": "1", "price": "1", "slippage": True},
])
async def test_bad_order_contract_rejected_before_network(payload):
    recorder = Recorder()
    with pytest.raises(ValueError):
        await BitTeamAPI(recorder).post_order_conditional_create(data=payload)
    assert not recorder.calls


def test_catalog_matches_swagger_exactly():
    expected = {endpoint_name(verb, path) for path, ops in SPEC["paths"].items() for verb in ops}
    assert expected == set(CATALOG)
    assert len(expected) == 110
