"""Owner-authorized autonomous intake from verified, unchanged audit proposals."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from tools.ai_agent_ingest import public_repository
from tools.ai_agent_schema import OWNER, AgentEvidenceError
from tools.ai_audit_tickets import SEVERITY, fingerprint, ticket_payload
from tools.ai_contract import Analysis, AuditFinding
from tools.ai_telemetry import mapping
from tools.ai_telemetry_archive import gh
from tools.github_api import github_api

MAX_BYTES = 2_000_000
PREDICATE = f"https://github.com/{OWNER}/platform-workflows/blob/main/docs/ai-telemetry.md#record-v1"
SIGNER = f"{OWNER}/platform-workflows/.github/workflows/ai.yml"
POLICY = "verified-audit-intake/v1"
ALLOWED_ROOTS = {"src", "tests", "docs", "standards", "app"}
ALLOWED_SUFFIXES = {
    ".py",
    ".md",
    ".kt",
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
}
FORBIDDEN = {
    ".github",
    ".claude",
    ".codex",
    ".git",
    "agents.md",
    "claude.md",
    "codeowners",
}


def eligible(finding: AuditFinding) -> bool:
    """Keep protected configuration/credentials out before dispatcher gates run."""
    path = PurePosixPath(finding.path)
    return (
        not set(part.lower() for part in path.parts) & FORBIDDEN
        and (finding.path == "README.md" or path.parts[0] in ALLOWED_ROOTS)
        and path.suffix in ALLOWED_SUFFIXES
    )


def evidence(repository: str, record: Path, bundle: Path) -> dict[str, Any]:
    """Only default-branch public audit subjects signed by the shared runner qualify."""
    if not re.fullmatch(
        rf"{OWNER}/[A-Za-z0-9_.-]+", repository
    ) or not public_repository(repository):
        raise AgentEvidenceError
    metadata = mapping(github_api(f"repos/{repository}"))
    branch = str(metadata["default_branch"])
    if not re.fullmatch(r"[A-Za-z0-9_.\/-]+", branch):
        raise AgentEvidenceError
    if record.stat().st_size > MAX_BYTES or bundle.stat().st_size > MAX_BYTES * 2:
        raise AgentEvidenceError
    verified = gh(
        [
            "attestation",
            "verify",
            str(record),
            "--repo",
            repository,
            "--bundle",
            str(bundle),
            "--signer-workflow",
            SIGNER,
            "--predicate-type",
            PREDICATE,
            "--source-ref",
            f"refs/heads/{branch}",
            "--deny-self-hosted-runners",
        ]
    )
    if verified.returncode:
        raise AgentEvidenceError
    document = mapping(json.loads(record.read_text(encoding="utf-8")))
    identity = mapping(document.get("identity"))
    if (
        document.get("schema_version") != 1
        or document.get("status") != "valid"
        or identity.get("github_repository") != repository
        or identity.get("mode") != "audit"
    ):
        raise AgentEvidenceError
    return document


def select(
    repository: str, document: dict[str, Any], issue_number: int | None = None
) -> dict[str, object] | None:
    """Verify the publication receipt and exact live body before promoting one task."""
    analysis = Analysis.model_validate(document["analysis"])
    tickets: dict[str, int] = {}
    for receipt in document.get("publication", []):
        if receipt.get("mode") == "audit" and receipt.get("status") == "published":
            tickets.update(
                {
                    t["fingerprint"]: t["number"]
                    for t in receipt.get("tickets", [])
                    if type(t.get("number")) is int
                }
            )
    for finding in sorted(analysis.findings, key=lambda f: SEVERITY[f.severity]):
        digest = fingerprint(repository, finding)
        number = tickets.get(digest)
        if (
            number is None
            or (issue_number is not None and number != issue_number)
            or not eligible(finding)
        ):
            continue
        issue = mapping(github_api(f"repos/{repository}/issues/{number}"))
        labels = {str(label.get("name")) for label in issue.get("labels", [])}
        expected = ticket_payload(finding, digest)
        if (
            issue.get("state") != "open"
            or mapping(issue.get("user")).get("login") != "github-actions[bot]"
            or issue.get("pull_request") is not None
            or issue.get("title") != expected["title"]
            or issue.get("body") != expected["body"]
            or not {"agent:proposed", finding.category} <= labels
            or "wontfix" in labels
            or any(
                label.startswith("agent:") and label != "agent:proposed"
                for label in labels
            )
        ):
            continue
        return {
            "repository": repository,
            "issue": number,
            "fingerprint": digest,
            "path": finding.path,
            "policy": POLICY,
        }
    return None


def promote(
    repository: str,
    record: Path,
    bundle: Path,
    *,
    apply: bool,
    issue_number: int | None = None,
) -> dict[str, object]:
    """The trusted owner controller labels a verified task; models never do."""
    document = evidence(repository, record, bundle)
    selected = select(repository, document, issue_number)
    if selected is None:
        return {"status": "no_eligible_proposal", "policy": POLICY}
    if apply:
        if mapping(github_api("user")).get("login") != OWNER:
            raise AgentEvidenceError
        endpoint = f"repos/{repository}/issues/{selected['issue']}"
        github_api(
            f"{endpoint}/comments",
            "POST",
            {
                "body": (
                    f"<!-- {POLICY}:{selected['fingerprint']} -->\n"
                    "Selected under the owner's autonomous-intake policy. "
                    "Signed audit and unchanged bot proposal verified. "
                    "Dispatcher path, diff, test and quota gates remain enforced."
                )
            },
        )
        github_api(f"{endpoint}/labels", "POST", {"labels": ["agent:ready"]})
    return {**selected, "status": "promoted" if apply else "eligible"}


def main() -> None:
    """Dry-run by default; apply is an explicit trusted controller operation."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--issue", type=int)
    args = parser.parse_args()
    try:
        sys.stdout.write(
            json.dumps(
                promote(
                    args.repository,
                    args.record,
                    args.bundle,
                    apply=args.apply,
                    issue_number=args.issue,
                )
            )
        )
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        message = "Autonomous intake failed closed; payload and diagnostics withheld."
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
