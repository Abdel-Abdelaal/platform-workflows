import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from tools import ai_output_scan as scanner
from tools import ai_runner, ai_telemetry


def report_stub(matches: object, status: int = 0) -> Mock:
    def run(command: list[str], **options: Any) -> subprocess.CompletedProcess[bytes]:
        report = Path(command[command.index("--report-path") + 1])
        assert report.parent.name.startswith("ai-output-scan-")
        assert options["cwd"] == str(report.parent)
        assert options["capture_output"] is True
        assert options["timeout"] == 30
        assert "AI_API_KEY" not in options["env"]
        assert "GH_TOKEN" not in options["env"]
        assert "GITLEAKS_CONFIG" not in options["env"]
        report.write_text(json.dumps(matches), encoding="utf-8")
        return subprocess.CompletedProcess(command, status, b"", b"")

    return Mock(side_effect=run)


@pytest.mark.parametrize("escaped", [True, False])
@pytest.mark.parametrize("fenced", [True, False])
def test_scanning_decodes_nested_json_and_preserves_usage(
    monkeypatch: pytest.MonkeyPatch,
    escaped: bool,
    fenced: bool,
) -> None:
    sample = "not-for-publication"
    payload = json.dumps({"summary": sample})
    if escaped:
        payload = payload.replace("not-", r"\u006eot-")
    if fenced:
        payload = "```json\n" + payload + "\n```"
    events = "\n".join(
        [
            json.dumps({"type": "text", "part": {"text": payload}}),
            json.dumps({"type": "step_finish", "part": {"tokens": {"input": 17}}}),
        ]
    )
    run = report_stub([{"Secret": sample}], 1)
    monkeypatch.setattr(scanner.subprocess, "run", run)
    cleaned, count = scanner.scan_events(events, Path("/trusted/gitleaks"))
    assert count == 1
    assert sample in run.call_args.kwargs["input"].decode()
    assert (
        ai_runner.parse_analysis(ai_runner.extract_text(cleaned)).summary
        == scanner.REDACTED
    )
    assert json.loads(cleaned.splitlines()[1])["part"]["tokens"]["input"] == 17
    assert sample not in cleaned


def test_clean_text_and_failure_text(monkeypatch: pytest.MonkeyPatch) -> None:
    run = report_stub([])
    monkeypatch.setattr(scanner.subprocess, "run", run)
    assert scanner.scan_events("plain diagnostic", Path("/scanner")) == (
        "plain diagnostic",
        0,
    )
    run = report_stub([{"Secret": "sensitive-text"}], 1)
    monkeypatch.setattr(scanner.subprocess, "run", run)
    assert scanner.scan_events("token=sensitive-text", Path("/scanner")) == (
        "token=" + scanner.REDACTED,
        1,
    )
    escaped = r"failed: token=\u0073ensitive-text"
    cleaned, count = scanner.scan_events(escaped, Path("/scanner"))
    assert count == 1
    assert r"\u0073ensitive-text" not in cleaned
    assert scanner.REDACTED in cleaned


BAD_REPORTS: list[tuple[object, int]] = [
    ({}, 0),
    (["invalid"], 1),
    ([{}], 1),
    ([{"Secret": ""}], 1),
    ([{"Secret": True}], 1),
    ([], 1),
    ([{"Secret": "secret"}], 0),
    ([], 2),
]


@pytest.mark.parametrize(("matches", "status"), BAD_REPORTS)
def test_malformed_or_inconsistent_reports_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    matches: object,
    status: int,
) -> None:
    monkeypatch.setattr(scanner.subprocess, "run", report_stub(matches, status))
    with pytest.raises(scanner.OutputScanError):
        scanner.scan_events("untrusted data", Path("/scanner"))


