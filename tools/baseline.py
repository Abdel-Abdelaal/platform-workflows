"""Prepare allowlisted baseline changes for a normally reviewed pull request."""

import argparse
import sys
from pathlib import Path

FILES = frozenset(
    {
        ".gitattributes",
        ".editorconfig",
        "ruff-base.toml",
        "pyrightconfig.base.json",
        ".pre-commit-config.yaml",
        "opencode.json",
        ".github/workflows/scorecard.yml",
        "labels.yml",
    }
)
MAX_FILE_BYTES = 100_000


def exceptions(repository: Path) -> set[str]:
    """Allow only explicit managed paths; reject wildcards and traversal."""
    path = repository / ".baseline-ignore"
    validate_path(repository, ".baseline-ignore")
    if not path.exists():
        return set()
    names = {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if names - FILES:
        msg = "baseline exceptions must be exact managed file paths"
        raise ValueError(msg)
    return names


def validate_path(root: Path, name: str) -> Path:
    """Reject symlinks at every component and all resolved path escapes."""
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        msg = "baseline path escapes repository"
        raise ValueError(msg)
    for component in [path, *path.parents]:
        if component == root:
            break
        if component.is_symlink():
            msg = "baseline paths cannot contain symlinks"
            raise ValueError(msg)
    return path


def synchronize(source: Path, repository: Path, *, apply: bool = False) -> list[str]:
    """Validate all inputs before writing exact managed files; never delete files."""
    source, repository = source.resolve(), repository.resolve()
    ignored = exceptions(repository)
    changes: dict[str, bytes] = {}
    for name in sorted(FILES - ignored):
        origin = validate_path(source, name)
        target = validate_path(repository, name)
        data = origin.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            msg = "baseline file exceeds size limit"
            raise ValueError(msg)
        if not target.exists() or target.read_bytes() != data:
            changes[name] = data
    if apply:
        for name, data in changes.items():
            target = repository / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    return list(changes)


def main() -> None:
    """Print proposed changes, applying only when explicitly requested."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    for name in synchronize(args.source, args.repository, apply=args.apply):
        sys.stdout.write(name + "\n")


if __name__ == "__main__":  # pragma: no cover
    main()
