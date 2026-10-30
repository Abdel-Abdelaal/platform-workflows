"""Exercise authentication, merge policy and exact-head mutation without writes."""

from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from tools import dependabot_merge as merge

SHA = "a" * 40
REPO = "Abdel-Abdelaal/example"
PUBLIC: dict[str, Any] = {
    "full_name": REPO,
    "private": False,
    "archived": False,
    "disabled": False,
    "fork": False,
    "default_branch": "main",
}
PR: dict[str, Any] = {
    "number": 1,
    "state": "open",
    "draft": False,
    "user": {"id": merge.BOT_ID},
    "commits": 1,
    "head": {
        "sha": SHA,
        "ref": "dependabot/uv/example-1.2.3",
        "repo": {"full_name": REPO},
    },
    "base": {"ref": "main"},
    "mergeable": True,
    "mergeable_state": "clean",
}
COMMIT: dict[str, Any] = {
    "sha": SHA,
    "author": {"id": merge.BOT_ID},
    "commit": {
        "verification": {"verified": True},
        "message": "update\n\n---\nupdated-dependencies:\n- dependency-name: example\n"
        "  dependency-version: 1.2.3\n"
        "  update-type: version-update:semver-patch\n...\n",
    },
}
RULES = [
    {
        "type": "required_status_checks",
        "parameters": {
            "required_status_checks": [{"context": "tests"}],
            "strict_required_status_checks_policy": True,
        },
    }
]


@pytest.mark.parametrize("field", ["private", "archived", "disabled", "fork"])
def test_rejects_ineligible_repositories(field: str) -> None:
    assert not merge.eligible({**PUBLIC, field: True})


@pytest.mark.parametrize(
    ("before", "after", "reason"),
    [
        ("semver-patch", "semver-major", "manual_update"),
        ("dependency-name: example", "dependency-name: opencode-ai", "harness_update"),
        ("dependency-name: example", "dependency-name: promptfoo", "harness_update"),
        ("semver-patch", "unknown", "manual_update"),
        ("updated-dependencies:", "other:", "unknown_metadata"),
        ("---", "missing", "unknown_metadata"),
    ],
)
def test_verified_metadata_requires_review_for_unknown_or_sensitive_changes(
    before: str, after: str, reason: str
) -> None:
    commit = deepcopy(COMMIT)
    commit["commit"]["message"] = commit["commit"]["message"].replace(before, after)
    assert merge.authenticated_updates(PR, [commit]) == reason


def test_group_with_one_major_does_not_merge() -> None:
    commit = deepcopy(COMMIT)
    commit["commit"]["message"] = commit["commit"]["message"].replace(
        "...",
        "- dependency-name: other\n  update-type: version-update:semver-major\n...",
    )
    assert merge.authenticated_updates(PR, [commit]) == "manual_update"


def test_manual_commit_and_changed_head_cannot_borrow_bot_metadata() -> None:
    assert (
        merge.authenticated_updates({**PR, "commits": 2}, [COMMIT]) == "modified_branch"
    )
    assert (
        merge.authenticated_updates(PR, [{**COMMIT, "sha": "b" * 40}])
        == "modified_branch"
    )
    assert (
        merge.authenticated_updates(PR, [{**COMMIT, "author": {"id": 1}}])
        == "unverified_commit"
    )
    commit = deepcopy(COMMIT)
    commit["commit"]["verification"]["verified"] = False
    assert merge.authenticated_updates(PR, [commit]) == "unverified_commit"


def inspection_api(
    pr: dict[str, Any] | None = None,
    rules: list[dict[str, Any]] | None = None,
) -> Mock:
    return Mock(
        side_effect=[
            PUBLIC,
            pr or PR,
            {"protected": True},
            RULES if rules is None else rules,
            [COMMIT],
            {
                "total_count": 1,
                "check_runs": [
                    {"name": "tests", "status": "completed", "conclusion": "success"}
                ],
            },
            {"total_count": 0, "statuses": []},
        ]
    )


def test_missing_required_protection_and_pending_checks_do_not_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(merge, "github_api", inspection_api(rules=[]))
    assert merge.inspect(REPO, 1)["reason"] == "missing_required_checks"
    monkeypatch.setattr(
        merge, "github_api", inspection_api(pr={**PR, "mergeable_state": "behind"})
    )
    assert merge.inspect(REPO, 1)["reason"] == "checks_reviews_or_base_pending"


