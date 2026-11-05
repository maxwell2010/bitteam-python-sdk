"""Distribution orchestration policy; actual builds/installs are separate checks."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location('release_distributions', ROOT / 'scripts_sdk/check_distributions.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_four_installations_use_fresh_venvs_isolation_and_only_selected_artifacts(monkeypatch, tmp_path):
    module = load()
    monkeypatch.setattr(module, 'source_version', lambda root: '1.7.0')
    monkeypatch.setattr(module, 'inspect_artifacts', lambda *args: {'synthetic': True})
    environments = []
    class Builder:
        def __init__(self, **kwargs): assert kwargs == {'with_pip': True}
        def create(self, path): environments.append(path)
    monkeypatch.setattr(module.venv, 'EnvBuilder', Builder)
    calls = []
    def run(command, **kwargs):
        calls.append((command, kwargs))
        mode = 'extras' if '--mode' in command and command[command.index('--mode')+1] == 'extras' else 'core'
        return SimpleNamespace(stdout=json.dumps({'status': 'passed', 'mode': mode}))
    monkeypatch.setattr(module.subprocess, 'run', run)
    wheel, sdist = tmp_path / 'synthetic.whl', tmp_path / 'synthetic.tar.gz'
    result = module.verify(wheel, sdist, ROOT)
    assert len(environments) == len(set(environments)) == 4
    assert [row['artifact'] for row in result['installed']] == ['wheel', 'wheel', 'sdist', 'sdist']
    for index in range(4):
        install, smoke = calls[index*2:index*2+2]
        artifact = wheel if index < 2 else sdist
        suffix = '[charts,sqlite,postgres]' if index % 2 else ''
        assert install[0][1:] == ['-I', '-m', 'pip', '--isolated', 'install', '--no-cache-dir', str(artifact)+suffix]
        assert smoke[0][1:3] == ['-I', '-B']
        assert '--installed' in smoke[0]
        assert install[1]['cwd'] == smoke[1]['cwd'] != ROOT
        assert install[1]['timeout'] == 300 and smoke[1]['timeout'] == 60


def test_installer_diagnostics_are_not_exported(monkeypatch, capsys):
    module = load()
    def fail(*args): raise RuntimeError('SYNTHETIC-secret-driver-data')
    monkeypatch.setattr(module, 'verify', fail)
    assert module.main(['--wheel', 'synthetic.whl', '--sdist', 'synthetic.tar.gz']) == 1
    output = capsys.readouterr()
    assert 'SYNTHETIC' not in output.out + output.err
    assert json.loads(output.out)['status'] == 'failed'


def test_missing_artifacts_cannot_start_installer(monkeypatch):
    module = load()
    monkeypatch.setattr(module, 'verify', lambda *args: pytest.fail('Must reject CLI first'))
    with pytest.raises(SystemExit) as error:
        module.main([])
    assert error.value.code == 2


def artifacts(tmp_path):
    import io
    import tarfile
    import zipfile
    root = tmp_path / 'source'
    (root / 'scripts_sdk').mkdir(parents=True)
    (root / 'bitteam_sdk').mkdir()
    (root / 'scripts_sdk/package_source.py').write_bytes((ROOT / 'scripts_sdk/package_source.py').read_bytes())
    (root / 'bitteam_sdk/__init__.py').write_text('__version__ = "1.7.0"\n', encoding='utf-8')
    for name in ('README.md', 'CHANGELOG.md'):
        (root / name).write_text('Synthetic public source\n', encoding='utf-8')
    wheel, sdist = tmp_path / 'synthetic.whl', tmp_path / 'synthetic.tar.gz'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.write(root / 'bitteam_sdk/__init__.py', 'bitteam_sdk/__init__.py')
        archive.writestr('bitteam_python_sdk-1.7.0.dist-info/METADATA', 'Name: synthetic\n')
    with tarfile.open(sdist, 'w:gz') as archive:
        for path in root.rglob('*'):
            if path.is_file(): archive.add(path, arcname='synthetic-1.7.0/' + path.relative_to(root).as_posix())
    return root, wheel, sdist


def test_archive_inspection_accepts_matching_public_bytes(tmp_path):
    root, wheel, sdist = artifacts(tmp_path)
    result = load().inspect_artifacts(wheel, sdist, root)
    assert result['wheel_files'] == 2 and result['sdist_files'] == 4


@pytest.mark.parametrize('extra', ['../outside.py', 'bitteam_sdk/cookies-private.py', 'bitteam_sdk/work/private.py', 'BITTEAM_SDK/__INIT__.PY'])
def test_archive_inspection_rejects_nonpublic_or_ambiguous_members(tmp_path, extra):
    import zipfile
    root, wheel, sdist = artifacts(tmp_path)
    with zipfile.ZipFile(wheel, 'a') as archive:
        archive.writestr(extra, 'synthetic')
    with pytest.raises(ValueError):
        load().inspect_artifacts(wheel, sdist, root)


def test_archive_inspection_rejects_payload_not_matching_selected_source(tmp_path):
    root, wheel, sdist = artifacts(tmp_path)
    (root / 'bitteam_sdk/__init__.py').write_text('__version__ = "1.7.0"\n# changed source\n', encoding='utf-8')
    with pytest.raises(ValueError, match='differs from selected source'):
        load().inspect_artifacts(wheel, sdist, root)
