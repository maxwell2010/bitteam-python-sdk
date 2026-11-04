"""Isolated core-only *source* smoke; this is not an installed-wheel check.

Run with a fresh venv containing only requirements-sdk.txt, without installing
the SDK: <core-venv-python> -I scripts_sdk/check_core_source.py --source-root ROOT
"""
import argparse
import asyncio
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import socket
import sys


def forbidden(*args, **kwargs):
    raise AssertionError("Core source smoke must not open HTTP/network or session cache")


def smoke(source_root):
    if not sys.flags.isolated:
        raise RuntimeError("Run core source smoke with Python -I")
    root = Path(source_root).resolve(strict=True)
    expected = root / "bitteam_sdk" / "__init__.py"
    if not expected.is_file():
        raise ValueError("Selected source root does not contain bitteam_sdk/__init__.py")

    absent = ("pandas", "plotly", "asyncpg", "aiosqlite")
    for name in absent:
        if importlib.util.find_spec(name) is not None:
            raise AssertionError("Core-only environment contains optional module: " + name)
        try:
            importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:
            pass
        else:
            raise AssertionError("Core-only environment contains optional distribution: " + name)
    try:
        importlib.metadata.distribution("bitteam-python-sdk")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise AssertionError("SDK must not be installed for this source-only check")
    if importlib.util.find_spec("bitteam_sdk") is not None:
        raise AssertionError("SDK was importable before selecting the explicit source root")

    # Permit the event loop's local socketpair while rejecting actual connects.
    socket.socket.connect = forbidden
    socket.socket.connect_ex = forbidden
    socket.create_connection = forbidden
    socket.getaddrinfo = forbidden
    import aiohttp
    aiohttp.ClientSession = forbidden

    def audit_cache_access(event, args):
        if event == "open" and isinstance(args[0], (str, bytes)):
            path = str(args[0]).replace("\\", "/").casefold()
            if "/bitteamsdk/sessions/" in path:
                raise AssertionError("Core source smoke cannot access a user session cache")
    sys.addaudithook(audit_cache_access)

    sys.path.insert(0, str(root))
    import bitteam_sdk as sdk
    if Path(sdk.__file__).resolve() != expected.resolve():
        raise AssertionError("Imported SDK does not match the explicitly selected source root")
    for name in ("__init__", "load", "save", "delete"):
        setattr(sdk.SessionCache, name, forbidden)
    sdk.SessionCache.exists = property(forbidden)
    if not sdk.__all__ or len(sdk.__all__) != len(set(sdk.__all__)):
        raise AssertionError("Core exports are empty or duplicated")
    for name in sdk.__all__:
        if getattr(sdk, name, None) is None:
            raise AssertionError("Missing core export: " + name)

    async def check_clients():
        for auth in (None, sdk.SessionAuth()):
            client = sdk.BitTeamClient(auth=auth) if auth is not None else sdk.BitTeamClient()
            if client.rest._session is not None:
                raise AssertionError("Core construction unexpectedly opened an HTTP session")
            await client.close()
            await client.close()
            if not client._closed or not client.rest._closed:
                raise AssertionError("Core close did not finish")
    asyncio.run(check_clients())

    standard = sdk.prepare_p2p_withdrawal(44, address="synthetic-only", amount="1.0000")
    internal = sdk.prepare_p2p_internal_transfer(7, "2.0000")
    if standard.payload["sum"] != "1.0000" or internal.payload["internal_request"] is not True:
        raise AssertionError("Pure core plan contract changed")
    evidence = sdk.transaction_evidence({"type": "withdraw", "status": 2}, source="p2p")
    if evidence.state != "unknown" or evidence.ui_state != "done":
        raise AssertionError("UI labels changed conservative core evidence state")
    if any(name in sys.modules for name in absent):
        raise AssertionError("Core construction imported optional functionality")
    print(json.dumps({"check": "core-source-only", "sdk_source": str(expected.resolve()),
        "sdk_version": sdk.__version__, "python": sys.version.split()[0],
        "aiohttp": importlib.metadata.version("aiohttp"),
        "certifi": importlib.metadata.version("certifi"),
        "optional_modules_absent": list(absent), "exports": len(sdk.__all__),
        "http_network_cache": "forbidden", "result": "passed"}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    args = parser.parse_args()
    smoke(args.source_root)


if __name__ == "__main__":
    main()
