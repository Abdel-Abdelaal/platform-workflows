"""Scan public controller records before upload and sign hosted ingestion later."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from pydantic import TypeAdapter, ValidationError

from tools.ai_agent_schema import (
    MAX_BATCH_BYTES,
    MAX_BATCH_RECORDS,
    OWNER,
    PREDICATE,
    TRANSPORT_REPOSITORY,
    AgentAttempt,
    AgentEvidenceError,
    batch,
    canonical,
)
from tools.ai_output_scan import OutputScanError, scan_events, scanner_path
from tools.ai_telemetry import mapping, timestamp
from tools.ai_telemetry_archive import gh
from tools.github_api import github_api

PAGE_SIZE = 100


def public_repository(repository: str) -> bool:
    """Only explicit, fresh public metadata permits transmission of this record."""
    data = mapping(github_api(f"repos/{repository}"))
    return (
        data.get("full_name") == repository
        and data.get("private") is False
        and data.get("visibility") == "public"
        and data.get("fork") is False
        and data.get("archived") is False
    )


def prepare(source: Path, output: Path, submitted: set[str]) -> list[str]:
    """Select one bounded public batch, scanning before any GitHub write."""
    scanner = scanner_path()
    if scanner is None:
        raise OutputScanError
    records: list[AgentAttempt] = []
    seen = set(submitted)
    visibility: dict[str, bool] = {}
    with source.open("rb") as stream:
        while True:
            line = stream.readline(MAX_BATCH_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_BATCH_BYTES:
                raise AgentEvidenceError
            record = AgentAttempt.model_validate_json(line)
            if record.record_id in seen:
                continue
            seen.add(record.record_id)
            if record.repo not in visibility:
                visibility[record.repo] = public_repository(record.repo)
            if not visibility[record.repo]:
                continue
            validate_join(record)
            cleaned, _count = scan_events(
                canonical(record.model_dump(by_alias=True)), scanner
            )
            records.append(AgentAttempt.model_validate_json(cleaned))
            if len(records) == MAX_BATCH_RECORDS:
                break
    if not records:
        return []
    document = batch(records)
    output.write_text(canonical(document), encoding="utf-8")
    return [record.record_id for record in records]


def validate_join(record: AgentAttempt) -> None:
    """A public record cannot expose another repository through its PR join."""
    if record.pr_url and not re.fullmatch(
        rf"https://github.com/{re.escape(record.repo)}/pull/[1-9][0-9]*",
        record.pr_url,
    ):
        raise AgentEvidenceError


def require_success(result: subprocess.CompletedProcess[str]) -> str:
    """Never expose CLI diagnostics, downloaded payloads or model text in logs."""
    if result.returncode:
        raise RuntimeError
    return result.stdout


def release_assets(tag: str) -> list[dict[str, object]]:
    """Read every asset page, including busy monthly releases."""
    metadata = mapping(github_api(f"repos/{TRANSPORT_REPOSITORY}/releases/tags/{tag}"))
    release_id = TypeAdapter(int).validate_python(metadata["id"], strict=True)
    result: list[dict[str, object]] = []
    page = 1
    while True:
        assets = TypeAdapter(list[dict[str, object]]).validate_python(
            github_api(
                f"repos/{TRANSPORT_REPOSITORY}/releases/{release_id}/assets"
                f"?per_page=100&page={page}"
            )
        )
        result.extend(assets)
        if len(assets) < PAGE_SIZE:
            return result
        page += 1


def dispatch(tag: str, asset: str) -> None:
    """Dispatch only the protected-main workflow with bounded asset selectors."""
    if not re.fullmatch(
        r"ai-agent-incoming-[0-9]{4}-[0-9]{2}", tag
    ) or not re.fullmatch(r"agent-input-[a-f0-9]{64}\.json", asset):
        raise AgentEvidenceError
    require_success(
        gh(
            [
                "workflow",
                "run",
                "ai-agent-ingest.yml",
                "--repo",
                TRANSPORT_REPOSITORY,
                "--ref",
                "main",
                "-f",
                f"asset_name={asset}",
                "-f",
                f"tag={tag}",
            ]
        )
    )


def delivered(pending: dict[str, object]) -> bool:
    """A queued upload counts as delivered only after its hosted signature verifies."""
    digest = str(pending["batch_id"])
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise AgentEvidenceError
    tag = "ai-telemetry-" + str(pending["tag"])[-7:]
    try:
        assets = release_assets(tag)
    except subprocess.SubprocessError:
        return False
    names = {str(a["name"]) for a in assets}
    for name in sorted(names):
        if not re.fullmatch(rf"agent-batch-{digest}-[0-9]+\.json", name):
            continue
        companion = name[:-5] + ".sigstore.json"
        if companion not in names:
            continue
        with tempfile.TemporaryDirectory(prefix="agent-delivery-proof-") as temporary:
            directory = Path(temporary)
            for asset in (name, companion):
                require_success(
                    gh(
                        [
                            "release",
                            "download",
                            tag,
                            "--repo",
                            TRANSPORT_REPOSITORY,
                            "--pattern",
                            asset,
                            "--dir",
                            str(directory),
                        ]
                    )
                )
            verified = gh(
                [
                    "attestation",
                    "verify",
                    str(directory / name),
                    "--repo",
                    TRANSPORT_REPOSITORY,
                    "--bundle",
                    str(directory / companion),
                    "--signer-workflow",
                    f"{TRANSPORT_REPOSITORY}/.github/workflows/ai-agent-ingest.yml",
                    "--source-ref",
                    "refs/heads/main",
                    "--deny-self-hosted-runners",
                    "--predicate-type",
                    PREDICATE,
                ]
            )
            if verified.returncode == 0:
                document = mapping(json.loads((directory / name).read_text()))
                if document.get("batch_id") != digest:
                    raise AgentEvidenceError
                return True
    return False


def save_ledger(ledger: Path, state: dict[str, object]) -> None:
    """Checkpoint pending work atomically across scanner/network/job failures."""
    ledger.parent.mkdir(parents=True, exist_ok=True)
    temporary = ledger.with_suffix(".tmp")
    temporary.write_text(canonical(state), encoding="utf-8")
    temporary.replace(ledger)


def release(tag: str) -> None:
    """Create only this tool's prerelease; never overwrite an existing asset."""
    if gh(["release", "view", tag, "--repo", TRANSPORT_REPOSITORY]).returncode:
        result = gh(
            [
                "release",
                "create",
                tag,
                "--repo",
                TRANSPORT_REPOSITORY,
                "--prerelease",
                "--latest=false",
                "--title",
                tag,
                "--notes",
                "Bounded public agent evidence; hosted ingestion signs bytes only.",
            ]
        )
        if (
            result.returncode
            and gh(["release", "view", tag, "--repo", TRANSPORT_REPOSITORY]).returncode
        ):
            raise RuntimeError


