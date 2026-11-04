"""Source inventory/manifest regressions without creating any distribution."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch

import pytest
from setuptools._distutils.filelist import FileList

from scripts_sdk.package_source import ROOT_FILES, plan_source_files, public_source_path
from scripts_sdk.check_source_docs import check_sources

ROOT = Path(__file__).resolve().parents[1]


def manifest_files(paths):
    files = FileList()
    files.set_allfiles([str(Path(path)) for path in paths])
    for line in (ROOT / "MANIFEST.in").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            files.process_template_line(line)
    return {name.replace(os.sep, "/") for name in files.files}


def test_import_is_inert_without_sdk_import_mkdir_or_archive_access():
    # Only the refactored module is loaded. The old script is never executed.
    spec = importlib.util.spec_from_file_location("synthetic_package_source", ROOT / "scripts_sdk/package_source.py")
    module = importlib.util.module_from_spec(spec)
    with patch("pathlib.Path.mkdir", side_effect=AssertionError("No output directory")), \
         patch("zipfile.ZipFile", side_effect=AssertionError("No archive")), \
         patch("subprocess.check_output", side_effect=AssertionError("No inventory on import")):
        spec.loader.exec_module(module)
    assert callable(module.plan_source_files)
    # There is no import of SDK even in a fresh isolated interpreter.
    result = subprocess.run([sys.executable, "-I", "-c",
        "import importlib.util,sys; from pathlib import Path; "
        "s=importlib.util.spec_from_file_location('planner',sys.argv[1]); "
        "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
        "assert 'bitteam_sdk' not in sys.modules", str(ROOT / "scripts_sdk/package_source.py")],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_manifest_and_future_plan_cover_canonical_docs_and_all_test_inputs(tmp_path):
    plan = plan_source_files(ROOT)
    assert ROOT_FILES <= set(plan)
    assert {"docs/CLOUD_HANDOFF.md", "docs/TEST_GAPS.md", "docs/P2P_READ_WORKFLOWS.md",
            "bitteam_sdk/LEGACY_README.md", "tests_sdk/pytest.ini",
            "scripts_sdk/check_source_docs.py", "bitteam_sdk/schemas/openapi.json"} <= set(plan)
    assert "bitteam_sdk/README.md" not in plan
    assert set(plan) == manifest_files(plan)
    assert check_sources(ROOT, paths=plan) == []
    assert plan == tuple(sorted(set(plan)))
    # A plain copy of the planned files models the future standalone tree.
    # No ZIP/tar/wheel, SDK install, build command or Git metadata is involved.
    for name in plan:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    assert not (tmp_path / ".git").exists()
    assert check_sources(tmp_path) == []
    assert plan_source_files(tmp_path) == plan


@pytest.mark.parametrize("name", [
    "../README.md", "/README.md", "bitteam_sdk/../secret.py",
    "bitteam_sdk/secrets.py", "bitteam_sdk/cookies.json", "bitteam_sdk/session.json",
    "bitteam_sdk/sessions/private.py", "bitteam_sdk/.cache/private.py",
    "tests_sdk/__pycache__/private.py", "docs/.env", "docs/credentials.md",
    "work/test.py", "output-sdk/source.zip", "dist/package.whl", "build/leak.py",
    "bitteam_sdk/private.db", "bitteam_sdk/private.sqlite3", "bitteam_sdk/log.log",
])
def test_sensitive_cache_and_build_paths_are_not_source_inputs(name):
    assert not public_source_path(name)


def test_explicit_inventory_is_filtered_without_reading_rejected_files():
    paths = list(plan_source_files(ROOT))
    rejected = ["bitteam_sdk/secrets.py", "bitteam_sdk/sessions/private.py", "work/leak.py",
                "bitteam_sdk/cookies.json", "build/leak.py"]
    assert plan_source_files(ROOT, paths=paths + rejected) == tuple(paths)


def test_missing_required_input_and_symlinks_fail_closed(tmp_path):
    paths = plan_source_files(ROOT)
    with pytest.raises(ValueError, match="Missing required"):
        plan_source_files(ROOT, paths=[name for name in paths if name != "README.md"])
    for name in ROOT_FILES:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("synthetic", encoding="utf-8")
    # Patch is_symlink rather than creating OS symlinks requiring Windows privileges.
    original = Path.is_symlink
    with patch.object(Path, "is_symlink", lambda path: path == tmp_path / "README.md" or original(path)):
        with pytest.raises(ValueError, match="symlink"):
            plan_source_files(tmp_path, paths=ROOT_FILES)


def test_manifest_excludes_sensitive_and_runtime_files_even_under_public_trees():
    rejected = {
        "bitteam_sdk/secrets.py", "docs/credentials.md", "bitteam_sdk/schemas/tokens.json",
        "bitteam_sdk/sessions/private.py", "bitteam_sdk/.cache/private.py",
        "tests_sdk/__pycache__/private.py", "scripts_sdk/build/leak.py",
        "bitteam_sdk/log.log", "bitteam_sdk/private.db", "bitteam_sdk/private.sqlite3",
        "docs/.env", "output-sdk/source.zip", "work/leak.py", "build/leak.py",
        "bitteam_sdk/Secrets.py", "docs/Credentials.md", "bitteam_sdk/schemas/Tokens.json",
        "bitteam_sdk/Sessions/private.py", "scripts_sdk/Build/leak.py",
        "tests_sdk/.VENV/leak.py", "docs/.ENV.md", "bitteam_sdk/.git/leak.py",
    }
    selected = manifest_files(list(plan_source_files(ROOT)) + sorted(rejected))
    assert not selected.intersection(rejected)


def test_planner_cli_prints_only_a_plan_without_creating_outputs():
    result = subprocess.run([sys.executable, "-I", "-B",
        str(ROOT / "scripts_sdk/package_source.py"), "--source-root", str(ROOT)],
        capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["artifacts_created"] is False
    assert report["files"] == list(plan_source_files(ROOT))
