"""Propose reviewed public-repository enrollment through an installation token."""

import argparse
import base64
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

from tools.ai_telemetry import mapping
from tools.github_api import github_api

OWNER = "Abdel-Abdelaal"
BASELINE_COMMIT = "2db3f67b69f1282c9cb377d8a30ae2a9948898c0"
PLATFORM_COMMIT = "40b37ce9647cc6cde2adc3d3d1acfc0aa06f92c9"
PLATFORM_RELEASE = "v1.10.0"
BRANCH = "ci/fleet-onboarding"
PAGE_SIZE = 100
MAX_FILE_BYTES = 100_000
CALLERS = (
    "pr.yml",
    "security.yml",
    "conformance-checks.yml",
    "scorecard.yml",
    "ai-review.yml",
    "ai-maintenance.yml",
    "baseline.yml",
    "stale-items.yml",
    "lint.yml",
)
FILES = (
    "README.md",
    "LICENSE",
    "AGENTS.md",
    "CLAUDE.md",
    ".gitattributes",
    ".editorconfig",
    "opencode.json",
    ".github/CODEOWNERS",
    ".github/dependabot.yml",
    ".github/zizmor.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    *(f".github/workflows/{name}" for name in CALLERS),
)


def objects(value: object) -> list[dict[str, Any]]:
    """Reject malformed API collections instead of guessing their contents."""
    if not isinstance(value, list):
        message = "expected a GitHub API list"
        raise TypeError(message)
    return [mapping(item) for item in cast("list[object]", value)]


def repositories(*, installation: bool) -> list[dict[str, Any]]:
    """Discover only eligible public repositories without emitting private names."""
    result: list[dict[str, Any]] = []
    page = 1
    while True:
        endpoint = (
            "installation/repositories" if installation else f"users/{OWNER}/repos"
        )
        payload = github_api(f"{endpoint}?per_page={PAGE_SIZE}&page={page}")
        batch = (
            objects(mapping(payload).get("repositories"))
            if installation
            else objects(payload)
        )
        for repository in batch:
            if (
                repository.get("private") is False
                and repository.get("fork") is False
                and repository.get("archived") is False
                and re.fullmatch(
                    rf"{OWNER}/[A-Za-z0-9_.-]+", str(repository.get("full_name", ""))
                )
            ):
                result.append(repository)
        if len(batch) < PAGE_SIZE:
            return result
        page += 1


def tree(repository: str, commit: str) -> dict[str, Any]:
    """Read the tracked tree without executing source or following symlinks."""
    value = mapping(github_api(f"repos/{repository}/git/trees/{commit}?recursive=1"))
    if value.get("truncated") is not False:
        message = "repository tree is incomplete"
        raise ValueError(message)
    return value


def templates() -> dict[str, str]:
    """Read only the reviewed starter's fixed allowlist at an immutable commit."""
    result: dict[str, str] = {}
    for name in FILES:
        path = "baseline/new-repo/" + name
        item = mapping(
            github_api(f"repos/{OWNER}/.github/contents/{path}?ref={BASELINE_COMMIT}")
        )
        if item.get("type") != "file" or item.get("encoding") != "base64":
            message = "starter file is not a regular encoded blob"
            raise ValueError(message)
        text = base64.b64decode(item["content"]).decode("utf-8")
        if len(text.encode()) > MAX_FILE_BYTES:
            message = "starter file exceeds size bound"
            raise ValueError(message)
        own_workflow = (
            rf"({OWNER}/platform-workflows/\.github/workflows/[^@\s]+)"
            r"@[a-f0-9]{40}[^\r\n]*"
        )
        result[name] = re.sub(
            own_workflow,
            rf"\g<1>@{PLATFORM_COMMIT} # {PLATFORM_RELEASE}",
            text,
        )
    return result


