"""Finalize AI evidence for signing and archive it without executing source."""

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from tools.ai_telemetry import mapping, new_record, save, timestamp


class AttemptEnvelope(BaseModel):
    """Validate the execution fields the finalizer and aggregator consume."""

    attributes: dict[str, int]
    duration_seconds: float = Field(ge=0)
    exit_category: str


class RecordEnvelope(BaseModel):
    """Validate required v1 evidence without interpreting the model's text."""

    schema_version: Literal[1]
    record_id: str = Field(min_length=1)
    identity: dict[str, str]
    attempts: list[AttemptEnvelope]
    status: Literal["valid", "no_valid_output", "skipped"]


def incoming_record(source: Path) -> dict[str, Any] | None:
    """Convert missing, malformed or partial evidence into an explicit gap."""
    try:
        text = source.read_text(encoding="utf-8")
        RecordEnvelope.model_validate_json(text, strict=True)
    except (OSError, UnicodeError, ValidationError):
        return None
    return mapping(json.loads(text))


class ReceiptEnvelope(BaseModel):
    """Require a status before treating publisher evidence as a receipt."""

    status: str = Field(min_length=1)


def read_receipts(directory: Path) -> tuple[list[dict[str, Any]], int]:
    """Retain valid receipts while counting damaged publication evidence."""
    receipts: list[dict[str, Any]] = []
    invalid = 0
    for path in sorted(directory.glob("**/publication.json")):
        try:
            text = path.read_text(encoding="utf-8")
            ReceiptEnvelope.model_validate_json(text, strict=True)
        except (OSError, UnicodeError, ValidationError):
            invalid += 1
        else:
            receipts.append(mapping(json.loads(text)))
    return receipts, invalid


def finalize(directory: Path, destination: Path) -> None:
    """Join analysis and publication evidence, explicitly representing gaps."""
    source = directory / "ai-record.json"
    record = incoming_record(source)
    if record is None:
        record = new_record("", "", thinking=os.environ.get("MODE") == "review")
        record["status"] = (
            "skipped"
            if os.environ.get("ANALYZE_RESULT") == "success"
            else "no_valid_output"
        )
        record["skip_reason"] = (
            "required credentials unavailable"
            if record["status"] == "skipped"
            else "analysis job failed before record upload"
        )
        record["configuration"] = {"available": False}
        if source.exists():
            record.update(
                status="no_valid_output", skip_reason="invalid incoming evidence"
            )
        record["evidence_gap"] = True
    record["job_results"] = mapping(json.loads(os.environ.get("JOB_RESULTS", "{}")))
    record["finalized_at"] = timestamp()
    receipts, invalid = read_receipts(directory)
    record["publication"] = receipts
    record["invalid_publication_receipts"] = invalid
    if not receipts:
        record["publication"] = [
            {"status": "not_published", "reason": "see job_results"}
        ]
    record["storage"] = {
        "backend": "github-release-assets",
        "retention": "until explicitly deleted",
    }
    save(record, destination)
    predicate = {
        "schema_version": 1,
        "record_id": record["record_id"],
        "status": record["status"],
        "identity": record["identity"],
    }
    destination.with_name("predicate.json").write_text(
        json.dumps(predicate), encoding="utf-8"
    )


def gh(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    """Keep credentials in the trusted CLI environment, never arguments or logs."""
    return subprocess.run(
        ["gh", *arguments],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )


def archive(record: Path, bundle: Path, directory: Path) -> None:
    """Append unique record/bundle assets to a monthly prerelease; never replace."""
    repository = os.environ["GITHUB_REPOSITORY"]
    run_id = os.environ["GITHUB_RUN_ID"]
    attempt = os.environ["GITHUB_RUN_ATTEMPT"]
    mode = os.environ["MODE"]
    if not re.fullmatch(r"[0-9]+", run_id + attempt) or mode not in {
        "review",
        "audit",
        "fix",
        "standards",
    }:
        msg = "invalid archive identity"
        raise ValueError(msg)
    tag = "ai-telemetry-" + timestamp()[:7]
    stem = f"ai-{run_id}-{attempt}-{mode}"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (stem + ".json")
    signature = directory / (stem + ".sigstore.json")
    shutil.copyfile(record, target)
    shutil.copyfile(bundle, signature)
    if gh(["release", "view", tag, "--repo", repository]).returncode:
        created = gh(
            [
                "release",
                "create",
                tag,
                "--repo",
                repository,
                "--prerelease",
                "--latest=false",
                "--title",
                "AI telemetry " + tag.removeprefix("ai-telemetry-"),
                "--notes",
                "Secret-scanned AI records and Sigstore bundles. "
                "See platform-workflows/docs/ai-telemetry.md.",
            ]
        )
        # Another mode may have created the same monthly release concurrently.
        if (
            created.returncode
            and gh(["release", "view", tag, "--repo", repository]).returncode
        ):
            msg = "telemetry release creation failed; CLI output withheld"
            raise RuntimeError(msg)
    uploaded = gh(
        ["release", "upload", tag, str(target), str(signature), "--repo", repository]
    )
    if uploaded.returncode:
        msg = "telemetry archive upload failed; CLI output withheld"
        raise RuntimeError(msg)


def main() -> None:
    """Separate finalization (before scanning/signing) from durable upload."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["finalize", "archive"])
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    args = parser.parse_args()
    if args.command == "finalize":
        finalize(args.directory, args.record)
    elif args.bundle:
        archive(args.record, args.bundle, args.directory)
    else:
        parser.error("archive requires --bundle")


if __name__ == "__main__":
    main()
