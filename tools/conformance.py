"""Check repository policy without executing any repository code or configuration."""

# BaseLoader constructs strings/lists/dicts only (never Python objects), preserving
# GitHub's `on` key instead of interpreting it as YAML 1.1 boolean True.
# ruff: noqa: S506

import argparse
import re
import subprocess
import sys
import tomllib
from collections.abc import Collection
from pathlib import Path
from typing import cast

import yaml

REQUIRED = (
    "README.md",
    "LICENSE",
    ".gitattributes",
    "AGENTS.md",
    "CLAUDE.md",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    "opencode.json",
)
PIN = re.compile(r"[\w.-]+/[\w./-]+@[a-f0-9]{40}")
COOLDOWN_DAYS = 14
SHA = re.compile(r"[a-f0-9]{40}")


def tracked_files(root: Path) -> set[str]:
    """Obtain tracked names without following untracked or ignored paths."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return set(result.stdout.decode("utf-8").rstrip("\0").split("\0"))


def safe_read(root: Path, name: str) -> str:
    """Reject links and paths outside the checked-out repository."""
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        msg = f"{name}: policy files must be regular files inside the repository"
        raise ValueError(msg)
    return path.read_text(encoding="utf-8")


def mapping(value: object) -> dict[str, object]:
    """Narrow parsed YAML dictionaries without trusting their shape."""
    if not isinstance(value, dict):
        msg = "expected a YAML mapping"
        raise TypeError(msg)
    return cast("dict[str, object]", value)


def workflow_findings(name: str, text: str) -> list[str]:
    """Apply reference policy to action and reusable-workflow uses alike."""
    findings: list[str] = []
    document = mapping(yaml.load(text, Loader=yaml.BaseLoader))
    jobs = mapping(document.get("jobs", {}))
    entries: list[dict[str, object]] = []
    for value in jobs.values():
        job = mapping(value)
        entries.append(job)
        steps = job.get("steps", [])
        if not isinstance(steps, list):
            msg = "steps must be a YAML sequence"
            raise TypeError(msg)
        entries.extend(mapping(step) for step in cast("list[object]", steps))
    for entry in entries:
        if entry.get("secrets") == "inherit":
            findings.append(f"{name}: inherited secrets are forbidden")
        ref = str(entry.get("uses", ""))
        if not ref:
            continue
        if ref.startswith("./"):
            continue
        if not PIN.fullmatch(ref):
            findings.append(f"{name}: remote uses must pin a full commit SHA: {ref}")
    events = document.get("on", {})
    if (
        "pull_request_target" in events
        if isinstance(events, (dict, list, str))
        else False
    ):
        findings.append(f"{name}: pull_request_target is forbidden")
    if document.get("permissions") != {}:
        findings.append(f"{name}: top-level permissions must be empty")
    return findings


def configuration_findings(root: Path, tracked: Collection[str]) -> list[str]:
    """Check glossary and dependency policies with parsed configuration."""
    findings: list[str] = []
    if "AGENTS.md" in tracked and not re.search(
        r"^## Glossary\s*$", safe_read(root, "AGENTS.md"), re.MULTILINE
    ):
        findings.append("AGENTS.md: missing ## Glossary")
    if ".github/dependabot.yml" in tracked:
        document = mapping(
            yaml.load(safe_read(root, ".github/dependabot.yml"), Loader=yaml.BaseLoader)
        )
        updates = sequence(document.get("updates", []))
        if not updates or any(
            not valid_cooldown(mapping(update)) for update in updates
        ):
            findings.append(
                ".github/dependabot.yml: each ecosystem needs >=14-day cooldown"
            )
    if ".pre-commit-config.yaml" in tracked:
        document = mapping(
            yaml.load(
                safe_read(root, ".pre-commit-config.yaml"), Loader=yaml.BaseLoader
            )
        )
        for value in sequence(document.get("repos", [])):
            repo = mapping(value)
            if repo.get("repo") in {"local", "meta"}:
                continue
            if not SHA.fullmatch(str(repo.get("rev", ""))):
                findings.append(".pre-commit-config.yaml: hook rev must pin full SHA")
    return findings


def sequence(value: object) -> list[object]:
    """Validate list-shaped policy input."""
    if not isinstance(value, list):
        msg = "expected a YAML sequence"
        raise TypeError(msg)
    return cast("list[object]", value)


def valid_cooldown(update: dict[str, object]) -> bool:
    """Require every ecosystem to specify the minimum waiting period."""
    cooldown = mapping(update.get("cooldown", {}))
    days = str(cooldown.get("default-days", ""))
    return days.isdigit() and int(days) >= COOLDOWN_DAYS


def inspect(root: Path, tracked: Collection[str]) -> list[str]:
    """Return actionable policy violations; never modify the checkout."""
    findings = [
        f"{name}: required tracked file missing"
        for name in REQUIRED
        if name not in tracked
    ]
    for name in sorted(tracked):
        is_workflow = name.startswith(".github/workflows/") and name.endswith(
            (".yml", ".yaml")
        )
        if is_workflow:
            try:
                findings.extend(workflow_findings(name, safe_read(root, name)))
            except (ValueError, TypeError, yaml.YAMLError):
                findings.append(f"{name}: invalid YAML or unsafe policy file")
    findings.extend(configuration_findings(root, tracked))
    if "pyproject.toml" in tracked:
        project = tomllib.loads(safe_read(root, "pyproject.toml"))
        if "uv.lock" not in tracked:
            findings.append("uv.lock: Python projects require tracked lockfile")
        if "tool" not in project:
            findings.append("pyproject.toml: Python tooling configuration missing")
    return findings


def main() -> int:
    """Report policy failures as CI annotations and return a failing status."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    root = parser.parse_args().repository.resolve()
    try:
        findings = inspect(root, tracked_files(root))
    except (ValueError, TypeError, OSError, yaml.YAMLError):
        findings = ["Invalid, unreadable or unsafe repository policy configuration"]
    for finding in findings:
        sys.stdout.write(f"{finding}\n")
    sys.stdout.write(f"Conformance: {len(findings)} violation(s)\n")
    return int(bool(findings))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
