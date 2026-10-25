import json
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from tools import ai_publish, github_api
from tools.ai_contract import Analysis, InlineFinding

DIFF = "--- a/main.py\n+++ b/main.py\n@@ -1 +1 @@\n-old\n+new"


def context() -> ai_publish.ReviewContext:
    return ai_publish.ReviewContext("owner/repo", 7, "a" * 40, DIFF)


@pytest.mark.parametrize("existing", [False, True])
def test_review_is_sticky_and_neutral_without_review_threads(
    monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    comments = (
        [{"id": 8, "body": ai_publish.MARKER, "user": {"login": "github-actions[bot]"}}]
        if existing
        else []
    )
    api = Mock(side_effect=[comments, {}, {}])
    monkeypatch.setattr(ai_publish, "github_api", api)
    analysis = Analysis(
        summary="review",
        comments=[
            InlineFinding(path="main.py", line=1, body="issue (non-blocking): evidence")
        ],
    )
    ai_publish.post_review(context(), analysis)
    calls = api.call_args_list
    assert calls[1].args[1] == ("PATCH" if existing else "POST")
    check = calls[2].args[2]
    assert check["conclusion"] == "neutral"
    assert check["output"]["annotations"][0]["annotation_level"] == "notice"
    assert all("reviews" not in call.args[0] for call in calls)


def test_comment_search_ignores_humans_and_paginates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    human = {"id": 1, "body": ai_publish.MARKER, "user": {"login": "human"}}
    own = {"id": 2, "body": ai_publish.MARKER, "user": {"login": "github-actions[bot]"}}
    monkeypatch.setattr(
        ai_publish, "github_api", Mock(side_effect=[[human] * 100, [own]])
    )
    result = ai_publish.own_comment(context())
    assert result is not None
    assert result.id == 2


@pytest.mark.parametrize("existing", [False, True])
def test_audit_updates_one_health_issue(
    monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    issues = [{"number": 3, "title": "Weekly health report"}] if existing else []
    api = Mock(side_effect=[issues, {}])
    monkeypatch.setattr(ai_publish, "github_api", api)
    ai_publish.post_audit("owner/repo", Analysis(summary="audit"))
    assert api.call_args_list[1].args[1] == ("PATCH" if existing else "POST")


@pytest.mark.parametrize("mode", ["review", "audit"])
@pytest.mark.parametrize("with_diff", [False, True])
def test_publisher_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str, with_diff: bool
) -> None:
    analysis = tmp_path / "analysis.json"
    analysis.write_text('{"summary":"review"}')
    args = [
        "tool",
        "--mode",
        mode,
        "--repository",
        "owner/repo",
        "--analysis",
        str(analysis),
    ]
    if with_diff:
        diff = tmp_path / "diff.txt"
        diff.write_text(DIFF)
        args.extend(["--diff", str(diff)])
    monkeypatch.setattr(sys, "argv", args)
    review = Mock()
    audit = Mock()
    monkeypatch.setattr(ai_publish, "post_review", review)
    monkeypatch.setattr(ai_publish, "post_audit", audit)
    ai_publish.main()
    assert (review if mode == "review" else audit).call_count == 1


@pytest.mark.parametrize("body", [None, {"body": "safe JSON"}])
@pytest.mark.parametrize("output", ["", '{"ok":true}'])
def test_github_api_uses_json_stdin_without_shell(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object] | None, output: str
) -> None:

    run = Mock(return_value=CompletedProcess([], 0, output))
    monkeypatch.setattr(github_api.subprocess, "run", run)
    result = github_api.github_api("repos/owner/repo/issues", "POST", body)
    assert "shell" not in run.call_args.kwargs
    assert run.call_args.kwargs["encoding"] == "utf-8"
    assert run.call_args.kwargs["timeout"] == 60
    assert result == ({"ok": True} if output else None)


@pytest.mark.parametrize("mode", ["review", "audit"])
def test_cli_receipt_excludes_api_bodies_and_user_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    analysis = tmp_path / "analysis.json"
    analysis.write_text('{"summary":"ok"}')
    receipt = tmp_path / "receipt.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "--mode",
            mode,
            "--repository",
            "owner/repo",
            "--analysis",
            str(analysis),
            "--receipt",
            str(receipt),
        ],
    )
    payload = {
        "status": "published",
        "comment": {"id": 7, "body": "private", "user": {"email": "private"}},
        "issue": {
            "number": 8,
            "html_url": "https://github.com/owner/repo/issues/8",
            "body": "private",
        },
    }
    monkeypatch.setattr(ai_publish, "post_review", Mock(return_value=payload))
    monkeypatch.setattr(ai_publish, "post_audit", Mock(return_value=payload))
    ai_publish.main()
    saved = json.loads(receipt.read_text())
    assert "private" not in json.dumps(saved)
    assert saved["comment"] == {"id": 7}
    assert saved["issue"]["number"] == 8


def test_partial_publication_preserves_comment_receipt_when_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = Mock(
        side_effect=[
            [],
            {"id": 7, "body": "private"},
            subprocess.CalledProcessError(1, "gh"),
        ]
    )
    monkeypatch.setattr(ai_publish, "github_api", api)
    receipt = tmp_path / "publication.json"
    with pytest.raises(subprocess.CalledProcessError):
        ai_publish.post_review(context(), Analysis(summary="ok"), receipt_path=receipt)
    saved = json.loads(receipt.read_text())
    assert saved["status"] == "partially_published"
    assert saved["comment"] == {"id": 7}
    assert "private" not in json.dumps(saved)
