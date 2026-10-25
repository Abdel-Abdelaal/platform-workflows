import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from tools import ai_context, ai_runner, ai_telemetry
from tools.ai_contract import Analysis, InlineFinding, parse_analysis


def event(kind: str, part: dict[str, object]) -> str:
    return json.dumps({"type": kind, "part": part})


def test_step_totals_keep_reasoning_and_cache_without_inventing_missing_usage():
    events = "\n".join(
        [
            "broken transport line",
            event(
                "step_finish",
                {
                    "tokens": {
                        "input": 10,
                        "output": 4,
                        "reasoning": 3,
                        "cache": {"read": 7, "write": 2},
                    },
                    "reason": "stop",
                },
            ),
            event("step_finish", {"tokens": {"input": 2, "output": 1}}),
        ]
    )
    result = ai_telemetry.event_usage(events)
    assert result["attributes"]["gen_ai.usage.input_tokens"] == 21
    assert result["attributes"]["gen_ai.usage.output_tokens"] == 8
    assert result["gen_ai.response.finish_reasons"] == ["stop"]
    assert ai_telemetry.event_usage("")["attributes"] == {}


def test_record_allowlist_never_copies_credentials_or_url_password(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("AI_API_KEY", "secret")
    monkeypatch.setenv("GH_TOKEN", "secret")
    monkeypatch.setenv(
        "AI_BASE_URL", "https://user:secret@provider.example/v1?key=secret"
    )
    record = ai_telemetry.new_record("public context", "prompt", thinking=False)
    assert "secret" not in json.dumps(record)
    assert record["attributes"]["server.address"] == "provider.example"
    assert record["configuration"]["context_sha256"] == ai_telemetry.digest(
        "public context"
    )


def test_failed_output_is_data_validation_errors_exclude_offending_value(
    tmp_path: Path,
):
    record = ai_telemetry.new_record("context", "prompt", thinking=True)
    token = ai_telemetry.CURRENT.set(record)
    try:
        with pytest.raises(ValidationError) as error:
            parse_analysis('{"summary":"ok","unexpected":"private"}')
        ai_telemetry.record_attempt(
            event("text", {"text": "untrusted response"}), 1.2, error.value
        )
    finally:
        ai_telemetry.CURRENT.reset(token)
    path = tmp_path / "ai-record.json"
    ai_telemetry.save(record, path)
    saved = json.loads(path.read_text())
    assert "private" not in json.dumps(saved)
    assert saved["attempts"][0]["validation_errors"] == [
        {"type": "extra_forbidden", "loc": ["unexpected"]}
    ]
    assert saved["attempts"][0]["response"] == "untrusted response"


def test_filtering_and_patch_rejection_are_distinct_from_publication():
    record = ai_telemetry.new_record("context", "prompt", thinking=True)
    analysis = Analysis(
        summary="ok",
        comments=[InlineFinding(path="x.py", line=7, body="finding")],
        patch="diff --git a/.github/workflows/a.yml b/.github/workflows/a.yml",
    )
    ai_telemetry.complete(record, analysis, "")
    assert record["findings"]["proposed"] == 1
    assert record["findings"]["eligible"] == 0
    assert record["patch_check"]["status"] == "rejected"
    assert "publication" not in record


@pytest.mark.parametrize("failure", ["invalid", "timeout", "process"])
def test_exhausted_cli_writes_evidence_without_echoing_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: str,
):
    context = tmp_path / "context.md"
    prompt = tmp_path / "prompt.md"
    context.write_text("context")
    prompt.write_text("trusted prompt")
    record = tmp_path / "ai-record.json"
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
            str(tmp_path / "output.json"),
            "--record",
            str(record),
        ],
    )
    monkeypatch.setenv("AI_API_KEY", "secret")
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    output = event("text", {"text": "private model response"})
    run = Mock(return_value=subprocess.CompletedProcess([], 0, output))
    if failure == "timeout":
        run = Mock(
            side_effect=subprocess.TimeoutExpired("opencode", 600, output=output)
        )
    if failure == "process":
        run = Mock(
            side_effect=subprocess.CalledProcessError(1, "opencode", output=output)
        )
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    with pytest.raises(ai_runner.AnalysisUnavailableError):
        ai_runner.main()
    saved = json.loads(record.read_text())
    assert saved["status"] == "no_valid_output"
    assert len(saved["attempts"]) == 3
    assert saved["attempts"][0]["response"] == "private model response"
    assert "private model" not in capsys.readouterr().err
    assert ai_telemetry.CURRENT.get() is None


@pytest.mark.parametrize(
    "payload", [None, "{", "[]", '[{"path":"a.py","status":"included"}]']
)
@pytest.mark.parametrize("has_key", [False, True])
def test_cli_manifest_diff_and_skip_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str | None, has_key: bool
) -> None:
    context = tmp_path / "context.md"
    context.write_text(
        "--- UNTRUSTED SOURCE: a.py ---\n[FILE TRUNCATED]\n--- END SOURCE ---"
    )
    prompt = tmp_path / "prompt.md"
    prompt.write_text("prompt")
    manifest = tmp_path / "manifest.json"
    if payload is not None:
        manifest.write_text(payload)
    diff = tmp_path / "pr.diff"
    diff.write_text("diff data")
    output = tmp_path / "record.json"
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
            str(tmp_path / "analysis.json"),
            "--record",
            str(output),
            "--manifest",
            str(manifest),
            "--diff",
            str(diff),
        ],
    )
    monkeypatch.setenv("AI_API_KEY", "key" if has_key else "")
    monkeypatch.setattr(
        ai_runner, "analyze", Mock(return_value=Analysis(summary="valid"))
    )
    ai_runner.main()
    saved = json.loads(output.read_text())
    assert saved["status"] == ("valid" if has_key else "skipped")
    assert saved["configuration"]["manifest_complete"] is (
        payload in ("[]", '[{"path":"a.py","status":"included"}]')
    )
    assert saved["configuration"]["diff_sha256"] == ai_telemetry.digest("diff data")
    if payload in (None, "{"):
        assert saved["context_manifest"][0]["status"] == "present_in_context"


def test_manifest_tracks_actual_truncation_omission_and_handbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    (repository / "src").mkdir(parents=True)
    for name in ("a.py", "b.py"):
        (repository / "src" / name).write_text("x" * 80)
    handbook = tmp_path / "handbook"
    (handbook / "standards").mkdir(parents=True)
    (handbook / "standards" / "ai.md").write_text("public standard")
    monkeypatch.setattr(ai_context, "MAX_FILE_CHARACTERS", 50)
    monkeypatch.setattr(ai_context, "MAX_CONTEXT_CHARACTERS", 180)
    monkeypatch.setattr(
        ai_context.subprocess,
        "run",
        Mock(
            side_effect=[
                subprocess.CompletedProcess([], 0, "src/a.py\0src/b.py\0"),
                subprocess.CompletedProcess([], 0, "standards/ai.md\0"),
            ]
        ),
    )
    manifest: list[dict[str, str]] = []
    ai_context.snapshot(repository, manifest=manifest)
    ai_context.snapshot(handbook, prefix="standards/", manifest=manifest)
    assert manifest == [
        {"path": "src/a.py", "status": "truncated", "source": "repository"},
        {"path": "src/b.py", "status": "omitted", "source": "repository"},
        {"path": "standards/ai.md", "status": "included", "source": "handbook"},
    ]