def proposal(repository: dict[str, Any], starter: dict[str, str]) -> dict[str, Any]:
    """Add missing starter files while preserving all existing application files."""
    name = repository["full_name"]
    metadata = mapping(github_api(f"repos/{name}"))
    if metadata.get("private") is not False:
        message = "public enrollment requires explicitly public storage"
        raise ValueError(message)
    branch = metadata["default_branch"]
    if not isinstance(branch, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9/_.-]*", branch
    ):
        message = "default branch needs manual enrollment review"
        raise ValueError(message)
    reference = mapping(github_api(f"repos/{name}/branches/{quote(branch, safe='')}"))
    commit = mapping(reference["commit"])["sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        message = "default branch did not resolve to an immutable commit"
        raise ValueError(message)
    tracked = tree(name, commit)
    protection = {
        "default_branch_protected": reference.get("protected"),
        "blocking_findings": []
        if reference.get("protected") is True
        else ["Default branch protection is missing or unverified."],
    }
    entries = objects(tracked["tree"])
    existing = {item["path"] for item in entries}
    for item in entries:
        if (
            item["path"] in {".github", ".github/workflows"}
            and item.get("type") != "tree"
        ):
            message = "starter parent directory is not a regular tree"
            raise ValueError(message)
    if ".github/workflows/conformance-checks.yml" in existing:
        return {
            "repository": name,
            "status": "existing enrollment marker",
            "files": {},
            **protection,
        }
    files = {
        path: text.replace("REPO-NAME", metadata["name"])
        for path, text in starter.items()
        if path not in existing
    }
    for path, value in files.items():
        if path.startswith(".github/workflows/"):
            files[path] = value.replace(
                "branches: [main]", "branches: " + json.dumps([branch])
            )
    if "AGENTS.md" in files:
        files["AGENTS.md"] = (
            "# Repository instructions\n\nFollow the shared handbook at "
            f"https://github.com/{OWNER}/.github/tree/main/standards.\n"
            "Use Conventional Commit PRs, immutable action pins and explicit secrets.\n"
            "Preserve existing application verification and third-party licensing.\n"
            "Document language-specific install/test commands before enabling them.\n"
            "AI is advisory; missing credentials skip explicitly.\n\n"
            "## Glossary\n\n| Name | Meaning |\n|---|---|\n"
            "| baseline | Reviewed shared repository files |\n"
            "| telemetry | Signed evidence from the shared advisory CI runner |\n"
        )
    return {
        "repository": name,
        "status": "proposal",
        "files": files,
        "base": branch,
        "parent": commit,
        "tree": tracked["sha"],
        **protection,
    }


def existing_secret_names(repository: str, names: set[str]) -> set[str]:
    """Read all necessary pages while returning names only, never secret values."""
    found: set[str] = set()
    page = 1
    while True:
        secrets = mapping(
            github_api(
                f"repos/{repository}/actions/secrets?per_page={PAGE_SIZE}&page={page}"
            )
        )
        batch = objects(secrets["secrets"])
        found.update(str(item["name"]) for item in batch if item.get("name") in names)
        if found == names or len(batch) < PAGE_SIZE:
            return found
        page += 1


def provision_provider_key(repository: str) -> None:
    """Set only a missing provider key, using encrypted CLI stdin without logging."""
    key = os.environ.get("AI_API_KEY", "")
    if not key:
        return
    if "AI_API_KEY" in existing_secret_names(repository, {"AI_API_KEY"}):
        return
    subprocess.run(
        ["gh", "secret", "set", "AI_API_KEY", "--repo", repository],
        input=key,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )


def provision_maintenance_app(repository: str) -> None:
    """Provision an absent approved pair only to a freshly verified public target."""
    names = ("BOT_APP_ID", "BOT_APP_KEY")
    values = {name: os.environ.get(name, "") for name in names}
    if not any(values.values()):
        return
    if not all(values.values()):
        message = "maintenance App provisioning requires a complete pair"
        raise ValueError(message)
    metadata = mapping(github_api(f"repos/{repository}"))
    if (
        not repository.startswith(OWNER + "/")
        or metadata.get("full_name") != repository
        or metadata.get("private") is not False
        or metadata.get("visibility") != "public"
        or metadata.get("archived") is not False
        or metadata.get("fork") is not False
        or metadata.get("disabled") is not False
    ):
        message = "maintenance credentials require a verified public target"
        raise ValueError(message)
    found = existing_secret_names(repository, set(names))
    if found:
        if found != set(names):
            message = "existing partial maintenance identity requires owner review"
            raise ValueError(message)
        return
    for name in names:
        subprocess.run(
            ["gh", "secret", "set", name, "--repo", repository],
            input=values[name],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )


def publish(plan: dict[str, Any]) -> str | None:
    """Open one draft enrollment PR; never overwrite a branch or merge changes."""
    repository = plan["repository"]
    metadata = mapping(github_api(f"repos/{repository}"))
    if metadata.get("private") is not False or metadata.get("archived") is not False:
        message = "repository is no longer eligible for public enrollment"
        raise ValueError(message)
    opened = objects(
        github_api(f"repos/{repository}/pulls?state=open&head={OWNER}:{BRANCH}")
    )
    if opened:
        provision_maintenance_app(repository)
        provision_provider_key(repository)
        return str(opened[0]["html_url"])
    files = plan["files"]
    if not files:
        provision_maintenance_app(repository)
        provision_provider_key(repository)
        return None
    if set(files) - set(FILES):
        message = "proposal contains files outside the reviewed allowlist"
        raise ValueError(message)
    created_tree = mapping(
        github_api(
            f"repos/{repository}/git/trees",
            "POST",
            {
                "base_tree": plan["tree"],
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "content": content}
                    for path, content in files.items()
                ],
            },
        )
    )
    commit = mapping(
        github_api(
            f"repos/{repository}/git/commits",
            "POST",
            {
                "message": "ci: enroll in shared engineering processes\n\n"
                "Co-Authored-By: Codex <noreply@openai.com>",
                "tree": created_tree["sha"],
                "parents": [plan["parent"]],
            },
        )
    )
    github_api(
        f"repos/{repository}/git/refs",
        "POST",
        {
            "ref": "refs/heads/" + BRANCH,
            "sha": commit["sha"],
        },
    )
    provision_maintenance_app(repository)
    provision_provider_key(repository)
    pull = mapping(
        github_api(
            f"repos/{repository}/pulls",
            "POST",
            {
                "title": "ci: enroll in shared engineering processes",
                "head": BRANCH,
                "base": plan["base"],
                "draft": True,
                "body": "## What\n\nAdd missing reviewed public starter files and "
                "nine shared process callers. Preserve existing application files."
                "\n\n## Why\n\nEvery public repository joins by a reviewable PR."
                "\n\n## How to test\n\nReview licensing and domain instructions. "
                "Run policy/security checks and add language-specific verification. "
                "AI requires AI_API_KEY; fix/baseline PRs need the automation App. "
                "Settings enforcement needs governance inventory and reviewed "
                "import/apply. This PR is never auto-merged.\n\nGenerated by "
                "deterministic fleet onboarding. Private repositories require "
                "the separate private profile.",
            },
        )
    )
    return str(pull["html_url"])


def main() -> None:
    """Dry-run with public reads, or apply only with a scoped installation token."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        discovered = repositories(installation=args.apply)
        starter = templates()
        outcomes: list[dict[str, Any]] = []
        for repository in discovered:
            plan = proposal(repository, starter)
            outcomes.append(
                {
                    "repository": plan["repository"],
                    "status": plan["status"],
                    "missing_files": sorted(plan["files"]),
                    "default_branch_protected": plan.get("default_branch_protected"),
                    "blocking_findings": plan.get("blocking_findings", []),
                    "pull_request": publish(plan) if args.apply else None,
                }
            )
        args.output.write_text(
            json.dumps(
                {
                    "baseline_commit": BASELINE_COMMIT,
                    "platform_commit": PLATFORM_COMMIT,
                    "platform_release": PLATFORM_RELEASE,
                    "repositories": outcomes,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        message = (
            "Fleet enrollment failed; external responses and credentials withheld."
        )
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
