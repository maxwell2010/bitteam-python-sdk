"""Plan a future standalone source archive; never create distribution artifacts.

The default inventory is Git-tracked files, intersected with a public allowlist.
A standalone tree uses its public file inventory without consulting enclosing Git.
Import and CLI execution only plan paths; neither imports the SDK nor writes files.
"""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess

ROOT_FILES = frozenset({
    "README.md", "CHANGELOG.md", "AGENTS.md", "MANIFEST.in", "pyproject.toml", ".gitignore",
    "requirements-sdk.txt", "requirements-sdk-dev.txt", ".github/workflows/sdk.yml",
})
REQUIRED_FILES = ROOT_FILES - {".gitignore"}
BLOCKED_PARTS = frozenset({
    ".git", "__pycache__", ".pytest_cache", ".cache", "cache", "sessions",
    "profiles", "build", "dist", "output-sdk", "work", ".venv", "venv",
})
REPORTS = frozenset({"bitteam_sdk/LIVE_CHECKS.json", "bitteam_sdk/EXTENDED_CHECKS.json"})


def public_source_path(name):
    """Whether a normalized relative path belongs to the public source allowlist."""
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != name or "\\" in name:
        return False
    if any(part.casefold() in BLOCKED_PARTS or part.casefold().endswith(".egg-info") for part in path.parts):
        return False
    filename = path.name.casefold()
    if filename.startswith((".env", "secret", "credential", "cookie", "token")):
        return False
    if name in ROOT_FILES:
        return True
    if len(path.parts) < 2:
        return False
    folder, suffix = path.parts[0], path.suffix
    if folder == "bitteam_sdk":
        return suffix in {".py", ".md"} or name in REPORTS or (
            path.parts[1] == "schemas" and suffix == ".json") or name in {
                "bitteam_sdk/requirements.txt", "bitteam_sdk/structure.txt"}
    return (folder == "docs" and suffix == ".md" or
            folder == "tests_sdk" and suffix in {".py", ".ini"} or
            folder == "scripts_sdk" and suffix == ".py")


def source_tree_inventory(root):
    """Enumerate a standalone source tree without VCS or reading file contents."""
    root = Path(root)
    return tuple(path.relative_to(root).as_posix() for path in root.rglob("*")
                 if path.is_file() and public_source_path(path.relative_to(root).as_posix()))


def plan_source_files(root, paths=None):
    """Return sorted relative files without creating directories or artifacts.

    Uses tracked files in a checkout; otherwise the standalone public inventory.
    Missing required inputs, case collisions and selected symlinks fail closed.
    """
    root = Path(root).resolve()
    if paths is None:
        if (root / ".git").exists():
            output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
            paths = output.decode("utf-8").split("\0")
        else:
            paths = source_tree_inventory(root)
    selected = sorted({name for name in paths if name and public_source_path(name)})
    missing = REQUIRED_FILES - set(selected)
    if missing:
        raise ValueError("Missing required source inputs: " + ", ".join(sorted(missing)))
    folded = set()
    for name in selected:
        if name.casefold() in folded:
            raise ValueError("Casefold source path collision: " + name)
        folded.add(name.casefold())
        file = root / name
        if any(parent.is_symlink() for parent in (file, *file.parents) if parent != root):
            raise ValueError("Source input cannot be a symlink: " + name)
        if not file.is_file() or not file.resolve().is_relative_to(root):
            raise ValueError("Missing or unsafe source input: " + name)
    return tuple(selected)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    print(json.dumps({"files": plan_source_files(args.source_root), "artifacts_created": False}, indent=2))


if __name__ == "__main__":
    main()
