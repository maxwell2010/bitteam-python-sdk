"""Validated endpoint access to the bundled official OpenAPI snapshot."""
import json
import math
import re
from importlib.resources import files
from urllib.parse import quote

from .auth import SessionAuth


def snake(value):
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()


def endpoint_name(verb, path):
    parts = []
    for part in path.removeprefix("/trade/api/").split("/"):
        if part:
            parts.append("by_" + snake(part[1:-1]) if part.startswith("{") else snake(part))
    return verb.lower() + "_" + "_".join(parts)


SPEC = json.loads(files("bitteam_sdk").joinpath("schemas/openapi.json").read_text(encoding="utf-8"))
CATALOG = {}
for _path, _ops in SPEC["paths"].items():
    for _verb, _op in _ops.items():
        if _verb not in ("get", "post", "delete", "put", "patch"):
            continue
        _name = endpoint_name(_verb, _path)
        # One current Altyn route has a placeholder but omits its parameter
        # declaration. Infer only its name/location from the URL template.
        _op = dict(_op)
        _parameters = list(_op.get("parameters", []))
        for _parameter in re.findall(r"\{([^}]+)\}", _path):
            if not any(p.get("in") == "path" and p.get("name") == _parameter for p in _parameters):
                _parameters.append({"name": _parameter, "in": "path", "type": "string", "required": True})
        _op["parameters"] = _parameters
        CATALOG[_name] = {"method": _verb.upper(), "path": _path.removeprefix("/trade/api"),
            "operation": _op, "server_only": "/webhook" in _path or "/dev/" in _path,
            "public": bool(set(_op.get("tags", [])) & {"PUBLIC", "CMC", "MARKDOWN"})}
        if _path in ("/trade/api/altyn/banks", "/trade/api/altyn/client/"):
            # Both return 401010 anonymously despite Swagger's PUBLIC tag.
            CATALOG[_name]["public"] = False


def validate(value, schema, label):
    """Validate documented constraints without including submitted secrets in errors."""
    kind = schema.get("type")
    if value is None:
        raise ValueError(f"{label} cannot be null")
    if schema.get("x-type") == "object" and isinstance(value, dict):
        return
    if kind == "string" and not isinstance(value, str):
        raise ValueError(f"{label} must be a string")
    if kind in ("integer", "number"):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{label} must be a finite number")
        if kind == "integer" and not isinstance(value, int):
            raise ValueError(f"{label} must be an integer")
    if kind == "boolean" and not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    if kind == "array":
        if not isinstance(value, list):
            raise ValueError(f"{label} must be a list")
        for item in value:
            validate(item, schema.get("items", {}), label + " item")
    if kind == "object" and not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{label} is not an allowed value")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get("maxLength", float("inf")):
            raise ValueError(f"{label} has invalid length")
        if schema.get("pattern") and not re.fullmatch(schema["pattern"], value):
            raise ValueError(f"{label} has invalid format")
    if kind in ("integer", "number"):
        if value < schema.get("minimum", -float("inf")) or value > schema.get("maximum", float("inf")):
            raise ValueError(f"{label} is out of range")


def query_params(params):
    result = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, dict):
            for nested, item in value.items():
                result[f"{key}[{nested}]"] = str(item).lower() if isinstance(item, bool) else item
        else:
            result[key] = str(value).lower() if isinstance(value, bool) else value
    return result


class EndpointAPI:
    def __init__(self, transport):
        self.transport = transport

    async def call(self, name, *, path=None, params=None, data=None):
        if name not in CATALOG:
            raise ValueError("Unknown BitTeam endpoint")
        entry = CATALOG[name]
        if entry["server_only"]:
            raise NotImplementedError("This operation is a server callback or exchange administration endpoint")
        endpoint = entry["path"]
        if endpoint in ("/login-auth", "/refresh-token", "/logout", "/refresh-logout"):
            if path or params or data:
                raise ValueError("Managed authentication methods do not accept raw parameters")
            auth = self.transport.auth
            if not isinstance(auth, SessionAuth):
                raise RuntimeError("This operation requires SessionAuth")
            if endpoint == "/login-auth":
                return await auth.open_spot_session()
            if endpoint == "/refresh-token":
                return await auth.refresh()
            return await auth.logout(use_refresh=endpoint == "/refresh-logout")
        path = dict(path or {})
        params = dict(params or {})
        parameters = entry["operation"].get("parameters", [])
        body_schema = None
        expected_paths = {p["name"] for p in parameters if p["in"] == "path"}
        if set(path) != expected_paths:
            raise ValueError("Path parameters do not match the documented endpoint")
        for parameter in parameters:
            where, key = parameter["in"], parameter["name"]
            if where == "body":
                body_schema = parameter.get("schema", {})
                continue
            container = path if where == "path" else params
            if parameter.get("required") and key not in container:
                raise ValueError(f"Required parameter: {key}")
            if key in container:
                # Path ids accept int as well as a string representation.
                if where == "path":
                    value = str(container[key])
                    if not value or value in (".", "..") or any(c in value for c in ("/", "\\", "?", "#", "%")):
                        raise ValueError("Invalid path parameter")
                    endpoint = endpoint.replace("{" + key + "}", quote(value, safe=""))
                else:
                    validate(container[key], parameter, key)
        if data is not None and not isinstance(data, dict):
            raise ValueError("Request body must be a dictionary")
        if body_schema is not None:
            payload = data or {}
            for key in body_schema.get("required", []):
                if key not in payload:
                    raise ValueError(f"Required body field: {key}")
            for key, value in payload.items():
                validate(value, body_schema.get("properties", {}).get(key, {}), key)
        return await self.transport._request(entry["method"], endpoint, params=query_params(params),
                                             data=data, public=entry["public"])
