import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import hook_updates

NOW = datetime(2026, 10, 25, tzinfo=UTC)
OLD = "a" * 40
NEW = "b" * 40
CONFIG = (
    "repos:\n  - repo: https://github.com/owner/hooks\n"
    f"    rev: {OLD} # v1.0.0\n    hooks:\n      - id: check\n"
)


def release(tag: str, date: str = "2026-10-01T00:00:00Z") -> dict[str, object]:
    return {"tag_name": tag, "published_at": date, "draft": False, "prerelease": False}


def api(
    monkeypatch: pytest.MonkeyPatch, releases: list[dict[str, object]], sha: str = NEW
) -> Mock:
    mock = Mock(
        side_effect=[{"archived": False, "disabled": False}, releases, {"sha": sha}]
    )
    monkeypatch.setattr(hook_updates, "github_api", mock)
    return mock


def test_newest_eligible_version_not_newest_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock = api(
        monkeypatch,
        [
            release("v9.0.0", "2026-10-24T00:00:00Z"),
            release("v1.2.0"),
            release("v1.1.0", "2026-10-10T00:00:00Z"),
        ],
    )
    changed, evidence = hook_updates.propose(CONFIG, NOW)
    assert f"rev: {NEW} # v1.2.0" in changed
    assert changed.splitlines()[-2:] == CONFIG.splitlines()[-2:]
    assert evidence == [f"owner/hooks: v1.0.0 -> v1.2.0 ({NEW})"]
    assert mock.call_args.args[0].endswith("/commits/v1.2.0")


def test_exactly_fourteen_days_is_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    api(monkeypatch, [release("v1.1.0", "2026-10-11T00:00:00Z")])
    assert hook_updates.eligible_release("owner/hooks", NOW) == ("v1.1.0", NEW)


def test_preview_and_draft_releases_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    api(
        monkeypatch,
        [
            dict(release("v9.0.0"), prerelease=True),
            dict(release("v8.0.0"), draft=True),
            release("nonsense"),
            release("v1.1.0"),
        ],
    )
    assert hook_updates.eligible_release("owner/hooks", NOW)[0] == "v1.1.0"


def test_unchanged_sha_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    api(monkeypatch, [release("v1.0.0")], OLD)
    assert hook_updates.propose(CONFIG, NOW) == (CONFIG, [])


@pytest.mark.parametrize("date", ["2026-10-11T00:00:01Z", "2027-01-01T00:00:00Z"])
def test_fresh_or_future_release_cannot_bypass_cooldown(
    monkeypatch: pytest.MonkeyPatch, date: str
) -> None:
    api(monkeypatch, [release("v1.1.0", date)])
    with pytest.raises(ValueError, match="cooldown"):
        hook_updates.propose(CONFIG, NOW)


def test_unknown_age_and_bad_sha_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    api(monkeypatch, [release("v1.1.0", "2026-10-01T00:00:00")])
    with pytest.raises(ValueError, match="timezone"):
        hook_updates.propose(CONFIG, NOW)
    api(monkeypatch, [release("v1.1.0")], "main")
    with pytest.raises(ValueError, match="full commit SHA"):
        hook_updates.propose(CONFIG, NOW)


def test_archived_upstream_is_not_silently_updated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        hook_updates,
        "github_api",
        Mock(return_value={"archived": True, "disabled": False}),
    )
    with pytest.raises(ValueError, match="archived"):
        hook_updates.propose(CONFIG, NOW)


@pytest.mark.parametrize(
    "config",
    [
        CONFIG.replace("v1.0.0", "undocumented"),
        CONFIG.replace("https://github.com", "https://other.invalid"),
        CONFIG.replace(OLD, "main"),
    ],
)
def test_unverifiable_source_layout_fails(config: str) -> None:
    with pytest.raises(ValueError, match="baseline"):
        hook_updates.propose(config, NOW)


def test_downgrade_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    api(monkeypatch, [release("v0.9.0")])
    with pytest.raises(ValueError, match="downgrade"):
        hook_updates.propose(CONFIG, NOW)


@pytest.mark.parametrize("apply", [False, True])
def test_cli_defaults_to_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apply: bool
) -> None:
    path = tmp_path / "baseline/.pre-commit-config.yaml"
    path.parent.mkdir()
    path.write_text(CONFIG)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hooks", "--repository", str(tmp_path)] + (["--apply"] if apply else []),
    )
    monkeypatch.setattr(
        hook_updates, "propose", Mock(return_value=("changed", ["evidence"]))
    )
    hook_updates.main()
    assert path.read_text() == ("changed" if apply else CONFIG)
