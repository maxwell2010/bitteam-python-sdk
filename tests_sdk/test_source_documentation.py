"""Static source metadata/link checks; no distribution or SDK import needed."""
from pathlib import Path

from scripts_sdk.check_source_docs import check_sources


def test_tracked_project_documentation_paths_resolve_without_casefold_collisions():
    assert check_sources(Path(__file__).resolve().parents[1]) == []


def test_missing_readme_and_wrong_case_links_are_detected(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nreadme="missing.md"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text('[missing](readme.md)\n', encoding="utf-8")
    errors = check_sources(tmp_path, ["pyproject.toml", "README.md"])
    assert any("project.readme" in error for error in errors)
    assert any("Broken relative link" in error for error in errors)


def test_casefold_collisions_are_detected_even_on_case_sensitive_hosts(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nreadme="README.md"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text("# Synthetic\n", encoding="utf-8")
    errors = check_sources(tmp_path, ["pyproject.toml", "README.md", "readme.md"])
    assert any("Casefold collision" in error for error in errors)


def test_parser_ignores_code_examples_and_resolves_encoded_paths_and_directories(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nreadme="README.md"\n', encoding="utf-8")
    (tmp_path / "README.md").write_text(
        '```md\n[example](missing.md)\n```\n`[inline](missing.md)`\n'
        '[a](docs/My%20Doc.md#section) [dir](docs/) [root](.) [web](https://example.test/no-file)\n', encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "My Doc.md").write_text("# Section\n", encoding="utf-8")
    assert check_sources(tmp_path, ["pyproject.toml", "README.md", "docs/My Doc.md"]) == []


def standalone_source_fixture(tmp_path):
    public = {
        "README.md": "# Synthetic\n[guide](docs/Guide.md)\n",
        "AGENTS.md": "# Synthetic instructions\n",
        "MANIFEST.in": "include README.md\n",
        "pyproject.toml": '[project]\nreadme="README.md"\n',
        "requirements-sdk.txt": "# Synthetic\n",
        "requirements-sdk-dev.txt": "# Synthetic\n",
        ".github/workflows/sdk.yml": "# Synthetic\n",
        "bitteam_sdk/__init__.py": "# Synthetic\n",
        "docs/Guide.md": "# Guide\n",
    }
    for name, content in public.items():
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return tmp_path


def test_standalone_source_tree_checks_public_links_without_git_or_artifacts(tmp_path, monkeypatch):
    import subprocess
    standalone_source_fixture(tmp_path)
    # An extracted source tree has no .git, even when its parent is a checkout.
    def forbidden(*args, **kwargs):
        raise AssertionError("Standalone documentation check must not require git")
    monkeypatch.setattr(subprocess, "check_output", forbidden)
    before = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    assert check_sources(tmp_path) == []
    after = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*") if path.is_file()}
    assert before == after and not (tmp_path / "output-sdk").exists()


def test_standalone_source_documentation_cli_works_with_isolated_python(tmp_path):
    import shutil
    import subprocess
    import sys
    standalone_source_fixture(tmp_path)
    source_scripts = Path(__file__).resolve().parents[1] / "scripts_sdk"
    target_scripts = tmp_path / "scripts_sdk"
    target_scripts.mkdir()
    for name in ("check_source_docs.py", "package_source.py"):
        shutil.copyfile(source_scripts / name, target_scripts / name)
    result = subprocess.run(
        [sys.executable, "-I", "-B", str(target_scripts / "check_source_docs.py"),
         "--repo-root", str(tmp_path)],
        cwd=tmp_path, text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "no SDK build" in result.stdout
    assert not (tmp_path / "output-sdk").exists()
