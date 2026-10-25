"""Validate untrusted model output before any GitHub or patch operation."""

import json
import re
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

MAX_PATCH_LINES = 400
MAX_PATCH_FILES = 5
DIFF_HEADER_FIELDS = 4


class InlineFinding(BaseModel):
    """One advisory finding whose location must also exist in the PR diff."""

    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1, max_length=300)
    line: int = Field(ge=1)
    body: str = Field(min_length=1, max_length=3000)


class Analysis(BaseModel):
    """The bounded contract for every model response."""

    model_config = ConfigDict(extra="forbid", strict=True)
    summary: str = Field(min_length=1, max_length=30000)
    comments: list[InlineFinding] = Field(
        default_factory=list[InlineFinding], max_length=10
    )
    patch: str = Field(default="", max_length=20000)


class UnsafePatchError(Exception):
    """A model patch attempts to leave the permitted review scope."""


def parse_analysis(text: str) -> Analysis:
    """Parse model JSON, accepting an optional single Markdown code fence."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return Analysis.model_validate_json(text)


def extract_text(events: str, *, tolerant: bool = False) -> str:
    """Read only final text events, never tool commands, from OpenCode JSONL."""
    fragments: list[str] = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "text":
                fragments.append(str(event["part"]["text"]))
        except (ValueError, TypeError, KeyError, AttributeError):
            if not tolerant:
                raise
    return "".join(fragments)


def added_lines(diff: str) -> dict[str, set[int]]:
    """Map added RIGHT-side lines so model locations cannot target other files."""
    locations: dict[str, set[int]] = {}
    path = ""
    line_number = 0
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].split("\t", 1)[0]
            locations.setdefault(path, set())
        elif match := re.match(r"@@ -[0-9,]+ \+(\d+)(?:,\d+)? @@", line):
            line_number = int(match.group(1))
        elif path and line.startswith("+"):
            locations[path].add(line_number)
            line_number += 1
        elif line.startswith(" "):
            line_number += 1
    return locations


def valid_findings(analysis: Analysis, diff: str) -> list[InlineFinding]:
    """Discard any annotation outside the actual added lines."""
    locations = added_lines(diff)
    return [
        finding
        for finding in analysis.comments
        if finding.line in locations.get(finding.path, set())
    ]


def _safe_patch_path(raw_path: str) -> str | None:
    if raw_path == "/dev/null":
        return None
    if not raw_path.startswith(("a/", "b/")):
        raise UnsafePatchError
    path = raw_path[2:]
    parts = PurePosixPath(path).parts
    if ".." in parts or not re.fullmatch(r"[A-Za-z0-9_./-]+", path):
        raise UnsafePatchError
    allowed = (
        path == "README.md"
        or (parts[0] in {"src", "tests"} and path.endswith(".py"))
        or (parts[0] in {"docs", "standards"} and path.endswith(".md"))
    )
    if not allowed or PurePosixPath(path).name in {"AGENTS.md", "CLAUDE.md"}:
        raise UnsafePatchError
    return path


def _paths_from_line(line: str) -> list[str]:
    if line.startswith("diff --git "):
        components = line.split()
        if len(components) != DIFF_HEADER_FIELDS:
            raise UnsafePatchError
        candidates = components[2:]
    elif line.startswith(("--- ", "+++ ")):
        candidates = [line[4:]]
    else:
        return []
    return [path for candidate in candidates if (path := _safe_patch_path(candidate))]


def validate_patch(patch: str) -> list[str]:
    """Allow a bounded text patch only in application, test or documentation paths.

    Configuration, workflows, agent rules and credentials cannot be changed by
    automated AI fixes. Git applies and tests the resulting patch in later jobs.
    """
    if not patch or len(patch.splitlines()) > MAX_PATCH_LINES:
        raise UnsafePatchError
    paths: list[str] = []
    for line in patch.splitlines():
        if line.startswith("new file mode ") and line != "new file mode 100644":
            raise UnsafePatchError
        if line.startswith(
            ("GIT binary patch", "rename ", "copy ", "new mode", "old mode")
        ):
            raise UnsafePatchError
        paths.extend(_paths_from_line(line))
    if not paths or len(set(paths)) > MAX_PATCH_FILES:
        raise UnsafePatchError
    return sorted(set(paths))