@pytest.mark.parametrize(
    "change",
    [
        {"draft": True},
        {"user": {"id": 1}},
        {"base": {"ref": "other"}},
        {"head": {"repo": {"full_name": "attacker/fork"}}},
    ],
)
def test_forks_other_authors_drafts_and_other_bases_are_refused(
    monkeypatch: pytest.MonkeyPatch,
    change: dict[str, Any],
) -> None:
    api = Mock(side_effect=[PUBLIC, {**PR, **change}])
    monkeypatch.setattr(merge, "github_api", api)
    assert merge.inspect(REPO, 1)["reason"] == "ineligible_pull_request"
    assert api.call_count == 2


def test_plan_never_writes_and_apply_merges_only_one_exact_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(merge, "repositories", Mock(return_value=[PUBLIC]))
    monkeypatch.setattr(
        merge,
        "inspect",
        Mock(
            side_effect=[
                {"repository": REPO, "number": n, "reason": "eligible", "head": SHA}
                for n in [1, 2, 1, 2]
            ]
        ),
    )
    api = Mock(return_value=[PR, {**PR, "number": 2}])
    monkeypatch.setattr(merge, "github_api", api)
    assert len(merge.run(apply=False)["pull_requests"]) == 2
    assert api.call_count == 1
    api.reset_mock(side_effect=True)
    api.side_effect = [[PR, {**PR, "number": 2}], {"merged": True, "sha": "c" * 40}]
    result = merge.run(apply=True)
    assert [item["reason"] for item in result["pull_requests"]] == [
        "merged",
        "next_cycle",
    ]
    assert api.call_args.args == (
        f"repos/{REPO}/pulls/1/merge",
        "PUT",
        {"sha": SHA, "merge_method": "squash"},
    )


@pytest.mark.parametrize(
    "message",
    [
        None,
        "x" * (merge.MAX_METADATA_BYTES + 1),
        "---\n[invalid\n...\n",
        "---\nupdated-dependencies: []\n...\n",
    ],
    ids=["missing", "oversize", "invalid-yaml", "empty"],
)
def test_missing_or_broken_signed_metadata_is_not_authorization(
    message: object,
) -> None:
    assert merge.classify_updates(message) == "unknown_metadata"


def test_pre_one_minor_and_entire_group_require_review() -> None:
    message = (
        COMMIT["commit"]["message"]
        .replace("1.2.3", "0.2.3")
        .replace("semver-patch", "semver-minor")
    )
    assert merge.classify_updates(message) == "prestable_update"
    assert merge.classify_updates(COMMIT["commit"]["message"]) == "compatible"


def security_message(
    subject: str, name: str = "postcss", version: str = "8.5.31"
) -> str:
    """The shape of a real signed Dependabot security update, without update-type."""
    return (
        f"{subject}\n\nBumps postcss.\n\n---\nupdated-dependencies:\n"
        f"- dependency-name: {name}\n  dependency-version: {version}\n"
        "  dependency-type: indirect\n...\n\nSigned-off-by: dependabot[bot]\n"
    )


@pytest.mark.parametrize(
    ("subject", "reason"),
    [
        ("chore(deps): bump postcss from 8.5.20 to 8.5.31 in /web-chat", "compatible"),
        ("build(deps): Bump postcss from 8.4.9 to 8.5.31", "compatible"),
        (
            "chore(deps): bump postcss from 7.0.1 to 8.5.31 in /web-chat",
            "manual_update",
        ),
        ("chore(deps): bump postcss from 8.5.20 to 8.5.30 in /web", "unknown_metadata"),
        ("chore(deps): bump other from 8.5.20 to 8.5.31 in /web", "unknown_metadata"),
        ("chore(deps): bump postcss from 8.5.31 to 8.5.31", "unknown_metadata"),
        ("chore(deps): bump postcss from 8.5.20-rc.1 to 8.5.31", "unknown_metadata"),
        ("chore(deps): update postcss", "unknown_metadata"),
    ],
    ids=[
        "patch",
        "minor",
        "major",
        "version-mismatch",
        "name-mismatch",
        "not-an-upgrade",
        "prerelease",
        "no-versions",
    ],
)
def test_security_update_type_comes_only_from_the_agreeing_signed_subject(
    subject: str, reason: str
) -> None:
    assert merge.classify_updates(security_message(subject)) == reason


