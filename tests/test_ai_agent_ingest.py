"""Agent ingestion privacy, redaction, provenance and delivery boundaries."""

import hashlib
import io
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError

from tools import ai_agent_excerpt as excerpt
from tools import ai_agent_ingest as ingest
from tools.ai_agent_schema import AgentAttempt, AgentEvidenceError, batch, canonical
from tools.ai_output_scan import OutputScanError

REPO = "Abdel-Abdelaal/shortlink"


def attempt(**changes: object) -> dict[str, object]:
    return {
        "schema": "agent-dispatcher.attempt/v1",
        "record_id": str(uuid4()),
        "recorded_at": "2026-10-26T08:00:00+00:00",
        "repo": REPO,
        "stage": "implement",
        "run_id": 7,
        "attempt": 2,
        "issue": 36,
        "prompt_sha256": "a" * 64,
        "output_sha256": "b" * 64,
        "output_excerpt": "bounded reply",
        "context_sha256": {"issue": "c" * 64},
        **changes,
    }


def public(repository: str) -> dict[str, object]:
    return {
        "full_name": repository,
        "visibility": "public",
        "private": False,
        "fork": False,
        "archived": False,
    }


def scanner(monkeypatch: pytest.MonkeyPatch) -> Mock:
    monkeypatch.setattr(
        ingest, "scanner_path", Mock(return_value=Path("/verified/gitleaks"))
    )

    def clean(text: str, _binary: Path) -> tuple[str, int]:
        return text, 0

    scan = Mock(side_effect=clean)
    monkeypatch.setattr(ingest, "scan_events", scan)
    return scan


