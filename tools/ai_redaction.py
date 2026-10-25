"""Remove the actual provider credential before response parsing or recording."""

import json
import re
from typing import cast

REDACTED = "[REDACTED PROVIDER CREDENTIAL]"
MAX_JSON_STRING_LAYERS = 3


def replace_value(text: str, key: str, replacement: str) -> str:
    """Also remove ordinary mixed JSON Unicode escapes in diagnostic fragments."""
    text = text.replace(key, replacement)
    if r"\u" in text and key.isascii():
        pattern = "".join(
            "(?:" + re.escape(char) + "|(?i:" + r"\\u" + f"{ord(char):04x}" + "))"
            for char in key
        )
        text = re.sub(pattern, lambda _match: replacement, text)
    return text


def _scrub(value: object, key: str, layers: int, replacement: str) -> object:
    if isinstance(value, str):
        text = replace_value(value, key, replacement)
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
            scrubbed = _scrub(decoded, key, layers + 1, replacement)
            return (
                text
                if scrubbed == decoded
                else json.dumps(scrubbed, ensure_ascii=False)
            )
        return text
    if isinstance(value, dict):
        return {
            replace_value(name, key, replacement): _scrub(
                item, key, layers, replacement
            )
            for name, item in cast("dict[str, object]", value).items()
        }
    if isinstance(value, list):
        return [
            _scrub(item, key, layers, replacement)
            for item in cast("list[object]", value)
        ]
    return value


def redact_events(events: str, key: str, *, replacement: str = REDACTED) -> str:
    """Scrub successful and failed JSONL events without exposing raw diagnostics."""
    if not key:
        return events
    lines: list[str] = []
    for line in events.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            lines.append(replace_value(line, key, replacement))
        else:
            lines.append(
                json.dumps(_scrub(value, key, 0, replacement), ensure_ascii=False)
            )
    return "\n".join(lines)
