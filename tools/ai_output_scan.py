"""Use an explicitly supplied, verified scanner before retaining model output."""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from tools.ai_redaction import redact_events

MAX_EVENTS_BYTES = 2_000_000
MAX_REPORT_BYTES = 8_000_000
MAX_SECRET_VALUES = 128
MAX_SECRET_BYTES = 32_768
MAX_JSON_LAYERS = 3
MAX_STRUCTURE_DEPTH = 32
REDACTED = "[REDACTED SECRET]"
SAFE_ENVIRONMENT = {
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
}


class OutputScanError(RuntimeError):
    """Output could not be safely scanned; raw diagnostics must be withheld."""


def decoded(value: object, layers: int = 0, depth: int = 0) -> object:
    """Expose ordinary nested JSON escapes to the scanner, without executing text."""
    if depth > MAX_STRUCTURE_DEPTH:
        raise OutputScanError
    if isinstance(value, str):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", value.strip())
        try:
            inner = json.loads(candidate)
        except ValueError:
            return re.sub(
                r"\\u([0-9a-fA-F]{4})", lambda match: chr(int(match[1], 16)), value
            )
        if layers >= MAX_JSON_LAYERS:
            raise OutputScanError
        return decoded(inner, layers + 1, depth + 1)
    if isinstance(value, dict):
        return {
            key: decoded(item, layers, depth + 1)
            for key, item in cast("dict[str, object]", value).items()
        }
    if isinstance(value, list):
        return [
            decoded(item, layers, depth + 1) for item in cast("list[object]", value)
        ]
    return value


def scanner_path() -> Path | None:
    """Opt in explicitly; refuse relative or missing executables before inference."""
    setting = os.environ.get("AI_OUTPUT_SECRET_SCANNER", "")
    if not setting:
        return None
    path = Path(setting)
    if not path.is_absolute() or not path.is_file():
        raise OutputScanError
    return path


def secret_values(matches: object, status: int) -> set[str]:
    """Validate the scanner's structured result without trusting its raw output."""
    if not isinstance(matches, list):
        raise OutputScanError
    secrets: set[str] = set()
    for item in cast("list[object]", matches):
        if not isinstance(item, dict):
            raise OutputScanError
        secret = cast("dict[str, object]", item).get("Secret")
        if (
            not isinstance(secret, str)
            or not secret
            or len(secret.encode()) > MAX_SECRET_BYTES
        ):
            raise OutputScanError
        secrets.add(secret)
    if bool(secrets) != (status == 1) or len(secrets) > MAX_SECRET_VALUES:
        raise OutputScanError
    return secrets


def scan_events(events: str, scanner: Path) -> tuple[str, int]:
    """Redact matched values, or fail closed on malformed/unavailable scan evidence."""
    if len(events.encode()) > MAX_EVENTS_BYTES:
        raise OutputScanError
    if not events:
        return events, 0
    try:
        values: list[object] = []
        for line in events.splitlines():
            try:
                value = json.loads(line)
            except ValueError:
                value = line
            values.append(decoded(value))
        source = json.dumps(values, ensure_ascii=False).encode()
        if len(source) > MAX_EVENTS_BYTES:
            raise OutputScanError
        with tempfile.TemporaryDirectory(prefix="ai-output-scan-") as directory:
            report = Path(directory) / "matches.json"
            descriptor = os.open(report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(descriptor)
            result = subprocess.run(
                [
                    str(scanner),
                    "stdin",
                    "--no-banner",
                    "--report-format",
                    "json",
                    "--report-path",
                    str(report),
                    "--exit-code",
                    "1",
                ],
                input=source,
                capture_output=True,
                check=False,
                cwd=directory,
                env={
                    name: value
                    for name, value in os.environ.items()
                    if name.upper() in SAFE_ENVIRONMENT
                },
                timeout=30,
            )
            if (
                result.returncode not in {0, 1}
                or report.stat().st_size > MAX_REPORT_BYTES
            ):
                raise OutputScanError
            matches: object = json.loads(report.read_text(encoding="utf-8"))
        secrets = secret_values(matches, result.returncode)
        for secret in sorted(secrets, key=len, reverse=True):
            events = redact_events(events, secret, replacement=REDACTED)
        return events, len(secrets)
    except (OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
        raise OutputScanError from None
