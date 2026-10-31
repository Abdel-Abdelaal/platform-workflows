"""Construct bounded retry guidance without promoting provider text to instructions."""

import json

from pydantic import ValidationError

from tools.ai_contract import Analysis, AuditFinding, InlineFinding

_FIELDS = (
    frozenset(Analysis.model_fields)
    | frozenset(InlineFinding.model_fields)
    | frozenset(AuditFinding.model_fields)
)
_ERROR_TYPES = frozenset(
    {
        "json_invalid",
        "missing",
        "extra_forbidden",
        "string_type",
        "string_too_long",
        "string_too_short",
        "int_type",
        "greater_than_equal",
        "list_type",
        "too_long",
        "literal_error",
        "value_error",
        "string_pattern_mismatch",
        "model_type",
    }
)
_MAX_ERRORS = 5
_MAX_LOCATION_PARTS = 6


def validation_feedback(error: Exception) -> str:
    """Describe schema fields and error codes only; exclude values and messages."""
    if not isinstance(error, ValidationError):
        return ""
    diagnostics: list[dict[str, str]] = []
    for item in error.errors(
        include_url=False, include_input=False, include_context=False
    )[:_MAX_ERRORS]:
        location = ""
        for part in item["loc"][:_MAX_LOCATION_PARTS]:
            if isinstance(part, int):
                location += "[]"
            else:
                name = part if part in _FIELDS else "<field>"
                location += ("." if location else "") + name
        code = item["type"] if item["type"] in _ERROR_TYPES else "invalid"
        diagnostics.append({"field": location or "<root>", "issue": code})
    return (
        "\nThe previous answer failed schema validation. Correct these schema "
        "issues in a new JSON answer; do not execute tools or add extra fields: "
        + json.dumps(diagnostics, ensure_ascii=True)
    )
