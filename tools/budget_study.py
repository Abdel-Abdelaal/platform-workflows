"""Freeze inputs and account for every condition of the analysis budget study.

The trusted workflow verifies frozen input hashes before any provider call, runs
the four output/deadline profiles in a recorded random order, stops when the
provider rejects a call early (quota, credentials or endpoint), and publishes a
summary that keeps failed and unattempted conditions. A valid JSON analysis is
not a correctness result; adjudication happens separately.
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any, cast

from tools.ai_runner import EXPERIMENT_PROFILES
from tools.ai_telemetry import mapping

INPUTS = ("context", "manifest", "diff", "prompt")
PROFILES = tuple(sorted(EXPERIMENT_PROFILES))
# A call that ends without valid output this fast never reached real analysis:
# the provider refused it (quota, credentials, endpoint). Stop instead of
# spending the rest of the allowance on the same refusal.
EARLY_FAILURE_SECONDS = 120
SHA256_HEX = 64


class StudyError(Exception):
    """The study must not invoke the provider."""


def file_sha256(path: Path) -> str:
    """Hash exact bytes, so line endings and encodings count."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_spec(path: Path) -> dict[str, Any]:
    """Read the frozen spec and reject one without every input hash."""
    spec = mapping(json.loads(path.read_text(encoding="utf-8")))
    hashes = mapping(spec.get("sha256"))
    if set(hashes) != set(INPUTS) or not all(
        isinstance(value, str) and len(value) == SHA256_HEX for value in hashes.values()
    ):
        message = "Frozen spec needs exactly one sha256 for each study input."
        raise StudyError(message)
    return spec


def verify(spec: dict[str, Any], files: dict[str, Path]) -> dict[str, str]:
    """Return the verified hashes, or name (never print) the inputs that changed."""
    expected = mapping(spec.get("sha256"))
    actual = {name: file_sha256(files[name]) for name in INPUTS}
    changed = [name for name in INPUTS if actual[name] != expected.get(name)]
    if changed:
        message = "Frozen study input changed: " + ", ".join(changed)
        raise StudyError(message)
    return actual


def plan(seed: str) -> list[str]:
    """Randomize condition order reproducibly from a recorded seed."""
    return random.Random(seed).sample(PROFILES, len(PROFILES))  # noqa: S311 - ordering, not security


def outcome(profile: str, record_path: Path, exit_code: int) -> dict[str, Any]:
    """Reduce one runner record to fixed-shape metadata, without response text."""
    result: dict[str, Any] = {"profile": profile, "exit_code": exit_code}
    try:
        record = mapping(json.loads(record_path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {**result, "status": "missing_record", "attempts": []}
    attempts = [
        mapping(item) for item in cast("list[object]", record.get("attempts") or [])
    ]
    configuration = mapping(record.get("configuration"))
    totals = mapping(record.get("usage_totals"))
    return {
        **result,
        "status": record.get("status")
        if isinstance(record.get("status"), str)
        else "unknown",
        "evidence_gap": record.get("evidence_gap") is True,
        "requested_profile": configuration.get("requested_experiment_profile"),
        "record_id": record.get("record_id"),
        "attempts": [
            {
                "exit_category": attempt.get("exit_category"),
                "duration_seconds": attempt.get("duration_seconds"),
                "finish_reasons": attempt.get("gen_ai.response.finish_reasons"),
                "response_sha256": attempt.get("response_sha256"),
            }
            for attempt in attempts
        ],
        "usage_totals": {
            key: value
            for key, value in totals.items()
            if key.startswith("gen_ai.usage.") and type(value) in {int, float}
        },
    }


def early_failure(result: dict[str, Any]) -> bool:
    """True when the provider refused before any real analysis could happen."""
    if result.get("status") == "valid":
        return False
    attempts = cast("list[dict[str, Any]]", result["attempts"])
    durations: list[object] = [attempt.get("duration_seconds") for attempt in attempts]
    return all(
        isinstance(seconds, int | float)
        and not isinstance(seconds, bool)
        and seconds < EARLY_FAILURE_SECONDS
        for seconds in durations
    )


def summarize(
    spec: dict[str, Any],
    seed: str,
    results: list[dict[str, Any]],
    *,
    unattempted_reason: str,
) -> dict[str, Any]:
    """List every planned condition in order, attempted or not."""
    done = {result["profile"]: result for result in results}
    order = plan(seed)
    return {
        "schema_version": 1,
        "study": "output_and_deadline",
        "seed": seed,
        "order": order,
        "inputs": {
            key: spec.get(key)
            for key in ("task", "repository", "base", "head", "handbook", "prompt")
        },
        "input_sha256": spec.get("sha256"),
        "conditions": [
            done.get(
                profile,
                {
                    "profile": profile,
                    "status": "unattempted",
                    "reason": unattempted_reason,
                },
            )
            for profile in order
        ],
        "correctness": "awaiting independent adjudication",
        "scope": "Pilot: one process attempt per profile; no quality or parity claim.",
    }


def read_ledger(path: Path) -> list[dict[str, Any]]:
    """Read appended outcomes; a missing ledger means nothing was attempted."""
    if not path.exists():
        return []
    return [
        mapping(json.loads(line))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def main() -> None:
    """Verify, plan, record or summarize; only `record` and `summarize` write files."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--spec", type=Path, required=True)
    for name in INPUTS:
        check.add_argument(f"--{name}", type=Path, required=True)
    order = commands.add_parser("plan")
    order.add_argument("--seed", required=True)
    record = commands.add_parser("record")
    record.add_argument("--profile", choices=PROFILES, required=True)
    record.add_argument("--record", type=Path, required=True)
    record.add_argument("--exit-code", type=int, required=True)
    record.add_argument("--ledger", type=Path, required=True)
    summary = commands.add_parser("summarize")
    summary.add_argument("--spec", type=Path, required=True)
    summary.add_argument("--seed", required=True)
    summary.add_argument("--ledger", type=Path, required=True)
    summary.add_argument("--unattempted-reason", required=True)
    summary.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "verify":
        spec = load_spec(args.spec)
        hashes = verify(spec, {name: getattr(args, name) for name in INPUTS})
        sys.stdout.write(json.dumps(hashes, indent=2) + "\n")
    elif args.command == "plan":
        sys.stdout.write("\n".join(plan(args.seed)) + "\n")
    elif args.command == "record":
        result = outcome(args.profile, args.record, args.exit_code)
        with args.ledger.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(result) + "\n")
        sys.stdout.write(("stop" if early_failure(result) else "continue") + "\n")
    else:
        report = summarize(
            load_spec(args.spec),
            args.seed,
            read_ledger(args.ledger),
            unattempted_reason=args.unattempted_reason,
        )
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
