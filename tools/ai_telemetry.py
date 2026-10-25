"""Collect bounded AI evidence as data, without changing the analysis interface."""

import hashlib
import json
import os
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import ValidationError

from tools.ai_contract import Analysis, UnsafePatchError, valid_findings, validate_patch

CURRENT: ContextVar[dict[str, Any] | None] = ContextVar("ai_record", default=None)
MAX_RESPONSE_CHARACTERS = 100000
TOKEN_FIELDS = {
    "input": "gen_ai.usage.input_tokens",
    "output": "gen_ai.usage.output_tokens",
    "reasoning": "gen_ai.usage.reasoning.output_tokens",
}


def timestamp() -> str:
    """Return an unambiguous UTC timestamp."""
    return datetime.now(UTC).isoformat()


def digest(text: str) -> str:
    """Identify exact UTF-8 input without copying repository content."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def new_record(context: str, prompt: str, *, thinking: bool) -> dict[str, Any]:
    """Copy only explicitly allowlisted identity and configuration fields."""
    identity = {
        name.lower(): os.environ.get(name, "")
        for name in (
            "GITHUB_REPOSITORY",
            "GITHUB_RUN_ID",
            "GITHUB_RUN_ATTEMPT",
            "GITHUB_EVENT_NAME",
            "GITHUB_WORKFLOW_REF",
            "GITHUB_SHA",
            "HEAD_SHA",
            "PR_NUMBER",
            "MODE",
            "PLATFORM_RELEASE",
            "TOOLING_COMMIT",
        )
    }
    return {
        "schema_version": 1,
        "record_id": str(uuid4()),
        "started_at": timestamp(),
        "identity": identity,
        "attributes": {
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "xiaomi",
            "gen_ai.request.model": "mimo-v2.6-flash",
            "server.address": urlsplit(
                os.environ.get(
                    "AI_BASE_URL", "https://token-plan-ams.xiaomimimo.com/v1"
                )
            ).hostname,
        },
        "configuration": {
            "thinking": thinking,
            "json_mode": not thinking,
            "prompt_sha256": digest(prompt),
            "context_sha256": digest(context),
            "context_characters": len(context),
            "glossary_present": "--- GLOSSARY DATA ---" in context,
        },
        "attempts": [],
        "status": "no_valid_output",
    }


def mapping(value: object) -> dict[str, Any]:
    """Treat non-object event payloads as missing telemetry."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def step_parts(events: str) -> list[dict[str, Any]]:
    """Ignore malformed events without losing other completed-step usage."""
    parts: list[dict[str, Any]] = []
    for line in events.splitlines():
        try:
            event = mapping(json.loads(line))
        except (ValueError, TypeError):
            continue
        if event.get("type") == "step_finish":
            parts.append(mapping(event.get("part")))
    return parts


def event_usage(events: str) -> dict[str, Any]:
    """Sum OpenCode step totals; unavailable usage stays absent, never zero."""
    usage: dict[str, Any] = {}
    reasons: list[str] = []
    for part in step_parts(events):
        tokens = mapping(part.get("tokens"))
        cache = mapping(tokens.get("cache"))
        values = {TOKEN_FIELDS[k]: tokens.get(k) for k in TOKEN_FIELDS}
        values["gen_ai.usage.cache_read.input_tokens"] = cache.get("read")
        values["gen_ai.usage.cache_write.input_tokens"] = cache.get("write")
        for key, value in values.items():
            if type(value) is int and value >= 0:
                usage[key] = usage.get(key, 0) + value
        reason = part.get("reason")
        if isinstance(reason, str):
            reasons.append(reason[:100])
    # OpenCode input excludes cached input; output excludes reasoning. OTel totals
    # include those subsets. Preserve the provider components for reconciliation.
    raw = dict(usage)
    if "gen_ai.usage.input_tokens" in usage:
        usage["gen_ai.usage.input_tokens"] += sum(
            usage.get(f"gen_ai.usage.cache_{kind}.input_tokens", 0)
            for kind in ("read", "write")
        )
    if "gen_ai.usage.output_tokens" in usage:
        usage["gen_ai.usage.output_tokens"] += usage.get(
            "gen_ai.usage.reasoning.output_tokens", 0
        )
    return {
        "attributes": usage,
        "opencode_usage": raw,
        "gen_ai.response.finish_reasons": reasons,
    }


def record_attempt(events: str, duration: float, error: Exception | None) -> None:
    """Retain response text as bounded data and errors without offending values."""
    record = CURRENT.get()
    if record is None:
        return
    attempt: dict[str, Any] = {
        "duration_seconds": duration,
        "exit_category": type(error).__name__ if error else "ok",
        **event_usage(events),
    }
    if isinstance(error, ValidationError):
        attempt["validation_errors"] = [
            {"type": item["type"], "loc": item["loc"]}
            for item in error.errors(
                include_url=False, include_input=False, include_context=False
            )
        ]
    fragments: list[str] = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                fragments.append(str(event["part"]["text"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            continue
    response = "".join(fragments)
    attempt["response"] = response[:MAX_RESPONSE_CHARACTERS]
    attempt["response_sha256"] = digest(response)
    attempt["response_truncated"] = len(response) > MAX_RESPONSE_CHARACTERS
    record["attempts"].append(attempt)


def complete(record: dict[str, Any], analysis: Analysis, diff: str) -> None:
    """Record the validated output and deterministic filtering decisions."""
    record["status"] = "valid"
    record["analysis"] = analysis.model_dump()
    findings = valid_findings(analysis, diff)
    record["findings"] = {
        "proposed": len(analysis.comments),
        "eligible": len(findings),
        "dropped": len(analysis.comments) - len(findings),
        "eligible_locations": [{"path": f.path, "line": f.line} for f in findings],
    }
    patch: dict[str, Any] = {"status": "not_proposed", "accepted_paths": []}
    if analysis.patch:
        try:
            patch = {
                "status": "accepted",
                "accepted_paths": validate_patch(analysis.patch),
            }
        except UnsafePatchError:
            patch["status"] = "rejected"
    record["patch_check"] = patch


def save(record: dict[str, Any], path: Path) -> None:
    """Write evidence atomically; callers must secret-scan before publication."""
    record.setdefault("ended_at", timestamp())
    totals: dict[str, int] = {}
    for attempt in record["attempts"]:
        for key, value in attempt["attributes"].items():
            totals[key] = totals.get(key, 0) + value
    record["usage_totals"] = totals
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(
        (json.dumps(record, ensure_ascii=True, indent=2) + "\n").encode()
    )
    temporary.replace(path)


def context_manifest(context: str) -> list[dict[str, str]]:
    """Read bounded source delimiters, retaining names only as untrusted data."""
    return [
        {"path": match, "status": "included"}
        for match in re.findall(r"^--- UNTRUSTED SOURCE: (.*?) ---$", context, re.M)
    ]
