"""Autonomous intake accepts signed, unchanged proposals rather than model authority."""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import ai_agent_promote as promote
from tools.ai_agent_schema import AgentEvidenceError
from tools.ai_audit_tickets import fingerprint, ticket_payload
from tools.ai_contract import Analysis, AuditFinding

REPO = "Abdel-Abdelaal/shortlink"


def finding(path: str = "README.md") -> AuditFinding:
    return AuditFinding(
        title="Refresh documented tests",
        category="documentation",
        severity="low",
        rule="stale-tests",
        path=path,
        evidence="Documented count differs",
        suggested_fix="Verify and update the measured count",
    )


def fixture() -> tuple[dict[str, object], dict[str, object]]:
    item = finding()
    digest = fingerprint(REPO, item)
    record: dict[str, object] = {
        "schema_version": 1,
        "status": "valid",
        "identity": {"github_repository": REPO, "mode": "audit"},
        "analysis": Analysis(summary="audit", findings=[item]).model_dump(),
        "publication": [
            {
                "mode": "audit",
                "status": "published",
                "tickets": [
                    {"number": 39, "fingerprint": digest},
                ],
            }
        ],
    }
    payload = ticket_payload(item, digest)
    issue: dict[str, object] = {
        "state": "open",
        "user": {"login": "github-actions[bot]"},
        "title": payload["title"],
        "body": payload["body"],
        "labels": [{"name": "agent:proposed"}, {"name": "documentation"}],
    }
    return record, issue


@pytest.mark.parametrize(
    "path", [".github/workflows/a.yml", "docs/AGENTS.md", "src/package-lock.json"]
)
def test_protected_paths_are_not_eligible(path: str) -> None:
    assert not promote.eligible(finding(path))


@pytest.mark.parametrize(
    "changes",
    [
        {"state": "closed"},
        {"user": {"login": "human"}},
        {"body": "forged marker"},
        {"title": "changed task"},
        {"pull_request": {}},
        {
            "labels": [
                {"name": "agent:proposed"},
                {"name": "documentation"},
                {"name": "wontfix"},
            ]
        },
        {
            "labels": [
                {"name": "agent:proposed"},
                {"name": "documentation"},
                {"name": "agent:running"},
            ]
        },
    ],
)
def test_changed_closed_or_active_tasks_are_not_promoted(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, object]
) -> None:
    record, issue = fixture()
    issue.update(changes)
    api = Mock(return_value=issue)
    monkeypatch.setattr(promote, "github_api", api)
    assert promote.select(REPO, record) is None
    assert all(len(call.args) == 1 for call in api.call_args_list)


def test_explicit_owner_policy_promotes_only_fixed_ready_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record, issue = fixture()
    monkeypatch.setattr(promote, "evidence", Mock(return_value=record))
    api = Mock(side_effect=[issue, {"login": "Abdel-Abdelaal"}, {}, {}])
    monkeypatch.setattr(promote, "github_api", api)
    result = promote.promote(REPO, tmp_path / "record", tmp_path / "bundle", apply=True)
    assert result["status"] == "promoted"
    assert api.call_args_list[-1].args[2] == {"labels": ["agent:ready"]}
    assert api.call_args_list[-2].args[0].endswith("/comments")


def test_dry_run_has_no_writes_and_missing_receipt_has_no_candidate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record, issue = fixture()
    monkeypatch.setattr(promote, "evidence", Mock(return_value=record))
    api = Mock(return_value=issue)
    monkeypatch.setattr(promote, "github_api", api)
    assert (
        promote.promote(REPO, tmp_path / "r", tmp_path / "b", apply=False)["status"]
        == "eligible"
    )
    assert api.call_count == 1
    record["publication"] = []
    assert promote.select(REPO, record) is None


def test_unverified_signature_and_private_source_fail_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record, _issue = fixture()
    subject, bundle = tmp_path / "r.json", tmp_path / "b.json"
    subject.write_text(json.dumps(record))
    bundle.write_text("{}")
    monkeypatch.setattr(promote, "public_repository", Mock(return_value=False))
    with pytest.raises(AgentEvidenceError):
        promote.evidence(REPO, subject, bundle)
    monkeypatch.setattr(promote, "public_repository", Mock(return_value=True))
    monkeypatch.setattr(
        promote, "github_api", Mock(return_value={"default_branch": "main"})
    )
    signed = Mock(return_value=subprocess.CompletedProcess([], 1, "withheld"))
    monkeypatch.setattr(promote, "gh", signed)
    with pytest.raises(AgentEvidenceError):
        promote.evidence(REPO, subject, bundle)
    assert "refs/heads/main" in signed.call_args.args[0]
    signed.return_value = subprocess.CompletedProcess([], 0, "verified")
    assert promote.evidence(REPO, subject, bundle)["status"] == "valid"
