"""Offline contracts for opt-in budget experiments; no provider inference."""

import json
from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
from unittest.mock import Mock

import pytest

from tools import ai_runner, ai_telemetry


@pytest.mark.parametrize("output", [32000, 131072])
@pytest.mark.parametrize("timeout", [600, 3600])
def test_experimental_limits_are_explicit_and_credential_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, output: int, timeout: int
):
    monkeypatch.setenv("GH_TOKEN", "not-for-model")
    monkeypatch.setenv("BOT_APP_KEY", "not-for-model")
    budget = ai_runner.ExperimentBudget(output, timeout)
    environment = ai_runner.isolated_environment(
        tmp_path, "provider-key", experiment=budget
    )
    config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    model = config["provider"]["mimo"]["models"]["mimo-v2.6-flash"]
    assert model["limit"]["output"] == output
    assert environment["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] == str(output)
    assert model["options"]["thinking"] == {"type": "enabled"}
    assert config["provider"]["mimo"]["options"]["baseURL"] == ai_runner.BASE_URL
    assert config["permission"] == {"*": "deny"}
    assert config["agent"]["review"]["permission"] == {"*": "deny"}
    assert config["small_model"] == config["model"] == ai_runner.MODEL
    assert "GH_TOKEN" not in environment
    assert "BOT_APP_KEY" not in environment
    assert "provider-key" not in environment["OPENCODE_CONFIG_CONTENT"]


@pytest.mark.parametrize(
    ("output", "timeout"),
    [(True, 600), (32000, False), (32768, 600), (32000, 1200), (131073, 3600)],
)
def test_arbitrary_or_boolean_experimental_limits_are_rejected(
    output: int, timeout: int
):
    with pytest.raises(ValueError, match="Unsupported experiment budget"):
        ai_runner.ExperimentBudget(output, timeout)


@pytest.mark.parametrize(
    ("thinking", "url"),
    [(False, ai_runner.BASE_URL), (True, "https://api.example.invalid/v1")],
)
def test_experiment_cannot_disable_thinking_or_switch_endpoints(
    monkeypatch: pytest.MonkeyPatch, thinking: bool, url: str
):
    monkeypatch.setenv("AI_BASE_URL", url)
    with pytest.raises(ValueError, match="Token Plan"):
        ai_runner.runner_config(
            thinking=thinking, experiment=ai_runner.ExperimentBudget(131072, 3600)
        )


def test_experiment_requires_output_scanner_before_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    monkeypatch.setattr(ai_runner, "prepare_output_scanner", Mock(return_value=None))
    run = Mock()
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    record = ai_telemetry.new_record("context", "prompt", thinking=True)
    token = ai_telemetry.CURRENT.set(record)
    try:
        with pytest.raises(ai_runner.AnalysisUnavailableError):
            ai_runner.analyze(
                "context",
                "prompt",
                "key",
                experiment=ai_runner.ExperimentBudget(131072, 3600),
            )
    finally:
        ai_telemetry.CURRENT.reset(token)
    assert record["evidence_gap"] is True
    assert record["configuration"]["experiment_budget"]["output_tokens"] == 131072
    run.assert_not_called()


@pytest.mark.parametrize("output", [32000, 131072])
@pytest.mark.parametrize("timeout", [600, 3600])
@pytest.mark.parametrize("result", ["valid", "invalid", "timeout"])
def test_one_attempt_and_effective_budget_are_recorded(
    monkeypatch: pytest.MonkeyPatch, result: str, output: int, timeout: int
):
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    monkeypatch.setattr(
        ai_runner, "prepare_output_scanner", Mock(return_value=Path("scanner"))
    )

    def scanned(events: str, _key: str, _scanner: Path | None) -> tuple[str, int]:
        return events, 0

    monkeypatch.setattr(ai_runner, "safe_events", scanned)
    event = json.dumps(
        {
            "type": "text",
            "part": {
                "text": '{"summary":"review"}' if result == "valid" else "invalid"
            },
        }
    )
    run = (
        Mock(side_effect=TimeoutExpired("opencode", timeout))
        if result == "timeout"
        else Mock(return_value=CompletedProcess([], 0, event))
    )
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    record = ai_telemetry.new_record("context", "prompt", thinking=True)
    token = ai_telemetry.CURRENT.set(record)
    try:
        if result == "valid":
            assert (
                ai_runner.analyze(
                    "context",
                    "prompt",
                    "key",
                    experiment=ai_runner.ExperimentBudget(output, timeout),
                ).summary
                == "review"
            )
        else:
            with pytest.raises(ai_runner.AnalysisUnavailableError):
                ai_runner.analyze(
                    "context",
                    "prompt",
                    "key",
                    experiment=ai_runner.ExperimentBudget(output, timeout),
                )
    finally:
        ai_telemetry.CURRENT.reset(token)
    environment = run.call_args.kwargs["env"]
    assert environment["OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"] == str(output)
    config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    assert (
        config["provider"]["mimo"]["models"]["mimo-v2.6-flash"]["limit"]["output"]
        == output
    )
    assert run.call_count == 1
    assert run.call_args.kwargs["timeout"] == timeout
    assert len(record["attempts"]) == 1
    assert record["configuration"]["experiment_budget"] == {
        "output_tokens": output,
        "timeout_seconds": timeout,
        "attempt_limit": 1,
        "correctness": "awaiting independent adjudication",
    }


def test_default_environment_does_not_inherit_experimental_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX", "131072")
    environment = ai_runner.isolated_environment(tmp_path, "key")
    config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    assert "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX" not in environment
    model = config["provider"]["mimo"]["models"]["mimo-v2.6-flash"]
    assert model["limit"]["output"] == 32768
    assert model["options"] == {}


def test_experiment_refuses_execution_without_active_telemetry(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    run = Mock()
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    token = ai_telemetry.CURRENT.set(None)
    try:
        with pytest.raises(ai_runner.AnalysisUnavailableError):
            ai_runner.analyze(
                "context",
                "prompt",
                "key",
                experiment=ai_runner.ExperimentBudget(131072, 3600),
            )
    finally:
        ai_telemetry.CURRENT.reset(token)
    run.assert_not_called()


@pytest.mark.parametrize(
    ("thinking", "url"),
    [(False, ai_runner.BASE_URL), (True, "https://api.example.invalid/v1")],
)
def test_refused_experiment_is_recorded_before_any_execution(
    monkeypatch: pytest.MonkeyPatch, thinking: bool, url: str
):
    monkeypatch.setenv("AI_BASE_URL", url)
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    run = Mock()
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    record = ai_telemetry.new_record("context", "prompt", thinking=thinking)
    token = ai_telemetry.CURRENT.set(record)
    try:
        with pytest.raises(ai_runner.AnalysisUnavailableError):
            ai_runner.analyze(
                "context",
                "prompt",
                "key",
                thinking=thinking,
                experiment=ai_runner.ExperimentBudget(32000, 600),
            )
    finally:
        ai_telemetry.CURRENT.reset(token)
    run.assert_not_called()
    assert record["evidence_gap_reason"] == "experiment configuration refused"
    assert record["configuration"]["experiment_budget"]["attempt_limit"] == 1
