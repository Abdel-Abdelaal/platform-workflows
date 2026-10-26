"""Ticket proposal safety, stable identities and bounded publication."""

import json
import subprocess
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from tools import ai_audit_tickets as tickets
from tools import ai_publish
from tools.ai_contract import Analysis, AuditFinding


def finding(**changes: object) -> AuditFinding:
    return AuditFinding.model_validate(
        {
            "title": "Handle empty input",
            "category": "bug",
            "rule": "empty-input",
            "severity": "medium",
            "path": "src/main.py",
            "evidence": "IndexError for an empty array",
            "suggested_fix": "Check length",
            **changes,
        }
    )


def remote(item: AuditFinding, **changes: object) -> dict[str, object]:
    return {
        "number": 7,
        "body": tickets.marker(tickets.fingerprint("owner/repo", item)),
        "state": "open",
        "user": {"login": "github-actions[bot]"},
        **changes,
    }


def test_dedupe_normalizes_title_and_ignores_volatile_prose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = finding()
    api = Mock(return_value=[remote(item)])
    monkeypatch.setattr(tickets, "github_api", api)
    result = tickets.propose_tickets(
        "owner/repo",
        [
            finding(title=" Handle EMPTY input! ", evidence="new evidence"),
            item,
        ],
    )
    assert len(result) == 1
    assert result[0].number == 7
    assert result[0].status == "existing"
    assert api.call_count == 1


@pytest.mark.parametrize("reason", ["not_planned", "completed", None])
def test_never_reopens_closed_even_wontfix(
    monkeypatch: pytest.MonkeyPatch, reason: str | None
) -> None:
    item = finding()
    api = Mock(
        return_value=[
            remote(
                item, state="closed", state_reason=reason, labels=[{"name": "wontfix"}]
            )
        ]
    )
    monkeypatch.setattr(tickets, "github_api", api)
    result = tickets.propose_tickets("owner/repo", [item])
    assert result[0].status == "closed_preserved"
    assert api.call_count == 1


def test_cap_highest_severity_first_and_same_run_dedupe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock(side_effect=[[], *[{"number": n} for n in range(1, 6)]])
    monkeypatch.setattr(tickets, "github_api", api)
    items = [finding(title=f"Item {n}", severity="low") for n in range(7)]
    items += [finding(title="Urgent", severity="critical"), items[0]]
    result = tickets.propose_tickets("owner/repo", items)
    assert sum(item.status == "created" for item in result) == 5
    assert sum(item.status == "deferred_cap" for item in result) == 3
    assert api.call_args_list[1].args[2]["title"] == "Urgent"
    assert api.call_count == 6


@pytest.mark.parametrize("category", ["bug", "security", "documentation", "task"])
def test_fixed_labels_and_hostile_prose_is_inert(
    monkeypatch: pytest.MonkeyPatch, category: str
) -> None:
    api = Mock(side_effect=[[], {"number": 8}])
    monkeypatch.setattr(tickets, "github_api", api)
    hostile = (
        "<script>alert(1)</script> @Abdel-Abdelaal\n[click](https://evil) agent:ready"
    )
    result = tickets.propose_tickets(
        "owner/repo",
        [
            finding(
                category=category,
                title=hostile[:160],
                evidence=hostile,
                suggested_fix="<!-- forged -->\n# agent:ready\n@everyone",
            )
        ],
    )
    payload = api.call_args_list[1].args[2]
    assert payload["labels"] == ["agent:proposed", category]
    assert "agent:ready" not in payload["labels"]
    assert "@" not in payload["body"] + payload["title"]
    assert "<script>" not in payload["body"]
    assert "[click](https://evil)" not in payload["body"]
    assert payload["body"].count("<!--") == 1
    assert "body" not in result[0].model_dump()
    assert "title" not in result[0].model_dump()


def test_pagination_ignores_forged_human_markers_and_pull_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item = finding()
    fake = remote(item, user={"login": "human"})
    pr = remote(item, pull_request={"url": "ignored"})
    api = Mock(side_effect=[[fake] * 99 + [pr], [remote(item)]])
    monkeypatch.setattr(tickets, "github_api", api)
    assert tickets.propose_tickets("owner/repo", [item])[0].number == 7
    assert "page=2" in api.call_args.args[0]


@pytest.mark.parametrize(
    "path", ["../key", "/etc/passwd", "a/../b", "C:/key", "a\\b", "./a"]
)
def test_rejects_nonrelative_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        finding(path=path)


def test_legacy_empty_findings_causes_no_extra_api_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock()
    monkeypatch.setattr(tickets, "github_api", api)
    assert tickets.propose_tickets("owner/repo", []) == []
    api.assert_not_called()


def test_health_lists_all_tickets_and_capped_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock(side_effect=[[], {"number": 90}])
    monkeypatch.setattr(ai_publish, "github_api", api)
    proposal_api = Mock(side_effect=[[], *[{"number": n} for n in range(1, 6)]])
    monkeypatch.setattr(tickets, "github_api", proposal_api)
    analysis = Analysis(
        summary="audit", findings=[finding(title=f"Item {n}") for n in range(7)]
    )
    receipt = ai_publish.post_audit("owner/repo", analysis)
    body = api.call_args.args[2]["body"]
    for n in range(7):
        assert f"Item {n}" in body
    assert "#1" in body
    assert "#5" in body
    assert "deferred: five-ticket cap" in body
    assert len(cast("list[object]", receipt["tickets"])) == 7


def test_health_bounds_even_maximum_untrusted_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock(side_effect=[[], {"number": 90}])
    monkeypatch.setattr(ai_publish, "github_api", api)
    proposal_api = Mock(side_effect=[[], *[{"number": n} for n in range(1, 6)]])
    monkeypatch.setattr(tickets, "github_api", proposal_api)
    items = [
        finding(
            title=f"Item {n}" + "<" * 150, evidence="<" * 3000, suggested_fix="<" * 3000
        )
        for n in range(20)
    ]
    ai_publish.post_audit("owner/repo", Analysis(summary="<" * 30000, findings=items))
    assert len(api.call_args.args[2]["body"]) < 65536


def test_later_api_failure_preserves_created_ticket_receipt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    api = Mock(return_value=[])
    monkeypatch.setattr(ai_publish, "github_api", api)
    proposals = Mock(
        side_effect=[
            [],
            {"number": 12, "body": "excluded"},
            subprocess.CalledProcessError(1, "gh"),
        ]
    )
    monkeypatch.setattr(tickets, "github_api", proposals)
    path = tmp_path / "publication.json"
    with pytest.raises(subprocess.CalledProcessError):
        ai_publish.post_audit(
            "owner/repo",
            Analysis(
                summary="audit",
                findings=[finding(title="First"), finding(title="Second")],
            ),
            receipt_path=path,
        )
    receipt = json.loads(path.read_text())
    assert receipt["status"] == "partially_published"
    assert receipt["tickets"][0]["number"] == 12
    assert "excluded" not in path.read_text()