def submit(source: Path, ledger: Path) -> None:
    """Submit one batch, retaining pending records until signature confirmation."""
    if mapping(github_api("user")).get("login") != OWNER:
        raise AgentEvidenceError
    state = mapping(json.loads(ledger.read_text()) if ledger.exists() else {})
    submitted = set(TypeAdapter(list[str]).validate_python(state.get("submitted", [])))
    pending = mapping(state.get("pending"))
    if pending:
        if not delivered(pending):
            dispatch(str(pending["tag"]), str(pending["asset"]))
            return
        submitted.update(TypeAdapter(list[str]).validate_python(pending["ids"]))
        state.update(submitted=sorted(submitted), pending=None)
        save_ledger(ledger, state)
    with tempfile.TemporaryDirectory(prefix="agent-public-export-") as temporary:
        directory = Path(temporary)
        outgoing = directory / "batch.json"
        ids = prepare(source, outgoing, submitted)
        if not ids:
            return
        digest = hashlib.sha256(outgoing.read_bytes()).hexdigest()
        asset = directory / f"agent-input-{digest}.json"
        outgoing.rename(asset)
        tag = "ai-agent-incoming-" + timestamp()[:7]
        release(tag)
        if not any(a.get("name") == asset.name for a in release_assets(tag)):
            require_success(
                gh(
                    [
                        "release",
                        "upload",
                        tag,
                        str(asset),
                        "--repo",
                        TRANSPORT_REPOSITORY,
                    ]
                )
            )
        state["pending"] = {
            "ids": ids,
            "asset": asset.name,
            "tag": tag,
            "batch_id": mapping(json.loads(asset.read_text()))["batch_id"],
        }
        save_ledger(ledger, state)
        dispatch(tag, asset.name)


