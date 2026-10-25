"""Remove the actual provider credential before response parsing or recording."""

import json
import re
from typing import cast

REDACTED = "[REDACTED PROVIDER CREDENTIAL]"
MAX_JSON_STRING_LAYERS = 3


def _scrub(value: object, key: str, layers: int) -> object:
    if isinstance(value, str):
        text = value.replace(key, REDACTED)
        # OpenCode text events contain a second JSON document as a string. Decode
        # that document too, so ordinary JSON escapes cannot hide the credential.
        if layers < MAX_JSON_STRING_LAYERS:
            candidate = text.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
                candidate = re.sub(r"\s*```$", "", candidate)
            try:
                decoded = json.loads(candidate)
            except ValueError:
                return text
            scrubbed = _scrub(decoded, key, layers + 1)
            return (
                text
                if scrubbed == decoded
                else json.dumps(scrubbed, ensure_ascii=False)
            )
        return text
    if isinstance(value, dict):
        return {
            name.replace(key, REDACTED): _scrub(item, key, layers)
            for name, item in cast("dict[str, object]", value).items()
        }
    if isinstance(value, list):
        return [_scrub(item, key, layers) for item in cast("list[object]", value)]
    return value


def redact_events(events: str, key: str) -> str:
    """Scrub successful and failed JSONL events without exposing raw diagnostics."""
    if not key:
        return events
    lines: list[str] = []
    for line in events.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            lines.append(line.replace(key, REDACTED))
        else:
            lines.append(json.dumps(_scrub(value, key, 0), ensure_ascii=False))
    return "\n".join(lines)