def test_bounded_inputs_reports_and_nested_structures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scanner, "MAX_EVENTS_BYTES", 16)
    with pytest.raises(scanner.OutputScanError):
        scanner.scan_events("x" * 17, Path("/scanner"))
    with pytest.raises(scanner.OutputScanError):
        scanner.scan_events(
            "x" * 14, Path("/scanner")
        )  # canonical wrapper exceeds bound
    assert scanner.scan_events("", Path("/scanner")) == ("", 0)
    monkeypatch.setattr(scanner, "MAX_EVENTS_BYTES", 10000)
    monkeypatch.setattr(scanner, "MAX_REPORT_BYTES", 1)
    monkeypatch.setattr(scanner.subprocess, "run", report_stub([]))
    with pytest.raises(scanner.OutputScanError):
        scanner.scan_events("data", Path("/scanner"))
    with pytest.raises(scanner.OutputScanError):
        scanner.decoded("text", depth=scanner.MAX_STRUCTURE_DEPTH + 1)
    assert scanner.decoded("[1,2]") == [1, 2]
    nested = "ordinary text"
    for _ in range(scanner.MAX_JSON_LAYERS + 1):
        nested = json.dumps(nested)
    with pytest.raises(scanner.OutputScanError):
        scanner.decoded(nested)
    monkeypatch.setattr(scanner, "MAX_SECRET_VALUES", 1)
    with pytest.raises(scanner.OutputScanError):
        scanner.secret_values([{"Secret": "one"}, {"Secret": "two"}], 1)
    monkeypatch.setattr(scanner, "MAX_SECRET_BYTES", 4)
    with pytest.raises(scanner.OutputScanError):
        scanner.secret_values([{"Secret": "oversized"}], 1)


def test_scanner_process_failure_withholds_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-github-credential")
    monkeypatch.setenv("AI_API_KEY", "test-provider-credential")
    monkeypatch.setenv("GITLEAKS_CONFIG", "untrusted-config")
    error = subprocess.TimeoutExpired("scanner", 30, output="sensitive diagnostic")
    monkeypatch.setattr(scanner.subprocess, "run", Mock(side_effect=error))
    with pytest.raises(scanner.OutputScanError) as captured:
        scanner.scan_events("data", Path("/scanner"))
    assert not captured.value.args
    assert not capsys.readouterr().out


def test_explicit_scanner_path_is_required_when_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_OUTPUT_SECRET_SCANNER", raising=False)
    assert scanner.scanner_path() is None
    for setting in ("relative/scanner", str(tmp_path / "missing")):
        monkeypatch.setenv("AI_OUTPUT_SECRET_SCANNER", setting)
        with pytest.raises(scanner.OutputScanError):
            scanner.scanner_path()
    executable = tmp_path / "scanner"
    executable.write_text("test fixture")
    monkeypatch.setenv("AI_OUTPUT_SECRET_SCANNER", str(executable))
    assert scanner.scanner_path() == executable


def setup_runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    executable = tmp_path / "scanner"
    executable.write_text("fixture")
    monkeypatch.setenv("AI_OUTPUT_SECRET_SCANNER", str(executable))
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    return ai_telemetry.new_record("context", "prompt", thinking=True)


def test_missing_scanner_stops_before_any_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = setup_runner(tmp_path, monkeypatch)
    monkeypatch.setenv("AI_OUTPUT_SECRET_SCANNER", str(tmp_path / "absent"))
    run = Mock()
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    token = ai_telemetry.CURRENT.set(record)
    try:
        with pytest.raises(ai_runner.AnalysisUnavailableError):
            ai_runner.analyze("context", "prompt", "key")
    finally:
        ai_telemetry.CURRENT.reset(token)
    run.assert_not_called()
    assert record["evidence_gap"] is True


@pytest.mark.parametrize("process_failure", [False, True])
def test_unavailable_output_scan_records_gap_without_retrying_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    process_failure: bool,
) -> None:
    record = setup_runner(tmp_path, monkeypatch)
    event = json.dumps(
        {"type": "text", "part": {"text": '{"summary":"sensitive text"}'}}
    )
    run = (
        Mock(side_effect=subprocess.CalledProcessError(1, "opencode", output=event))
        if process_failure
        else Mock(return_value=subprocess.CompletedProcess([], 0, event))
    )
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    monkeypatch.setattr(
        ai_runner, "scan_events", Mock(side_effect=scanner.OutputScanError)
    )
    token = ai_telemetry.CURRENT.set(record)
    try:
        with pytest.raises(ai_runner.AnalysisUnavailableError):
            ai_runner.analyze("context", "prompt", "key")
    finally:
        ai_telemetry.CURRENT.reset(token)
    assert run.call_count == 1
    assert len(record["attempts"]) == 1
    assert record["attempts"][0]["response"] == ""
    assert record["attempts"][0]["exit_category"] == "OutputScanError"
    assert "sensitive text" not in json.dumps(record)