def ingest(tag: str, asset_name: str, output: Path) -> None:
    """Download only fixed-repository owner uploads; repeat validation and scanning."""
    if not re.fullmatch(
        r"ai-agent-incoming-[0-9]{4}-[0-9]{2}", tag
    ) or not re.fullmatch(r"agent-input-[a-f0-9]{64}\.json", asset_name):
        raise AgentEvidenceError
    if not public_repository(TRANSPORT_REPOSITORY):
        raise AgentEvidenceError
    assets = release_assets(tag)
    asset = next(a for a in assets if a.get("name") == asset_name)
    if (
        mapping(asset.get("uploader")).get("login") != OWNER
        or int(str(asset["size"])) > MAX_BATCH_BYTES
    ):
        raise AgentEvidenceError
    with tempfile.TemporaryDirectory(prefix="agent-hosted-ingest-") as temporary:
        directory = Path(temporary)
        require_success(
            gh(
                [
                    "release",
                    "download",
                    tag,
                    "--repo",
                    TRANSPORT_REPOSITORY,
                    "--pattern",
                    asset_name,
                    "--dir",
                    str(directory),
                ]
            )
        )
        payload = (directory / asset_name).read_bytes()
        if (
            len(payload) > MAX_BATCH_BYTES
            or hashlib.sha256(payload).hexdigest() != asset_name[12:-5]
        ):
            raise AgentEvidenceError
        document = mapping(json.loads(payload))
        if (
            document.get("record_type") != "agent-batch/v1"
            or document.get("schema_version") != 1
        ):
            raise AgentEvidenceError
        incoming = TypeAdapter(list[dict[str, object]]).validate_python(
            document["records"]
        )
        if not 0 < len(incoming) <= MAX_BATCH_RECORDS:
            raise AgentEvidenceError
        source = directory / "records.jsonl"
        source.write_text(
            "".join(canonical(r) + "\n" for r in incoming), encoding="utf-8"
        )
        # Unknown/private targets abort ingestion, including mixed batches.
        if len(prepare(source, output, set())) != len(incoming):
            raise AgentEvidenceError
    result = mapping(json.loads(output.read_text()))
    result["ingestion"] = {
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "source_asset": asset_name,
        "source_tag": tag,
        "controller_execution_provenance": "not independently attested",
    }
    output.write_text(canonical(result), encoding="utf-8")
    output.with_name("predicate.json").write_text(
        canonical(
            {
                "schema_version": 1,
                "predicate_type": PREDICATE,
                "batch_id": result["batch_id"],
                "source_assurance": result["source_assurance"],
                "ingestion": result["ingestion"],
            }
        ),
        encoding="utf-8",
    )


def archive(record: Path, bundle: Path, directory: Path) -> None:
    """Keep the hosted signature next to its immutable public batch."""
    data = mapping(json.loads(record.read_text()))
    identity = str(data["batch_id"])
    if not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise AgentEvidenceError
    directory.mkdir(parents=True, exist_ok=True)
    run_id = os.environ["GITHUB_RUN_ID"]
    if not run_id.isdigit():
        raise AgentEvidenceError
    target = directory / f"agent-batch-{identity}-{run_id}.json"
    signature = directory / f"agent-batch-{identity}-{run_id}.sigstore.json"
    shutil.copyfile(record, target)
    shutil.copyfile(bundle, signature)
    source_tag = str(mapping(data.get("ingestion")).get("source_tag", ""))
    if not re.fullmatch(r"ai-agent-incoming-[0-9]{4}-[0-9]{2}", source_tag):
        raise AgentEvidenceError
    tag = "ai-telemetry-" + source_tag[-7:]
    release(tag)
    require_success(
        gh(
            [
                "release",
                "upload",
                tag,
                str(target),
                str(signature),
                "--repo",
                TRANSPORT_REPOSITORY,
            ]
        )
    )


def main() -> None:
    """Separate the local sender from hosted ingestion and signature archival."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["submit", "ingest", "archive"])
    parser.add_argument("--source", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--tag", default="")
    parser.add_argument("--asset-name", default="")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--directory", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "submit" and args.source and args.ledger:
            submit(args.source, args.ledger)
        elif args.command == "ingest" and args.output:
            ingest(args.tag, args.asset_name, args.output)
        elif (
            args.command == "archive" and args.output and args.bundle and args.directory
        ):
            archive(args.output, args.bundle, args.directory)
        else:
            parser.error("missing command arguments")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        RuntimeError,
        StopIteration,
        subprocess.SubprocessError,
        ValidationError,
    ):
        message = "Agent telemetry operation failed; payload and diagnostics withheld."
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
