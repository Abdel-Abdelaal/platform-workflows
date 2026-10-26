"""Recurring intake never promotes unsigned, private or concurrent tasks."""

from typing import Any
from unittest.mock import Mock

import pytest

from tools import ai_agent_cycle as intake


def test_discovery_excludes_private_fork_archived_and_self(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows: list[dict[str, object]] = []
    for name, flags in [
        ("new-public", {}),
        ("private", {"private": True}),
        ("fork", {"fork": True}),
        ("old", {"archived": True}),
        ("agent-dispatcher", {}),
    ]:
        rows.append(
            {
                "full_name": f"{intake.OWNER}/{name}",
                "private": False,
                "fork": False,
                "archived": False,
                **flags,
            }
        )
    monkeypatch.setattr(intake, "github_api", Mock(return_value=rows))
    assert intake.repositories() == [f"{intake.OWNER}/new-public"]


def test_busy_queue_never_downloads_or_promotes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intake, "repositories", lambda: ["o/r"])
    monkeypatch.setattr(intake, "github_api", Mock(return_value=[{"number": 1}]))
    promote = Mock()
    monkeypatch.setattr(intake, "promote", promote)
    assert intake.cycle(apply=True) == {"status": "queue_busy"}
    promote.assert_not_called()


def test_unsigned_asset_never_promotes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "repositories", lambda: ["o/r"])

    def api(endpoint: str) -> list[dict[str, Any]]:
        if "/issues?" in endpoint:
            return []
        if "/assets?" in endpoint:
            return [{"name": "ai-123-1-audit.json"}]
        return [{"id": 1, "tag_name": "ai-telemetry-2026-10"}]

    monkeypatch.setattr(intake, "github_api", api)
    promote = Mock()
    monkeypatch.setattr(intake, "promote", promote)
    assert intake.cycle(apply=True) == {"status": "no_eligible_proposal"}
    promote.assert_not_called()


def test_one_verified_promotion_per_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(intake, "repositories", lambda: ["o/r"])

    def api(endpoint: str) -> list[dict[str, Any]]:
        if "/issues?" in endpoint:
            return []
        if "/assets?" in endpoint:
            return [
                {"name": f"ai-123-1-audit.{suffix}"}
                for suffix in ("json", "sigstore.json")
            ]
        return [{"id": 1, "tag_name": "ai-telemetry-2026-10"}]

    monkeypatch.setattr(intake, "github_api", api)
    monkeypatch.setattr(intake, "gh", Mock(return_value=Mock(returncode=0)))
    promote = Mock(return_value={"status": "promoted"})
    monkeypatch.setattr(intake, "promote", promote)
    assert intake.cycle(apply=True) == {"status": "promoted"}
    assert promote.call_count == 1
    assert promote.call_args.kwargs == {"apply": True}
