"""Freeze the newest eligible hook releases without bypassing the cooldown."""

import argparse
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from tools.baseline import validate_path
from tools.conformance import mapping, sequence
from tools.github_api import github_api

COOLDOWN = timedelta(days=14)
VERSION = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")
REPOSITORY = re.compile(r"https://github\.com/([\w-]+/[\w.-]+)")
REVISION = re.compile(r"^([ \t]+rev:[ \t]+)([a-f0-9]{40})(?:[ \t]+#.*)?$", re.M)
TAG_COMMENT = re.compile(r"#\s*(?:frozen:\s*)?(v?\d+\.\d+\.\d+)\s*$")


def semantic_version(tag: str) -> tuple[int, int, int]:
    """Accept stable semantic tags only; no branch names or prereleases."""
    match = VERSION.fullmatch(tag)
    if match is None:
        msg = "hook releases must use stable semantic tags"
        raise ValueError(msg)
    return int(match[1]), int(match[2]), int(match[3])


def eligible_release(repository: str, now: datetime) -> tuple[str, str]:
    """Select by semantic version and verified publication age, then resolve SHA."""
    metadata = mapping(github_api(f"repos/{repository}"))
    if metadata.get("archived") is not False or metadata.get("disabled") is not False:
        msg = "hook upstream is archived, disabled or unavailable"
        raise ValueError(msg)
    releases = sequence(github_api(f"repos/{repository}/releases?per_page=100"))
    eligible: list[str] = []
    for value in releases:
        release = mapping(value)
        if release.get("draft") is not False or release.get("prerelease") is not False:
            continue
        tag = str(release.get("tag_name", ""))
        if VERSION.fullmatch(tag) is None:
            continue
        published = datetime.fromisoformat(str(release.get("published_at", "")))
        if published.tzinfo is None:
            msg = "release publication timestamp must have a timezone"
            raise ValueError(msg)
        if published <= now - COOLDOWN:
            eligible.append(tag)
    if not eligible:
        msg = "no verifiable stable hook release satisfies the 14-day cooldown"
        raise ValueError(msg)
    tag = max(eligible, key=semantic_version)
    commit = mapping(github_api(f"repos/{repository}/commits/{tag}"))
    sha = str(commit.get("sha", ""))
    if re.fullmatch(r"[a-f0-9]{40}", sha) is None:
        msg = "resolved hook revision is not a full commit SHA"
        raise ValueError(msg)
    return tag, sha


def propose(source: str, now: datetime) -> tuple[str, list[str]]:
    """Change revision lines only, preserving every other byte of the config."""
    document = mapping(yaml.safe_load(source))
    repos = sequence(document.get("repos", []))
    revisions = list(REVISION.finditer(source))
    if len(revisions) != len(repos):
        msg = "baseline hook layout must have one frozen revision per repository"
        raise ValueError(msg)
    updates: list[tuple[int, int, str]] = []
    evidence: list[str] = []
    for value, revision in zip(repos, revisions, strict=True):
        repo = mapping(value)
        match = REPOSITORY.fullmatch(str(repo.get("repo", "")))
        old_tag = TAG_COMMENT.search(revision[0])
        if match is None or old_tag is None or repo.get("rev") != revision[2]:
            msg = "baseline hooks require GitHub URLs, frozen SHAs and version comments"
            raise ValueError(msg)
        tag, sha = eligible_release(match[1], now)
        if semantic_version(tag) < semantic_version(old_tag[1]):
            msg = "hook update would downgrade the reviewed release"
            raise ValueError(msg)
        if sha == revision[2]:
            continue
        updates.append(
            (revision.start(), revision.end(), f"{revision[1]}{sha} # {tag}")
        )
        evidence.append(f"{match[1]}: {old_tag[1]} -> {tag} ({sha})")
    for start, end, replacement in reversed(updates):
        source = source[:start] + replacement + source[end:]
    return source, evidence


def main() -> None:
    """Prepare reviewed baseline updates; dry-run unless explicitly applying."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = validate_path(args.repository.resolve(), "baseline/.pre-commit-config.yaml")
    changed, evidence = propose(path.read_text(encoding="utf-8"), datetime.now(UTC))
    if args.apply and evidence:
        path.write_text(changed, encoding="utf-8", newline="\n")
    sys.stdout.write("\n".join(evidence) + "\n")


if __name__ == "__main__":  # pragma: no cover
    main()
