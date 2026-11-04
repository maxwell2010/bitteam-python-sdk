"""Install a built wheel in a fresh venv and smoke-test it without network calls.

Run after `python -m build --wheel --sdist --outdir dist-sdk-ci`:
    python scripts_sdk/check_wheel.py --dist-dir dist-sdk-ci
Alternatively pass --wheel /absolute/path/to/a/specific.whl.
Only pip dependency installation uses the network; the SDK smoke is offline.
"""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


async def installed_smoke():
    from importlib import metadata, resources
    import socket
    import aiohttp
    import bitteam_sdk
    from bitteam_sdk.endpoints import CATALOG
    from bitteam_sdk.p2p_api import P2P_CATALOG

    def forbidden(*args, **kwargs):
        raise AssertionError("Installed SDK smoke must not open a network connection")

    # No client context manager/init/login, OS cache, or credential handling.
    socket.create_connection = forbidden
    socket.socket.connect = forbidden
    aiohttp.ClientSession = forbidden
    package = Path(bitteam_sdk.__file__).resolve()
    if not package.is_relative_to(Path(sys.prefix).resolve()):
        raise AssertionError("SDK was imported outside the isolated virtual environment")
    if metadata.version("bitteam-python-sdk") != bitteam_sdk.__version__:
        raise AssertionError("Distribution version differs from package version")
    root = resources.files("bitteam_sdk")
    for name in ("openapi.json", "p2p_site.json"):
        payload = json.loads(root.joinpath("schemas", name).read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not payload:
            raise AssertionError("Missing or empty bundled schema: " + name)
    if not CATALOG or not P2P_CATALOG:
        raise AssertionError("Installed endpoint catalogs are empty")
    # Optional storage modules are shipped, but importing them needs their extras.
    # This environment deliberately installs only core wheel dependencies.
    for module in ("sqlite.py", "postgres.py"):
        if not root.joinpath("storage", module).is_file():
            raise AssertionError("Missing optional storage module: " + module)
    client = bitteam_sdk.BitTeamClient()
    try:
        for owner, method in ((client.api, "get_pairs"), (client.site, "get_coins"),
                              (client.p2p, "get_accounts"), (client.p2p, "get_withdrawal"),
                              (client, "wait_for_withdrawal")):
            if not callable(getattr(owner, method, None)):
                raise AssertionError("Missing installed SDK method: " + method)
    finally:
        await client.close()
    print("Installed wheel smoke passed:", bitteam_sdk.__version__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--wheel", type=Path)
    choice.add_argument("--dist-dir", type=Path, default=Path("dist-sdk-ci"))
    parser.add_argument("--installed", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.installed:
        asyncio.run(installed_smoke())
        return
    candidates = [args.wheel] if args.wheel else list(args.dist_dir.glob("*.whl"))
    if len(candidates) != 1 or not candidates[0].is_file():
        parser.error("Provide exactly one built wheel, or use --wheel to select it explicitly")
    wheel = candidates[0].resolve()
    script = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="bitteam-wheel-smoke-") as temporary:
        directory = Path(temporary)
        environment = directory / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install", str(wheel)], cwd=directory, check=True)
        subprocess.run([str(python), "-I", str(script), "--installed"], cwd=directory, check=True)


if __name__ == "__main__":
    main()
