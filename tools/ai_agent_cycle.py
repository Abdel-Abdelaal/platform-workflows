"""Discover public fleet audits and promote at most one verified proposal per cycle."""

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from tools.ai_agent_promote import OWNER, promote
from tools.ai_agent_schema import AgentEvidenceError
from tools.ai_telemetry import mapping
from tools.ai_telemetry_archive import gh
from tools.github_api import github_api

PAGE_SIZE = 100


def repositories() -> list[str]:
    """Refresh public, owned, non-fork targets each invocation, including new repos."""
    result: list[str] = []
    for page in range(1, 11):
        rows = github_api(f"users/{OWNER}/repos?per_page=100&page={page}")
        if not isinstance(rows, list):
            raise AgentEvidenceError
        rows = cast(list[Any], rows)
        for row in rows:
            item = mapping(row)
            name = str(item.get("full_name", ""))
            if (
                re.fullmatch(rf"{OWNER}/[A-Za-z0-9_.-]+", name)
                and item.get("private") is False
                and item.get("fork") is False
                and item.get("archived") is False
                and name != f"{OWNER}/agent-dispatcher"
            ):
                result.append(name)
        if len(rows) < PAGE_SIZE:
            return sorted(set(result))
    raise AgentEvidenceError


def release_assets(repository: str, release_id: int) -> list[str]:
    """Read every asset page within the explicit archive-size budget."""
    assets: list[str] = []
    for page in range(1, 11):
        rows = github_api(
            f"repos/{repository}/releases/{release_id}/assets?per_page=100&page={page}"
        )
        if not isinstance(rows, list):
            raise AgentEvidenceError
        rows = cast(list[Any], rows)
        assets.extend(str(mapping(row).get("name", "")) for row in rows)
        if len(rows) < PAGE_SIZE:
            return assets
    raise AgentEvidenceError


def candidates(targets: list[str]) -> Iterator[tuple[str, str, str, str]]:
    """Discover bounded record/signature pairs without trusting their contents."""
    for repository in targets:
        releases = github_api(f"repos/{repository}/releases?per_page=30")
        if not isinstance(releases, list):
            raise AgentEvidenceError
        releases = cast(list[dict[str, Any]], releases)
        for release in releases:
            tag = str(release.get("tag_name", ""))
            if not re.fullmatch(r"ai-telemetry-\d{4}-\d{2}", tag):
                continue
            assets = release_assets(repository, int(release["id"]))
            records = sorted(
                (
                    name
                    for name in assets
                    if re.fullmatch(r"ai-\d+-\d+-audit.json", name)
                ),
                key=lambda name: int(name.split("-")[1]),
                reverse=True,
            )
            for name in records[:2]:
                signature = name.removesuffix(".json") + ".sigstore.json"
                if signature in assets:
                    yield repository, tag, name, signature
            # Only the newest monthly archive with audit records is relevant.
            if records:
                break


def cycle(*, apply: bool) -> dict[str, Any]:
    """Keep intake serial and bounded; signatures, not asset names, authorize work."""
    targets = repositories()
    for repository in targets:
        for label in ("agent:ready", "agent:running", "agent:parked"):
            if github_api(
                f"repos/{repository}/issues?state=open&labels={label}&per_page=1"
            ):
                return {"status": "queue_busy"}
    for repository, tag, name, signature in candidates(targets):
        with tempfile.TemporaryDirectory(prefix="verified-audit-") as tmp:
            result = gh(
                [
                    "release",
                    "download",
                    tag,
                    "--repo",
                    repository,
                    "--pattern",
                    name,
                    "--pattern",
                    signature,
                    "--dir",
                    tmp,
                ]
            )
            if result.returncode:
                raise AgentEvidenceError
            selected = promote(
                repository, Path(tmp) / name, Path(tmp) / signature, apply=apply
            )
            if selected["status"] in {"promoted", "eligible"}:
                return selected
    return {"status": "no_eligible_proposal"}


def main() -> None:
    """Read-only unless the trusted host explicitly supplies --apply."""
    try:
        if sys.argv[1:] not in ([], ["--apply"]):
            raise AgentEvidenceError
        sys.stdout.write(json.dumps(cycle(apply="--apply" in sys.argv[1:])))
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        message = "Audit discovery failed closed; diagnostics withheld."
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
