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
