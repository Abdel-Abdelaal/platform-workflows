"""Bound the controller's untrusted attempt records before public ingestion."""

import hashlib
import json
import math
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

OWNER = "Abdel-Abdelaal"
TRANSPORT_REPOSITORY = f"{OWNER}/platform-workflows"
MAX_BATCH_RECORDS = 25
MAX_BATCH_BYTES = 1_000_000
MAX_LIST = 20
SOURCE_SCHEMA = "agent-dispatcher.attempt/v1"
PREDICATE = (
    f"https://github.com/{TRANSPORT_REPOSITORY}/blob/main/"
    "docs/ai-agent-telemetry.md#agent-batch-v1"
)
Stage = Literal[
    "triage",
    "plan",
    "implement",
    "repair",
    "review",
    "ci_repair",
    "ci_review",
    "gate",
    "route",
    "publish",
]


class AgentEvidenceError(ValueError):
    """A bounded public export or provenance requirement was not satisfied."""


class AgentAttempt(BaseModel):
    """Allowlist public fields; unknown producer extensions never publish by default."""

    model_config = ConfigDict(strict=True, extra="ignore", populate_by_name=True)
    source_schema: Literal["agent-dispatcher.attempt/v1"] = Field(alias="schema")
    record_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    recorded_at: str = Field(max_length=40)
    repo: str = Field(pattern=r"^Abdel-Abdelaal/[A-Za-z0-9_.-]+$")
    stage: Stage
    run_id: int | None = Field(default=None, ge=0)
    attempt: int | None = Field(default=None, ge=0)
    issue: int | None = Field(default=None, ge=1)
    pr_url: str | None = Field(default=None, max_length=300)
    branch: str | None = Field(default=None, max_length=300)
    provider: str | None = Field(default=None, max_length=80)
    harness: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    effort: str | None = Field(default=None, max_length=30)
    level: str | None = Field(default=None, max_length=30)
    read_only: bool | None = None
    started_at: str | None = Field(default=None, max_length=40)
    finished_at: str | None = Field(default=None, max_length=40)
    duration_ms: float | int | None = Field(default=None, ge=0, le=86_400_000)
    prompt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    prompt_chars: int | None = Field(default=None, ge=0)
    context_sha256: dict[str, str] | str | None = None
    outcome: str | None = Field(default=None, max_length=80)
    reason: str | None = Field(default=None, max_length=2000)
    exit_code: int | None = None
    exhausted: bool | None = None
    resets_at: str | None = Field(default=None, max_length=40)
    usage: dict[str, int | float | None] | None = None
    available_usage: None = None
    output_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    output_chars: int | None = Field(default=None, ge=0)
    output_excerpt: str = Field(default="", max_length=2000)
    gate_refusals: list[str] = Field(default_factory=list[str], max_length=20)
    files: int | list[str] | None = None
    lines: int | None = Field(default=None, ge=0)

    @field_validator("recorded_at", "started_at", "finished_at", "resets_at")
    @classmethod
    def aware_time(cls, value: str | None) -> str | None:
        """Reject ambiguous local timestamps instead of inventing UTC evidence."""
        if value is not None and datetime.fromisoformat(value).utcoffset() is None:
            raise ValueError
        return value

    @field_validator("context_sha256")
    @classmethod
    def context_hashes(cls, value: dict[str, str] | str | None) -> object:
        """Keep hashes only, never accidentally retain attached source text."""
        hashes = [value] if isinstance(value, str) else list((value or {}).values())
        if len(hashes) > MAX_LIST or any(
            not re.fullmatch(r"[a-f0-9]{64}", h) for h in hashes
        ):
            raise ValueError
        if isinstance(value, dict) and any(
            not re.fullmatch(r"[a-z_]{1,40}", key) for key in value
        ):
            raise ValueError
        return value

    @field_validator("usage")
    @classmethod
    def reported_usage(cls, value: dict[str, int | float | None] | None) -> object:
        """Keep known provider counters; missing counters remain absent."""
        allowed = {
            "input_tokens",
            "output_tokens",
            "reasoning_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "reported_cost_usd",
            "total_tokens",
        }
        if value and (
            not value.keys() <= allowed
            or any(
                number is not None and (number < 0 or not math.isfinite(number))
                for number in value.values()
            )
        ):
            raise ValueError
        return value


def canonical(value: object) -> str:
    """Use a deterministic transport encoding, rejecting non-finite numbers."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


def batch(records: list[AgentAttempt]) -> dict[str, object]:
    """Bind every bounded source record into one signable public subject."""
    if not records or len(records) > MAX_BATCH_RECORDS:
        raise AgentEvidenceError
    documents = [r.model_dump(by_alias=True) for r in records]
    payload = canonical(documents)
    if len(payload.encode()) > MAX_BATCH_BYTES:
        raise AgentEvidenceError
    document: dict[str, object] = {
        "schema_version": 1,
        "record_type": "agent-batch/v1",
        "batch_id": hashlib.sha256(payload.encode()).hexdigest(),
        "source_assurance": "controller-reported; hosted ingestion signs bytes only",
        "records": documents,
        "payload_retention": "hashes and bounded excerpts; no full prompts or outputs",
    }
    if len(canonical(document).encode()) > MAX_BATCH_BYTES:
        raise AgentEvidenceError
    return document
