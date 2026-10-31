"""Experimental CLI preflight uses fake analysis and never provider credentials."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import ai_runner, ai_telemetry
from tools.ai_contract import Analysis


def arguments(tmp_path: Path) -> list[str]:
    for name, text in (
        ("context.md", "public fixture"),
        ("prompt.md", "review"),
        ("manifest.json", '[{"path":"fixture.py","status":"included"}]'),
    ):
        (tmp_path / name).write_text(text)
    return [
        "runner",
        "--context",
        str(tmp_path / "context.md"),
        "--prompt",
        str(tmp_path / "prompt.md"),
        "--output",
        str(tmp_path / "analysis.json"),
        "--record",
        str(tmp_path / "record.json"),
        "--manifest",
        str(tmp_path / "manifest.json"),
    ]


@pytest.mark.parametrize(
    "profile", ["32000-600", "32000-3600", "131072-600", "131072-3600"]
)
def test_cli_passes_only_explicit_experimental_budget_with_active_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile: str,
) -> None:
    argv = [*arguments(tmp_path), "--experiment-profile", profile]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv("AI_API_KEY", "fake-test-key")

    def analyze(*_args: object, **kwargs: object) -> Analysis:
        record = ai_telemetry.CURRENT.get()
        assert record is not None
        assert record["configuration"]["manifest_complete"] is True
        output, timeout = map(int, profile.split("-"))
        assert kwargs["experiment"] == ai_runner.ExperimentBudget(output, timeout)
        assert kwargs["thinking"] is True
        return Analysis(summary="fake analysis")

    monkeypatch.setattr(ai_runner, "analyze", analyze)
    ai_runner.main()
    assert (
        json.loads((tmp_path / "analysis.json").read_text())["summary"]
        == "fake analysis"
    )
    assert ai_telemetry.CURRENT.get() is None


@pytest.mark.parametrize("removed", ["--record", "--manifest"])
def test_missing_receipt_arguments_refused_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    removed: str,
) -> None:
    argv = arguments(tmp_path)
    index = argv.index(removed)
    del argv[index : index + 2]
    monkeypatch.setattr(sys, "argv", [*argv, "--experiment-profile", "131072-3600"])
    analyze = Mock()
    monkeypatch.setattr(ai_runner, "analyze", analyze)
    with pytest.raises(SystemExit):
        ai_runner.main()
    analyze.assert_not_called()


@pytest.mark.parametrize(
    ("manifest", "reason"),
    [
        ("not JSON", "experimental input manifest unavailable"),
        ("[]", "experimental input manifest empty"),
        ('[{"x":"y"}]', "experimental input manifest lacks path or status"),
        ('[{"path":"a.py"}]', "experimental input manifest lacks path or status"),
    ],
)
def test_invalid_manifest_preserves_refusal_record_without_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: str,
    reason: str,
) -> None:
    argv = arguments(tmp_path)
    (tmp_path / "manifest.json").write_text(manifest)
    monkeypatch.setattr(sys, "argv", [*argv, "--experiment-profile", "131072-3600"])
    analyze = Mock()
    monkeypatch.setattr(ai_runner, "analyze", analyze)
    with pytest.raises(ai_runner.AnalysisUnavailableError):
        ai_runner.main()
    analyze.assert_not_called()
    record = json.loads((tmp_path / "record.json").read_text())
    assert record["evidence_gap"] is True
    assert record["evidence_gap_reason"] == reason
    assert record["attempts"] == []
    assert record["configuration"]["requested_experiment_profile"] == "131072-3600"
    assert ai_telemetry.CURRENT.get() is None


def test_disabled_thinking_refused_before_analysis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            *arguments(tmp_path),
            "--experiment-profile",
            "131072-3600",
            "--thinking",
            "disabled",
        ],
    )
    analyze = Mock()
    monkeypatch.setattr(ai_runner, "analyze", analyze)
    with pytest.raises(SystemExit):
        ai_runner.main()
    analyze.assert_not_called()


def test_omitting_the_profile_keeps_production_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "argv", arguments(tmp_path))
    monkeypatch.setenv("AI_API_KEY", "fake-test-key")
    seen: dict[str, object] = {}

    def analyze(*_args: object, **kwargs: object) -> Analysis:
        seen.update(kwargs)
        return Analysis(summary="fake analysis")

    monkeypatch.setattr(ai_runner, "analyze", analyze)
    ai_runner.main()
    assert seen["experiment"] is None
    record = json.loads((tmp_path / "record.json").read_text())
    assert "requested_experiment_profile" not in record["configuration"]


def test_missing_key_marks_an_experiment_as_an_evidence_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv = [*arguments(tmp_path), "--experiment-profile", "32000-600"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv("AI_API_KEY", raising=False)
    analyze = Mock()
    monkeypatch.setattr(ai_runner, "analyze", analyze)
    ai_runner.main()
    analyze.assert_not_called()
    record = json.loads((tmp_path / "record.json").read_text())
    assert record["status"] == "skipped"
    assert record["evidence_gap"] is True
    assert record["evidence_gap_reason"] == "provider key missing"
    assert json.loads((tmp_path / "analysis.json").read_text()) == {
        "skipped": "AI_API_KEY missing"
    }
