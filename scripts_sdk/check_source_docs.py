"""Check tracked documentation paths without building or importing the SDK."""
import argparse
from collections import defaultdict
from pathlib import Path
import posixpath
import subprocess
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt

try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib


def tracked_paths(root):
    output = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
    return output.decode("utf-8").rstrip("\0").split("\0") if output else []


def standalone_paths(root):
    """Read a public source inventory without consulting any enclosing Git repo."""
    # -I direct script execution omits both the source root and script directory
    # from sys.path. Load only the explicit, side-effect-free sibling planner.
    if __package__ in (None, ""):
        from importlib.util import module_from_spec, spec_from_file_location
        spec = spec_from_file_location("sdk_source_planner", Path(__file__).with_name("package_source.py"))
        planner = module_from_spec(spec)
        spec.loader.exec_module(planner)
        plan_source_files = planner.plan_source_files
    else:
        from scripts_sdk.package_source import plan_source_files
    root = Path(root)
    inventory = (path.relative_to(root).as_posix() for path in root.rglob("*")
                 if path.is_file())
    return list(plan_source_files(root, paths=inventory))


def source_paths(root):
    root = Path(root)
    return tracked_paths(root) if (root / ".git").exists() else standalone_paths(root)


def check_sources(root, paths=None):
    root = Path(root)
    paths = source_paths(root) if paths is None else list(paths)
    files, errors = set(paths), []
    folded = defaultdict(list)
    for path in paths:
        folded[path.casefold()].append(path)
    for collisions in folded.values():
        if len(collisions) > 1:
            errors.append("Casefold collision: " + ", ".join(sorted(collisions)))

    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    readme = config["project"].get("readme")
    readme = readme.get("file") if isinstance(readme, dict) else readme
    if not isinstance(readme, str) or readme not in files or not (root / readme).is_file():
        errors.append("project.readme does not name a tracked file: " + str(readme))

    parser = MarkdownIt()
    for document in sorted(path for path in files if path.lower().endswith(".md")):
        file = root / document
        if not file.is_file():
            errors.append("Missing tracked Markdown file: " + document)
            continue
        for token in parser.parse(file.read_text(encoding="utf-8")):
            for child in token.children or ():
                destination = child.attrGet("href") if child.type == "link_open" else child.attrGet("src") if child.type == "image" else None
                if not destination:
                    continue
                url = urlsplit(destination)
                if url.scheme or url.netloc or not url.path:
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(document), unquote(url.path)))
                # Require exact tracked case even on Windows; directory links
                # are valid if they contain tracked files. Anchors are not checked.
                exists = target == "." and bool(files) or target in files or any(
                    path.startswith(target.rstrip("/") + "/") for path in files)
                if target.startswith("../") or target.startswith("/") or not exists:
                    errors.append(f"Broken relative link: {document} -> {destination}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = check_sources(args.repo_root)
    if errors:
        raise SystemExit("\n".join(errors))
    print("Source readme, relative Markdown paths and casefold checks passed; no SDK build")


if __name__ == "__main__":
    main()
