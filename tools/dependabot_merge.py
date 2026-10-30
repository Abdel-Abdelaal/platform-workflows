"""Merge authenticated compatible updates from trusted default-branch automation."""

import argparse
import json
import re
from pathlib import Path
from typing import Any, cast

import yaml

from tools.ai_telemetry import mapping
from tools.fleet_onboarding import OWNER, objects, repositories
from tools.github_api import github_api

BOT_ID = 49699333
COMPATIBLE = {"version-update:semver-patch", "version-update:semver-minor"}
MANUAL = {"opencode-ai", "promptfoo"}
MAX_METADATA_BYTES = 100_000


def eligible(repository: dict[str, Any]) -> bool:
    """Keep private, disabled, archived and foreign repositories outside the token."""
    return (
        repository.get("private") is False
        and repository.get("archived") is False
        and repository.get("disabled") is False
        and repository.get("fork") is False
        and re.fullmatch(rf"{OWNER}/[A-Za-z0-9_.-]+", repository.get("full_name", ""))
        is not None
    )


def authenticated_updates(pr: dict[str, Any], commits: list[dict[str, Any]]) -> str:
    """Use verified commit metadata, never an editable PR title/body or label.

    The identity/signature and YAML metadata convention follows MIT-licensed
    dependabot/fetch-metadata. We deliberately accept only one untouched bot commit;
    unknown metadata and any manually modified branch require maintainer review.
    """
    if (
        pr.get("commits") != 1
        or len(commits) != 1
        or commits[0].get("sha") != mapping(pr.get("head")).get("sha")
    ):
        return "modified_branch"
    commit = commits[0]
    if (
        mapping(commit.get("author")).get("id") != BOT_ID
        or mapping(mapping(commit.get("commit")).get("verification")).get("verified")
        is not True
    ):
        return "unverified_commit"
    return classify_updates(mapping(commit.get("commit")).get("message"))


def classify_updates(message: object) -> str:
    """Reject incomplete or incompatible signed metadata without guessing versions."""
    updates = metadata_updates(message)
    if not updates:
        return "unknown_metadata"
    for update in updates:
        name, kind = update.get("dependency-name"), update.get("update-type")
        version = str(update.get("dependency-version", ""))
        if not isinstance(name, str) or not name or not isinstance(kind, str):
            return "unknown_metadata"
        if kind not in COMPATIBLE:
            return "manual_update"
        if name in MANUAL or name.startswith("@opencode-ai/"):
            return "harness_update"
        if kind == "version-update:semver-minor" and version.startswith("0."):
            return "prestable_update"
    return "compatible"


def metadata_updates(message: object) -> list[dict[str, Any]]:
    """Parse only the bounded YAML envelope used by authenticated Dependabot commits."""
    if not isinstance(message, str) or len(message) > MAX_METADATA_BYTES:
        return []
    match = re.search(r"^---\n(.*?)\n\.\.\.(?:\n|$)", message, re.M | re.S)
    if match is None:
        return []
    try:
        updates = mapping(yaml.safe_load(match[1])).get("updated-dependencies")
    except (yaml.YAMLError, TypeError, ValueError):
        return []
    return objects(cast("list[object]", updates)) if isinstance(updates, list) else []


def inspect(repository: str, number: int) -> dict[str, Any]:
    """Re-read identity, protection, current head and verified metadata each cycle."""
    root = f"repos/{repository}"
    repo = mapping(github_api(root))
    pr = mapping(github_api(f"{root}/pulls/{number}"))
    result: dict[str, Any] = {"repository": repository, "number": number}
    head, base = mapping(pr.get("head")), mapping(pr.get("base"))
    if not eligible(repo):
        return {**result, "reason": "ineligible_repository"}
    if (
        pr.get("state") != "open"
        or pr.get("draft") is not False
        or mapping(pr.get("user")).get("id") != BOT_ID
        or mapping(head.get("repo")).get("full_name") != repository
        or base.get("ref") != repo.get("default_branch")
        or not str(head.get("ref", "")).startswith("dependabot/")
    ):
        return {**result, "reason": "ineligible_pull_request"}
    branch = mapping(github_api(f"{root}/branches/{base['ref']}"))
    rules = objects(github_api(f"{root}/rules/branches/{base['ref']}"))
    protected = any(
        rule.get("type") == "required_status_checks"
        and mapping(rule.get("parameters")).get("required_status_checks")
        and mapping(rule.get("parameters")).get("strict_required_status_checks_policy")
        is True
        for rule in rules
    )
    if branch.get("protected") is not True or not protected:
        return {**result, "reason": "missing_required_checks"}
    commits = objects(github_api(f"{root}/pulls/{number}/commits?per_page=100"))
    reason = authenticated_updates(pr, commits)
    if reason != "compatible":
        return {**result, "reason": reason}
    sha = head.get("sha")
    if (
        pr.get("mergeable") is not True
        or pr.get("mergeable_state") != "clean"
        or not isinstance(sha, str)
        or re.fullmatch(r"[a-f0-9]{40}", sha) is None
    ):
        return {**result, "reason": "checks_reviews_or_base_pending"}
    return {**result, "reason": "eligible", "head": sha}


def run(*, apply: bool, report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Bound each cycle to one protected squash per public repository.

    GitHub enforces checks, review, resolved threads and current base at mutation.
    The expected SHA prevents merging a replacement head. No checkout, model call,
    package installation, auto-approval, branch update or protection bypass occurs.
    """
    if report is None:
        report = {}
    results: list[dict[str, Any]] = []
    report.update(apply=apply, repositories=[], pull_requests=results)
    targets = [repo for repo in repositories(installation=apply) if eligible(repo)]
    report["repositories"] = [repo["full_name"] for repo in targets]
    for repo in targets:
        name = repo["full_name"]
        prs = objects(github_api(f"repos/{name}/pulls?state=open&per_page=100"))
        merged = False
        for pr in prs:
            if mapping(pr.get("user")).get("id") != BOT_ID:
                continue
            item = inspect(name, pr["number"])
            results.append(item)
            if apply and not merged and item["reason"] == "eligible":
                item["reason"] = "merge_requested"
                outcome = mapping(
                    github_api(
                        f"repos/{name}/pulls/{pr['number']}/merge",
                        "PUT",
                        {"sha": item["head"], "merge_method": "squash"},
                    )
                )
                merged = outcome.get("merged") is True
                item["reason"] = "merged" if merged else "merge_refused"
                item["merge_commit"] = outcome.get("sha") if merged else None
            elif apply and merged and item["reason"] == "eligible":
                item["reason"] = "next_cycle"
    return report


def main() -> None:
    """Write a public, payload-free maintenance receipt; default to read-only."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report: dict[str, Any] = {"apply": args.apply, "state": "started"}
    args.output.write_text(json.dumps(report) + "\n")
    try:
        run(apply=args.apply, report=report)
        report["state"] = "complete"
    finally:
        args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