def test_security_minor_before_one_still_needs_review() -> None:
    message = security_message(
        "chore(deps): bump postcss from 0.4.1 to 0.5.0", version="0.5.0"
    )
    assert merge.classify_updates(message) == "prestable_update"


def test_grouped_updates_without_update_type_are_never_derived() -> None:
    message = security_message(
        "chore(deps): bump postcss from 8.5.20 to 8.5.31"
    ).replace("...", "- dependency-name: other\n  dependency-version: 1.0.1\n...")
    assert merge.classify_updates(message) == "unknown_metadata"


def test_real_inspection_retains_exact_authenticated_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(merge, "github_api", inspection_api())
    assert merge.inspect(REPO, 1) == {
        "repository": REPO,
        "number": 1,
        "reason": "eligible",
        "head": SHA,
    }


def test_server_refusal_never_falls_back_to_bypass_or_new_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report: dict[str, Any] = {}
    monkeypatch.setattr(merge, "repositories", Mock(return_value=[PUBLIC]))
    monkeypatch.setattr(
        merge,
        "inspect",
        Mock(
            return_value={
                "repository": REPO,
                "number": 1,
                "reason": "eligible",
                "head": SHA,
            }
        ),
    )
    api = Mock(side_effect=[[PR], RuntimeError("head changed; merge refused")])
    monkeypatch.setattr(merge, "github_api", api)
    with pytest.raises(RuntimeError, match="head changed"):
        merge.run(apply=True, report=report)
    assert api.call_count == 2
    assert report["pull_requests"][0]["reason"] == "merge_requested"
    assert "head changed" not in str(report)


def test_controller_only_runs_trusted_default_branch_code() -> None:
    workflow = yaml.safe_load(
        (
            Path(__file__).resolve().parents[1]
            / ".github/workflows/dependabot-maintenance.yml"
        ).read_text()
    )
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    job = workflow["jobs"]["maintain"]
    assert "github.ref_name == github.event.repository.default_branch" in job["if"]
    assert job["permissions"] == {"contents": "read"}
    assert "AI_API_KEY" not in str(job)
    steps = job["steps"]
    checkout = next(
        step for step in steps if step.get("uses", "").startswith("actions/checkout@")
    )
    assert checkout["with"] == {
        "ref": "${{ github.sha }}",
        "persist-credentials": False,
    }
    app = next(step for step in steps if step.get("id") == "app")
    assert app["with"]["repositories"] == "${{ steps.targets.outputs.repositories }}"
    assert "permission-administration" not in app["with"]
    assert workflow["concurrency"]["cancel-in-progress"] is False


@pytest.mark.parametrize(
    ("state", "conclusion"),
    [("completed", "failure"), ("in_progress", None), ("completed", "cancelled")],
)
def test_optional_deterministic_failures_and_pending_checks_prevent_merge(
    monkeypatch: pytest.MonkeyPatch, state: str, conclusion: str | None
) -> None:
    monkeypatch.setattr(
        merge,
        "github_api",
        Mock(
            return_value={
                "total_count": 1,
                "check_runs": [
                    {
                        "name": "lint / Lint (all languages)",
                        "status": state,
                        "conclusion": conclusion,
                    }
                ],
            }
        ),
    )
    assert not merge.checks_ready(REPO, SHA)


def test_advisory_does_not_gate_but_external_pending_status_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checks = {
        "total_count": 2,
        "check_runs": [
            {"name": "tests", "status": "completed", "conclusion": "success"},
            {"name": "review / ai / Isolated analysis", "status": "in_progress"},
        ],
    }
    api = Mock(
        side_effect=[
            checks,
            {"total_count": 1, "statuses": [{"state": "pending"}]},
            checks,
            {"total_count": 0, "statuses": []},
        ]
    )
    monkeypatch.setattr(merge, "github_api", api)
    assert not merge.checks_ready(REPO, SHA)
    assert merge.checks_ready(REPO, SHA)


def test_incomplete_check_page_is_not_a_clean_bill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        merge, "github_api", Mock(return_value={"total_count": 101, "check_runs": []})
    )
    assert not merge.checks_ready(REPO, SHA)
