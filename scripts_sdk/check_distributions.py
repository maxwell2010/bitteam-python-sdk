"""Inspect release artifacts and test four fresh installed environments.

Only pip installation uses package-network access. SDK smoke checks forbid
network and SessionCache access. PostgreSQL driver import is not a server test.
"""
import argparse
import ast
import asyncio
import importlib.util
from importlib import metadata, resources
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile


OPTIONALS = {'pandas': 'pandas', 'plotly': 'plotly', 'asyncpg': 'asyncpg', 'aiosqlite': 'aiosqlite'}
EXTRAS = 'charts,sqlite,postgres'


def source_version(root):
    tree = ast.parse((root / 'bitteam_sdk/__init__.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('Missing source version')


def inspect_artifacts(wheel, sdist, root):
    spec = importlib.util.spec_from_file_location('_release_source_plan', root / 'scripts_sdk/package_source.py')
    planner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(planner)
    source = set(planner.source_tree_inventory(root))
    version = source_version(root)
    expected_sdk = {name for name in source if name.startswith('bitteam_sdk/') and (
        name.endswith(('.py', '.md')) or '/schemas/' in name or name in planner.REPORTS)}

    def validate_names(names):
        folded = set()
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or path.as_posix() != name or '\\' in name:
                raise ValueError('Unsafe archive member')
            if name.casefold() in folded:
                raise ValueError('Duplicate archive member')
            folded.add(name.casefold())

    with zipfile.ZipFile(wheel) as archive:
        members = archive.infolist()
        if any(stat.S_ISLNK(member.external_attr >> 16) for member in members):
            raise ValueError('Wheel contains a symlink')
        wheel_names = {member.filename for member in members if not member.is_dir()}
        validate_names([member.filename.rstrip('/') for member in members])
        metadata_roots = {name.split('/')[0] for name in wheel_names if '.dist-info/' in name}
        if metadata_roots != {f'bitteam_python_sdk-{version}.dist-info'}:
            raise ValueError('Wheel metadata directory mismatch')
        allowed_metadata = {'METADATA', 'WHEEL', 'RECORD', 'top_level.txt'}
        if any(name.split('/', 1)[1] not in allowed_metadata for name in wheel_names if name.split('/')[0] in metadata_roots):
            raise ValueError('Wheel contains unexpected metadata payload')
        payload = {name for name in wheel_names if name.split('/')[0] not in metadata_roots}
        if not expected_sdk <= payload or not payload <= {name for name in source if name.startswith('bitteam_sdk/')}:
            raise ValueError('Wheel payload differs from public SDK inventory')
        if any(archive.read(name) != (root / name).read_bytes() for name in payload):
            raise ValueError('Wheel SDK content differs from selected source')
    with tarfile.open(sdist, 'r:gz') as archive:
        members = archive.getmembers()
        if any(not (member.isfile() or member.isdir()) for member in members):
            raise ValueError('Source distribution contains a special member')
        validate_names([member.name.rstrip('/') for member in members])
        roots = {PurePosixPath(member.name).parts[0] for member in members}
        if len(roots) != 1:
            raise ValueError('Source distribution root mismatch')
        names = {'/'.join(PurePosixPath(member.name).parts[1:]) for member in members if member.isfile()}
        generated = {'PKG-INFO', 'setup.cfg'}
        egg_files = {'PKG-INFO', 'SOURCES.txt', 'dependency_links.txt', 'requires.txt', 'top_level.txt'}
        for name in names:
            path = PurePosixPath(name)
            egg = len(path.parts) == 2 and path.parts[0] == 'bitteam_python_sdk.egg-info' and path.name in egg_files
            if not planner.public_source_path(name) and name not in generated and not egg:
                raise ValueError('Source distribution contains a non-public payload')
        if not source <= names or not {'README.md', 'CHANGELOG.md'} <= names:
            raise ValueError('Source distribution omits public source inputs')
        prefix = next(iter(roots))
        for name in source:
            stream = archive.extractfile(prefix + '/' + name)
            if stream is None or stream.read() != (root / name).read_bytes():
                raise ValueError('Source distribution content differs from selected source')
    return {'wheel_files': len(wheel_names), 'sdist_files': len(names)}


async def installed_smoke(mode, expected_version):
    import socket
    import aiohttp

    def forbidden(*args, **kwargs):
        raise AssertionError('Installed smoke forbids network and session-cache operations')

    for name in ('create_connection', 'getaddrinfo', 'gethostbyname', 'gethostbyaddr'):
        setattr(socket, name, forbidden)
    socket.socket.connect = socket.socket.connect_ex = forbidden
    aiohttp.ClientSession = forbidden
    if mode == 'core':
        for module, distribution in OPTIONALS.items():
            assert importlib.util.find_spec(module) is None, 'Optional module unexpectedly installed'
            try:
                metadata.version(distribution)
            except metadata.PackageNotFoundError:
                pass
            else:
                raise AssertionError('Optional distribution unexpectedly installed')
    import bitteam_sdk as sdk
    assert Path(sdk.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert metadata.version('bitteam-python-sdk') == sdk.__version__ == expected_version
    assert len(sdk.__all__) == len(set(sdk.__all__)) == 38
    assert all(hasattr(sdk, name) for name in sdk.__all__)
    for name in ('__init__', 'load', 'save', 'delete'):
        setattr(sdk.SessionCache, name, forbidden)
    sdk.SessionCache.exists = property(forbidden)
    package = resources.files('bitteam_sdk')
    for name in ('openapi.json', 'p2p_site.json'):
        assert isinstance(json.loads(package.joinpath('schemas', name).read_text(encoding='utf-8')), dict)
    from bitteam_sdk.endpoints import CATALOG
    from bitteam_sdk.p2p_api import P2P_CATALOG
    assert len(CATALOG) == 110 and len(P2P_CATALOG) == 84
    for auth in (sdk.PublicAuth(), sdk.SessionAuth()):
        client = sdk.BitTeamClient(auth=auth)
        await client.close()
        await client.close()
    result = {'mode': mode, 'version': sdk.__version__, 'exports': len(sdk.__all__), 'status': 'passed'}
    if mode == 'extras':
        import asyncpg
        import pandas
        import plotly
        import aiosqlite
        from bitteam_sdk.models import Kline
        from bitteam_sdk.storage.sqlite import SQLiteStorage
        from bitteam_sdk.charting import plot_candles
        store = SQLiteStorage(':memory:', retention=None)
        try:
            await store.init()
            candle = Kline('SYN_USDT', '1m', 0, '1.00', '3.00', '1.00', '2.00', '4.00')
            await store.save_kline(candle)
            rows = await store.get_klines('SYN_USDT', '1m')
            assert len(rows) == 1 and tuple(rows[0]) == (0, '1.00', '3.00', '1.00', '2.00', '4.00')
        finally:
            await store.close()
        empty = Kline.to_dataframe([])
        assert empty.empty and list(empty.columns) == ['open', 'high', 'low', 'close', 'volume']
        assert empty.resample('2min').sum().empty
        frame = Kline.to_dataframe(rows)
        assert frame.resample('2min').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).iloc[0]['volume'] == 4
        figure = plot_candles(frame, show=False)
        assert figure.data[0].type == 'candlestick' and 'candlestick' in figure.to_json()
        result['dependencies'] = {name: metadata.version(distribution) for name, distribution in OPTIONALS.items()}
        result['postgres'] = 'driver imported only; server runtime is a separate check'
    print(json.dumps(result, sort_keys=True))


def verify(wheel, sdist, root):
    expected = source_version(root)
    inspection = inspect_artifacts(wheel, sdist, root)
    checks = []
    script = Path(__file__).resolve()
    for artifact in (wheel, sdist):
        for mode in ('core', 'extras'):
            with tempfile.TemporaryDirectory(prefix='bitteam-release-install-') as temporary:
                directory = Path(temporary)
                venv.EnvBuilder(with_pip=True).create(directory / 'venv')
                python = directory / 'venv' / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
                requirement = str(artifact) + (f'[{EXTRAS}]' if mode == 'extras' else '')
                subprocess.run([str(python), '-I', '-m', 'pip', '--isolated', 'install', '--no-cache-dir', requirement], cwd=directory, check=True, capture_output=True, text=True, timeout=300)
                result = subprocess.run([str(python), '-I', '-B', str(script), '--installed', '--mode', mode, '--expected-version', expected], cwd=directory, check=True, capture_output=True, text=True, timeout=60)
                row = json.loads(result.stdout)
                assert row['status'] == 'passed'
                row['artifact'] = 'wheel' if artifact == wheel else 'sdist'
                checks.append(row)
    return {'status': 'passed', 'inspection': inspection, 'installed': checks}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path)
    parser.add_argument('--sdist', type=Path)
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--installed', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=('core', 'extras'), default='core', help=argparse.SUPPRESS)
    parser.add_argument('--expected-version', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.installed:
        asyncio.run(installed_smoke(args.mode, args.expected_version))
        return 0
    if args.wheel is None or args.sdist is None:
        parser.error('--wheel and --sdist are required')
    try:
        result = verify(args.wheel.resolve(), args.sdist.resolve(), args.source_root.resolve())
    except Exception:
        print(json.dumps({'status': 'failed', 'error': 'Distribution verification failed; no raw installer diagnostics exported'}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
