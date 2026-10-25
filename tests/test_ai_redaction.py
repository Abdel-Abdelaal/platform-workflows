import json
import subprocess
from unittest.mock import Mock

import pytest

from tools import ai_redaction, ai_runner, ai_telemetry


@pytest.mark.parametrize("escaped", [False, True])
@pytest.mark.parametrize("fenced", [False, True])
def test_nested_event_text_redacts_decoded_credentials_without_losing_usage(
    escaped: bool,
    fenced: bool,
) -> None:
    key = "test-provider-credential"
    analysis = json.dumps({"summary": key, "patch": key})
    if escaped:
        analysis = analysis.replace("test-", r"\u0074est-")
    if fenced:
        analysis = "```json\n" + analysis + "\n```"
    events = "\n".join(
        [
            json.dumps({"type": "text", "part": {"text": analysis}}),
            json.dumps({"type": "step_finish", "part": {"tokens": {"input": 123}}}),
        ]
    )
    scrubbed = ai_redaction.redact_events(events, key)
    output = ai_runner.parse_analysis(ai_runner.extract_text(scrubbed))
    assert output.summary == ai_redaction.REDACTED
    assert output.patch == ai_redaction.REDACTED
    assert json.loads(scrubbed.splitlines()[1])["part"]["tokens"]["input"] == 123
    assert key not in scrubbed


def test_unstructured_failure_and_empty_key() -> None:
    assert (
        ai_redaction.redact_events("provider-secret", "provider-secret")
        == ai_redaction.REDACTED
    )
    assert ai_redaction.redact_events("unchanged", "") == "unchanged"


@pytest.mark.parametrize("failure", [False, True])
def test_runner_redacts_before_validated_output_and_attempt_recording(
    monkeypatch: pytest.MonkeyPatch, failure: bool
) -> None:
    key = "test-provider-credential"
    event = json.dumps({"type": "text", "part": {"text": json.dumps({"summary": key})}})
    result = subprocess.CompletedProcess([], 0, event)
    run = (
        Mock(
            side_effect=[
                subprocess.CalledProcessError(1, "opencode", output=event),
                result,
            ]
        )
        if failure
        else Mock(return_value=result)
    )
    monkeypatch.setattr(ai_runner.shutil, "which", Mock(return_value="opencode"))
    monkeypatch.setattr(ai_runner.subprocess, "run", run)
    record = ai_telemetry.new_record("source", "prompt", thinking=True)
    token = ai_telemetry.CURRENT.set(record)
    try:
        result_analysis = ai_runner.analyze("source", "prompt", key)
        ai_telemetry.complete(record, result_analysis, "")
    finally:
        ai_telemetry.CURRENT.reset(token)
    assert result_analysis.summary == ai_redaction.REDACTED
    assert key not in json.dumps(record)
    assert len(record["attempts"]) == (2 if failure else 1)
