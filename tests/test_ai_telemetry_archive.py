import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import ai_telemetry
from tools import ai_telemetry_archive as archive


@pytest.mark.parametrize("has_record", [False, True])
@pytest.mark.parametrize("result", ["success", "failure"])
def test_finalize_preserves_analysis_time_and_joins_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, has_record: bool, result: str
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    monkeypatch.setenv("ANALYZE_RESULT", result)
    monkeypatch.setenv("JOB_RESULTS", '{"analyze":{"result":"failure"}}')
    if has_record:
        record = ai_telemetry.new_record("source", "prompt", thinking=True)
        record["ended_at"] = "2026-10-01T00:00:00+00:00"
        ai_telemetry.save(record, incoming / "ai-record.json")
        (incoming / "publication.json").write_text(
            '{"status":"published","comment":{"id":7}}'
        )
    output = tmp_path / "final.json"
    archive.finalize(incoming, output)
    saved = json.loads(output.read_text())
    predicate = json.loads((tmp_path / "predicate.json").read_text())
    assert predicate["record_id"] == saved["record_id"]
    assert saved["job_results"]["analyze"]["result"] == "failure"
    if has_record:
        assert saved["ended_at"] == "2026-10-01T00:00:00+00:00"
        assert saved["publication"][0]["comment"]["id"] == 7
    else:
        assert saved["status"] == (
            "skipped" if result == "success" else "no_valid_output"
        )
        assert saved["publication"][0]["status"] == "not_published"


@pytest.mark.parametrize("codes", [[0, 0], [1, 0, 0], [1, 1, 0, 0], [1, 1, 1], [0, 1]])
def test_release_archive_never_overwrites_assets_and_handles_creation_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, codes: list[int]
) -> None:
    for name, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "2",
        "MODE": "audit",
    }.items():
        monkeypatch.setenv(name, value)
    record = tmp_path / "record.json"
    bundle = tmp_path / "bundle.json"
    record.write_text('{"untrusted":"$(execute nothing)"}')
    bundle.write_text("signed bundle")
    cli = Mock(
        side_effect=[subprocess.CompletedProcess([], code, "") for code in codes]
    )
    monkeypatch.setattr(archive, "gh", cli)
    if codes in ([1, 1, 1], [0, 1]):
        with pytest.raises(RuntimeError, match="withheld"):
            archive.archive(record, bundle, tmp_path / "archive")
    else:
        archive.archive(record, bundle, tmp_path / "archive")
    assert all("--clobber" not in call.args[0] for call in cli.call_args_list)
    assert (
        tmp_path / "archive" / "ai-123-2-audit.json"
    ).read_bytes() == record.read_bytes()


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_private_signature_storage_has_explicit_visibility_and_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, visibility: str
) -> None:
    for name, value in {
        "GITHUB_REPOSITORY": "owner/repository",
        "GITHUB_RUN_ID": "123",
        "GITHUB_RUN_ATTEMPT": "1",
        "MODE": "audit",
        "REPOSITORY_VISIBILITY": visibility,
    }.items():
        monkeypatch.setenv(name, value)
    record = tmp_path / "record.json"
    bundle = tmp_path / "bundle.json"
    record.write_text("{}")
    bundle.write_text("{}")
    cli = Mock(return_value=subprocess.CompletedProcess([], 0, ""))
    monkeypatch.setattr(archive, "gh", cli)
    if visibility == "public":
        with pytest.raises(ValueError, match="private repository"):
            archive.archive(
                record, bundle, tmp_path / "archive", signature_format="dsse"
            )
        assert not cli.called
    else:
        archive.archive(record, bundle, tmp_path / "archive", signature_format="dsse")
        assert (tmp_path / "archive/ai-123-1-audit.dsse.json").exists()
        assert not (tmp_path / "archive/ai-123-1-audit.sigstore.json").exists()
    with pytest.raises(ValueError, match="unsupported"):
        archive.archive(record, bundle, tmp_path / "other", signature_format="unknown")


def test_archive_rejects_invalid_identity_before_any_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in {
        "GITHUB_REPOSITORY": "owner/repo",
        "GITHUB_RUN_ID": "../bad",
        "GITHUB_RUN_ATTEMPT": "2",
        "MODE": "review",
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match="identity"):
        archive.archive(tmp_path, tmp_path, tmp_path)


def test_cli_helper_captures_output_without_shell(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = Mock(return_value=subprocess.CompletedProcess([], 0, ""))
    monkeypatch.setattr(archive.subprocess, "run", run)
    archive.gh(["release", "view", "tag"])
    assert run.call_args.args[0] == ["gh", "release", "view", "tag"]
    assert "shell" not in run.call_args.kwargs
    assert run.call_args.kwargs["encoding"] == "utf-8"


@pytest.mark.parametrize("command", ["finalize", "archive", "missing_bundle"])
def test_archive_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    args = [
        "tool",
        "finalize" if command == "finalize" else "archive",
        "--directory",
        str(tmp_path),
        "--record",
        str(tmp_path / "record.json"),
    ]
    if command == "archive":
        args.extend(["--bundle", str(tmp_path / "bundle.json")])
    monkeypatch.setattr(sys, "argv", args)
    finalize = Mock()
    upload = Mock()
    monkeypatch.setattr(archive, "finalize", finalize)
    monkeypatch.setattr(archive, "archive", upload)
    if command == "missing_bundle":
        with pytest.raises(SystemExit):
            archive.main()
    else:
        archive.main()
        assert (finalize if command == "finalize" else upload).call_count == 1


@pytest.mark.parametrize("payload", ["{", "[]", "{}", '{"attempts":[{}]}'])
def test_invalid_incoming_evidence_becomes_a_signed_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, payload: str
) -> None:
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    (incoming / "ai-record.json").write_text(payload)
    monkeypatch.setenv("ANALYZE_RESULT", "success")
    output = tmp_path / "record.json"
    archive.finalize(incoming, output)
    saved = json.loads(output.read_text())
    assert saved["evidence_gap"] is True
    assert saved["status"] == "no_valid_output"
    assert saved["skip_reason"] == "invalid incoming evidence"


def test_damaged_receipt_does_not_prevent_record_finalization(tmp_path: Path) -> None:
    (tmp_path / "publication.json").write_text("{")
    archive.finalize(tmp_path, tmp_path / "record.json")
    saved = json.loads((tmp_path / "record.json").read_text())
    assert saved["invalid_publication_receipts"] == 1
    assert saved["publication"][0]["status"] == "not_published"
