import json
import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from tools import ai_runner
from tools.ai_contract import Analysis


def test_environment_excludes_privileged_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_TOKEN", "github-secret")
    monkeypatch.setenv("GOV_APP_KEY", "private-secret")
    monkeypatch.setenv("PATH", "safe-path")
    environment = ai_runner.isolated_environment(tmp_path, "ai-secret")
    assert "GH_TOKEN" not in environment
    assert "GOV_APP_KEY" not in environment
    assert environment["AI_API_KEY"] == "ai-secret"
    config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    assert config["permission"] == {"*": "deny"}
    assert config["model"] == "mimo/mimo-v2.6-flash"
    assert config["small_model"] == config["model"]
    assert config["share"] == "disabled"
    assert config["agent"]["review"]["steps"] == 3
    assert "ai-secret" not in environment["OPENCODE_CONFIG_CONTENT"]


def test_missing_runner_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value=None))
    with pytest.raises(ai_runner.MissingRunnerError):
        ai_runner.analyze("context", "prompt", "key")


def test_runner_uses_clean_directory_pure_mode_and_validates_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    event = json.dumps({"type": "text", "part": {"text": '{"summary":"review"}'}})
    run = Mock(return_value=CompletedProcess([], 0, event))
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    result = ai_runner.analyze("untrusted data", "trusted prompt", "key")
    assert result.summary == "review"
    assert "--pure" in run.call_args.args[0]
    assert run.call_args.kwargs["timeout"] == 300
    assert "GH_TOKEN" not in run.call_args.kwargs["env"]


@pytest.mark.parametrize("has_key", [False, True])
def test_runner_cli_skips_or_writes_validated_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_key: bool
) -> None:
    context = tmp_path / "context.md"
    prompt = tmp_path / "prompt.md"
    output = tmp_path / "analysis.json"
    context.write_text("context")
    prompt.write_text("prompt")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "--context",
            str(context),
            "--prompt",
            str(prompt),
            "--output",
            str(output),
        ],
    )
    monkeypatch.setenv("AI_API_KEY", "test-key" if has_key else "")
    monkeypatch.setattr(
        ai_runner, "analyze", Mock(return_value=Analysis(summary="valid"))
    )
    ai_runner.main()
    if has_key:
        assert json.loads(output.read_text())["summary"] == "valid"
    else:
        assert "skipped" in output.read_text()


def test_invalid_tool_text_retries_without_executing_or_echoing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    invalid = json.dumps(
        {"type": "text", "part": {"text": "<tool_call>secret</tool_call>"}}
    )
    valid = json.dumps({"type": "text", "part": {"text": '{"summary":"valid"}'}})
    run = Mock(
        side_effect=[CompletedProcess([], 0, invalid), CompletedProcess([], 0, valid)]
    )
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    assert ai_runner.analyze("context", "prompt", "key").summary == "valid"
    assert run.call_count == 2
    assert "secret" not in run.call_args.args[0][-1]


def test_exhausted_analysis_fails_without_provider_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    run = Mock(return_value=CompletedProcess([], 0, "private invalid output"))
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    with pytest.raises(ai_runner.AnalysisUnavailableError) as error:
        ai_runner.analyze("context", "prompt", "key")
    assert run.call_count == 3
    assert "private" not in str(error.value)
