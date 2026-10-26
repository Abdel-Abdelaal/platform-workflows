"""Trusted stdin/stdout excerpt scrubber for the controller's scanner hook."""

import json
import sys

from tools.ai_output_scan import OutputScanError, scan_events, scanner_path

MAX_BYTES = 16_000


def scrub(text: str) -> str:
    """Fail closed without a verified scanner; return only scrubbed excerpt text."""
    scanner = scanner_path()
    if scanner is None:
        raise OutputScanError
    cleaned, _count = scan_events(json.dumps({"excerpt": text}), scanner)
    value = json.loads(cleaned)["excerpt"]
    if not isinstance(value, str):
        raise OutputScanError
    return value


def read_excerpt() -> str:
    """Reject oversized input before parsing or spawning the scanner."""
    data = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise OutputScanError
    return data.decode("utf-8")


def main() -> None:
    """Read bounded stdin and emit only safe text, never diagnostics or credentials."""
    try:
        sys.stdout.write(scrub(read_excerpt()))
    except (OSError, ValueError, KeyError, OutputScanError):
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