@pytest.mark.parametrize("patch", [False, True])
def test_matched_secrets_are_removed_before_output_and_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    patch: bool,
) -> None:
    record = setup_runner(tmp_path, monkeypatch)
    analysis = {
        "summary": "provider-key",
        "patch": "token=other-secret" if patch else "",
    }
    raw = json.dumps({"type": "text", "part": {"text": json.dumps(analysis)}})
    cleaned = raw.replace("other-secret", scanner.REDACTED)
    run = Mock(return_value=subprocess.CompletedProcess([], 0, raw))

    def scan(data: str, _path: Path, *, context: str = "") -> tuple[str, int]:
        assert context == "context"
        assert "provider-key" not in data
        return cleaned.replace("provider-key", "redacted"), 1

    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    monkeypatch.setattr(ai_runner, "scan_events", scan)
    token = ai_telemetry.CURRENT.set(record)
    try:
        if patch:
            with pytest.raises(ai_runner.AnalysisUnavailableError):
                ai_runner.analyze("context", "prompt", "provider-key")
        else:
            assert (
                ai_runner.analyze("context", "prompt", "provider-key").summary
                == "redacted"
            )
    finally:
        ai_telemetry.CURRENT.reset(token)
    assert "other-secret" not in json.dumps(record)
    assert all(attempt["secret_values_redacted"] == 1 for attempt in record["attempts"])
    assert run.call_count == (3 if patch else 1)


@pytest.mark.parametrize("process_failure", [False, True])
def test_context_secrets_are_removed_from_bare_output_and_failure_telemetry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    process_failure: bool,
) -> None:
    record = setup_runner(tmp_path, monkeypatch)
    sample = "context-only-sensitive-value"
    context = 'API_TOKEN = "' + sample + '"'
    event = json.dumps(
        {"type": "text", "part": {"text": json.dumps({"summary": sample})}}
    )
    provider = (
        Mock(side_effect=subprocess.TimeoutExpired("opencode", 600, output=event))
        if process_failure
        else Mock(return_value=subprocess.CompletedProcess([], 0, event))
    )
    scan = report_stub([{"Secret": sample}], 1)

    def run(command: list[str], **options: Any) -> Any:
        if "--report-path" in command:
            return scan(command, **options)
        return provider(command, **options)

    monkeypatch.setattr(scanner.subprocess, "run", run)
    token = ai_telemetry.CURRENT.set(record)
    try:
        if process_failure:
            with pytest.raises(ai_runner.AnalysisUnavailableError):
                ai_runner.analyze(context, "prompt", "provider-key")
        else:
            assert (
                ai_runner.analyze(context, "prompt", "provider-key").summary
                == scanner.REDACTED
            )
    finally:
        ai_telemetry.CURRENT.reset(token)
    assert context in scan.call_args.kwargs["input"].decode()
    assert sample not in json.dumps(record)
    assert all(attempt["secret_values_redacted"] == 1 for attempt in record["attempts"])


def test_context_only_matches_do_not_inflate_output_redaction_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan = report_stub([{"Secret": "context-sensitive-value"}], 1)
    monkeypatch.setattr(scanner.subprocess, "run", scan)
    assert scanner.scan_events(
        "safe response", Path("/scanner"), context="context-sensitive-value"
    ) == ("safe response", 0)
    monkeypatch.setattr(scanner, "MAX_EVENTS_BYTES", 16)
    with pytest.raises(scanner.OutputScanError):
        scanner.scan_events("safe", Path("/scanner"), context="c" * 16)