def source_file(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    source = tmp_path / "attempts.jsonl"
    source.write_text("".join(canonical(r) + "\n" for r in records), encoding="utf-8")
    return source


def test_allowlist_drops_unknown_secrets_and_preserves_unknown_usage() -> None:
    record = AgentAttempt.model_validate(attempt(environment={"TOKEN": "private"}))
    data = record.model_dump(by_alias=True)
    assert "environment" not in data
    assert data["usage"] is None
    assert data["available_usage"] is None
    assert "private" not in canonical(batch([record]))


def test_producer_privacy_metadata_and_omitted_excerpt_are_preserved() -> None:
    record = AgentAttempt.model_validate(
        attempt(
            schema_version=1,
            controller_revision="a" * 40,
            output_excerpt=None,
            excerpt_status="omitted_no_scanner",
            excerpt_truncated=True,
        )
    )
    data = record.model_dump(by_alias=True)
    assert data["output_excerpt"] is None
    assert data["excerpt_status"] == "omitted_no_scanner"
    assert data["excerpt_truncated"] is True
    assert data["controller_revision"] == "a" * 40
    assert AgentAttempt.model_validate(attempt(stage="error")).stage == "error"


def test_excerpt_scrubber_requires_scanner_and_emits_only_clean_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(excerpt, "scanner_path", Mock(return_value=None))
    with pytest.raises(OutputScanError):
        excerpt.scrub("untrusted")
    monkeypatch.setattr(excerpt, "scanner_path", Mock(return_value=Path("/scanner")))
    scan = Mock(return_value=('{"excerpt":"[REDACTED SECRET]"}', 1))
    monkeypatch.setattr(excerpt, "scan_events", scan)
    assert excerpt.scrub("untrusted") == "[REDACTED SECRET]"
    assert json.loads(scan.call_args.args[0]) == {"excerpt": "untrusted"}


def test_excerpt_cli_bounds_stdin_and_withholds_failure_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(excerpt.sys, "stdin", io.TextIOWrapper(io.BytesIO(b"raw")))
    monkeypatch.setattr(excerpt, "scrub", Mock(return_value="safe"))
    excerpt.main()
    assert capsys.readouterr().out == "safe"
    monkeypatch.setattr(
        excerpt.sys,
        "stdin",
        io.TextIOWrapper(io.BytesIO(b"x" * (excerpt.MAX_BYTES + 1))),
    )
    with pytest.raises(SystemExit) as error:
        excerpt.main()
    assert error.value.code == 1
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    "changes",
    [
        {"schema": "unknown"},
        {"repo": "other/private"},
        {"recorded_at": "2026-10-26"},
        {"stage": "shell"},
        {"output_excerpt": "x" * 2001},
        {"context_sha256": {"issue": "raw prompt"}},
        {"usage": {"input_tokens": -1}},
        {"usage": {"unknown": 5}},
        {"usage": {"input_tokens": True}},
        {"available_usage": 0},
    ],
)
def test_invalid_schema_and_invented_usage_fail(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        AgentAttempt.model_validate(attempt(**changes))


def test_batch_is_stable_and_bounded() -> None:
    record = AgentAttempt.model_validate(attempt())
    assert batch([record]) == batch([record])
    with pytest.raises(AgentEvidenceError):
        batch([])
    with pytest.raises(AgentEvidenceError):
        batch([record] * 26)


def test_sender_filters_private_unknown_and_deduplicates_before_upload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanned = scanner(monkeypatch)
    item = attempt()
    hidden = attempt(repo="Abdel-Abdelaal/confidential", output_excerpt="private data")

    def metadata(endpoint: str) -> dict[str, object]:
        return public(REPO) if endpoint.endswith(REPO) else {}

    monkeypatch.setattr(ingest, "github_api", metadata)
    source = source_file(tmp_path, [item, item, hidden])
    output = tmp_path / "out.json"
    assert ingest.prepare(source, output, set()) == [item["record_id"]]
    assert "confidential" not in output.read_text()
    assert "private data" not in output.read_text()
    assert scanned.call_count == 1
    assert ingest.prepare(source, output, {str(item["record_id"])}) == []


def test_redaction_precedes_public_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanner(monkeypatch)
    monkeypatch.setattr(ingest, "public_repository", Mock(return_value=True))

    def redact(text: str, _binary: Path) -> tuple[str, int]:
        return text.replace("sensitive-value", "[REDACTED SECRET]"), 1

    monkeypatch.setattr(ingest, "scan_events", redact)
    source = source_file(tmp_path, [attempt(output_excerpt="sensitive-value")])
    output = tmp_path / "out.json"
    ingest.prepare(source, output, set())
    assert "sensitive-value" not in output.read_text()
    assert "[REDACTED SECRET]" in output.read_text()


def test_missing_scanner_and_cross_repo_join_fail_before_write(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = source_file(
        tmp_path, [attempt(pr_url="https://github.com/Abdel-Abdelaal/private/pull/1")]
    )
    output = tmp_path / "out.json"
    monkeypatch.setattr(ingest, "scanner_path", Mock(return_value=None))
    with pytest.raises(OutputScanError):
        ingest.prepare(source, output, set())
    scanner(monkeypatch)
    monkeypatch.setattr(ingest, "public_repository", Mock(return_value=True))
    with pytest.raises(AgentEvidenceError):
        ingest.prepare(source, output, set())
    assert not output.exists()


def test_hosted_ingest_rechecks_owner_hash_targets_and_scanner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanner(monkeypatch)
    monkeypatch.setattr(ingest, "public_repository", Mock(return_value=True))
    data = canonical(batch([AgentAttempt.model_validate(attempt())])).encode()
    name = "agent-input-" + hashlib.sha256(data).hexdigest() + ".json"
    monkeypatch.setattr(
        ingest,
        "release_assets",
        Mock(
            return_value=[
                {
                    "name": name,
                    "size": len(data),
                    "uploader": {"login": "Abdel-Abdelaal"},
                }
            ]
        ),
    )

    def download(args: list[str]) -> subprocess.CompletedProcess[str]:
        (Path(args[args.index("--dir") + 1]) / name).write_bytes(data)
        return subprocess.CompletedProcess(args, 0, "")

    monkeypatch.setattr(ingest, "gh", download)
    output = tmp_path / "record.json"
    ingest.ingest("ai-agent-incoming-2026-10", name, output)
    assert (
        json.loads(output.read_text())["ingestion"]["controller_execution_provenance"]
        == "not independently attested"
    )
    assert (tmp_path / "predicate.json").exists()
    monkeypatch.setattr(ingest, "public_repository", Mock(return_value=False))
    with pytest.raises(AgentEvidenceError):
        ingest.ingest("ai-agent-incoming-2026-10", name, output)


@pytest.mark.parametrize(
    ("tag", "name"),
    [
        ("arbitrary", "agent-input-" + "a" * 64 + ".json"),
        ("ai-agent-incoming-2026-10", "../../escape"),
    ],
)
def test_untrusted_selectors_never_reach_cli(tag: str, name: str) -> None:
    with pytest.raises(AgentEvidenceError):
        ingest.dispatch(tag, name)


def test_submit_checkpoints_pending_and_requires_verified_delivery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    scanner(monkeypatch)
    monkeypatch.setattr(ingest, "public_repository", Mock(return_value=True))
    monkeypatch.setattr(
        ingest, "github_api", Mock(return_value={"login": "Abdel-Abdelaal"})
    )
    monkeypatch.setattr(ingest, "release", Mock(return_value=None))
    monkeypatch.setattr(ingest, "release_assets", Mock(return_value=[]))
    monkeypatch.setattr(
        ingest, "gh", Mock(return_value=subprocess.CompletedProcess([], 0, ""))
    )
    dispatch = Mock()
    monkeypatch.setattr(ingest, "dispatch", dispatch)
    item = attempt()
    source = source_file(tmp_path, [item])
    ledger = tmp_path / "state.json"
    ingest.submit(source, ledger)
    state = json.loads(ledger.read_text())
    assert state.get("submitted", []) == []
    assert state["pending"]["ids"] == [item["record_id"]]
    monkeypatch.setattr(ingest, "delivered", Mock(return_value=False))
    ingest.submit(source, ledger)
    assert dispatch.call_count == 2
    monkeypatch.setattr(ingest, "delivered", Mock(return_value=True))
    ingest.submit(source, ledger)
    assert json.loads(ledger.read_text())["submitted"] == [item["record_id"]]
    assert dispatch.call_count == 2


def test_delivery_rejects_unsigned_or_invalid_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = "a" * 64
    name = f"agent-batch-{digest}-123.json"
    pending: dict[str, object] = {
        "batch_id": digest,
        "tag": "ai-agent-incoming-2026-10",
    }
    monkeypatch.setattr(ingest, "release_assets", Mock(return_value=[{"name": name}]))
    assert ingest.delivered(pending) is False
    monkeypatch.setattr(
        ingest,
        "release_assets",
        Mock(
            return_value=[
                {"name": name},
                {"name": name[:-5] + ".sigstore.json"},
            ]
        ),
    )

    def fake_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[0] == "release":
            path = (
                Path(args[args.index("--dir") + 1]) / args[args.index("--pattern") + 1]
            )
            path.write_text(canonical({"batch_id": digest}))
        else:
            assert "--source-ref" in args
            assert "--predicate-type" in args
        return subprocess.CompletedProcess(args, 0, "")

    monkeypatch.setattr(ingest, "gh", fake_cli)
    assert ingest.delivered(pending) is True


def test_release_asset_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock(side_effect=[{"id": 1}, [{"name": "item"}] * 100, [{"name": "last"}]])
    monkeypatch.setattr(ingest, "github_api", api)
    assert len(ingest.release_assets("tag")) == 101
    assert "page=2" in api.call_args.args[0]


def test_archive_preserves_source_month_and_never_overwrites(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    record = tmp_path / "record.json"
    bundle = tmp_path / "bundle.json"
    record.write_text(
        canonical(
            {
                "batch_id": "a" * 64,
                "ingestion": {"source_tag": "ai-agent-incoming-2026-09"},
            }
        )
    )
    bundle.write_text("{}")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    release = Mock()
    upload = Mock(return_value=subprocess.CompletedProcess([], 0, ""))
    monkeypatch.setattr(ingest, "release", release)
    monkeypatch.setattr(ingest, "gh", upload)
    ingest.archive(record, bundle, tmp_path / "archive")
    assert release.call_args.args == ("ai-telemetry-2026-09",)
    assert "--clobber" not in upload.call_args.args[0]
    assert len(list((tmp_path / "archive").glob("*.json"))) == 2


def test_sender_rejects_nonowner_before_scanning_or_upload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ingest, "github_api", Mock(return_value={"login": "other"}))
    scan = Mock()
    monkeypatch.setattr(ingest, "prepare", scan)
    with pytest.raises(AgentEvidenceError):
        ingest.submit(tmp_path / "source", tmp_path / "ledger")
    scan.assert_not_called()


def test_failed_cli_diagnostics_are_not_forwarded() -> None:
    with pytest.raises(RuntimeError) as caught:
        ingest.require_success(subprocess.CompletedProcess([], 1, "untrusted payload"))
    assert "untrusted payload" not in str(caught.value)


def test_hosted_workflow_exposes_no_model_or_untrusted_run_source() -> None:
    workflow = yaml.safe_load(Path(".github/workflows/ai-agent-ingest.yml").read_text())
    job = workflow["jobs"]["ingest"]
    assert "refs/heads/main" in job["if"]
    assert workflow["permissions"] == {}
    assert job["permissions"] == {
        "contents": "write",
        "id-token": "write",
        "attestations": "write",
    }
    steps = job["steps"]
    assert steps[0]["uses"].startswith("step-security/harden-runner@")
    for step in steps:
        assert "${{ inputs." not in step.get("run", "")
        assert "AI_API_KEY" not in step.get("env", {})
    assert any("sha256sum --check" in step.get("run", "") for step in steps)
