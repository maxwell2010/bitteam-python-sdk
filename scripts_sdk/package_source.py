"""Create a standalone source archive from an explicit file allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from bitteam_sdk import __version__
output = root / 'output-sdk'
output.mkdir(exist_ok=True)
archive = output / f'bitteam-python-sdk-{__version__}-source.zip'
include = [root / p for p in ['pyproject.toml','MANIFEST.in','requirements-sdk.txt','requirements-sdk-dev.txt']]
include.append(root / '.github/workflows/sdk.yml')
for folder in ['bitteam_sdk','tests_sdk','scripts_sdk']:
    for path in (root / folder).rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix in ('.py','.md','.ini','.json'):
            include.append(path)
with ZipFile(archive, 'w', ZIP_DEFLATED) as target:
    target.writestr('README.md', (root / 'bitteam_sdk/README.md').read_text(encoding='utf-8-sig'))
    for path in sorted(set(include)):
        target.write(path, path.relative_to(root).as_posix())
with ZipFile(archive) as target:
    for name in target.namelist():
        assert not name.lower().endswith(('.env','.db','.log','.pyc'))
checksums = []
for path in sorted(output.iterdir()):
    if path.is_file() and (path.suffix in ('.whl','.zip') or path.name.endswith('.tar.gz')):
        checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
(output / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='ascii')
print(archive)
