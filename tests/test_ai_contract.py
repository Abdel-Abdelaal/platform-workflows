import json

import pytest
from pydantic import ValidationError

from tools.ai_contract import (
    Analysis,
    InlineFinding,
    UnsafePatchError,
    added_lines,
    extract_text,
    parse_analysis,
    valid_findings,
    validate_patch,
)

DIFF = r"""diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -1,2 +1,3 @@
 context
-old
+new
+second
\ No newline at end of file
"""


@pytest.mark.parametrize("fenced", [False, True])
def test_model_json_contract(fenced: bool) -> None:
    text = '{"summary":"Useful review", "comments":[], "patch":""}'
    if fenced:
        text = "```json\n" + text + "\n```"
    assert parse_analysis(text).summary == "Useful review"


@pytest.mark.parametrize(
    "text", ["not JSON", '{"summary":"x","commands":["evil"]}', '{"summary":""}']
)
def test_invalid_or_extended_model_output_rejected(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_analysis(text)


def test_extract_only_text_events() -> None:
    events = [
        {"type": "step_start"},
        {"type": "text", "part": {"text": "one"}},
        {"type": "tool_use", "part": {"text": "never execute this"}},
        {"type": "text", "part": {"text": "two"}},
    ]
    assert extract_text("\n".join(json.dumps(event) for event in events)) == "onetwo"


def test_inline_findings_must_match_added_diff_lines() -> None:
    assert added_lines(DIFF) == {"src/main.py": {2, 3}}
    valid = InlineFinding(path="src/main.py", line=2, body="issue (non-blocking): test")
    analysis = Analysis(
        summary="review",
        comments=[
            valid,
            InlineFinding(path="src/main.py", line=1, body="context line"),
            InlineFinding(path="other.py", line=2, body="wrong file"),
        ],
    )
    assert valid_findings(analysis, DIFF) == [valid]


@pytest.mark.parametrize(
    "path",
    [
        "src/main.py",
        "tests/unit/test_main.py",
        "docs/decision.md",
        "standards/python.md",
        "README.md",
    ],
)
def test_permitted_patch_paths(path: str) -> None:
    assert validate_patch(f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n") == [
        path
    ]


@pytest.mark.parametrize(
    "patch",
    [
        "",
        "--- a/.github/workflows/ci.yml\n+++ b/.github/workflows/ci.yml",
        "--- a/../../src/main.py\n+++ b/../../src/main.py",
        "--- /etc/passwd\n+++ /etc/passwd",
        "--- a/src/AGENTS.md\n+++ b/src/AGENTS.md",
        "--- a/src/key.pem\n+++ b/src/key.pem",
        "GIT binary patch\nanything",
        "rename from src/a.py\nrename to src/b.py",
        "copy from src/a.py",
        "new mode 100755",
        "old mode 100644",
        "new file mode 100755\n--- /dev/null\n+++ b/src/x.py",
        "--- a/src/x.py\tdate\n+++ b/src/x.py\tdate",
        "@@ -1 +1 @@\n-old\n+new",
        "--- a/\n+++ b/",
        " \n" * 401,
        "\n".join(f"--- /dev/null\n+++ b/src/file{number}.py" for number in range(6)),
    ],
)
def test_unsafe_patch_rejected(patch: str) -> None:
    with pytest.raises(UnsafePatchError):
        validate_patch(patch)


def test_new_non_executable_file_is_allowed() -> None:
    assert validate_patch(
        "new file mode 100644\n--- /dev/null\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+pass"
    ) == ["src/new.py"]


def test_git_diff_headers_are_validated_too() -> None:
    assert validate_patch(DIFF) == ["src/main.py"]


@pytest.mark.parametrize(
    "header",
    [
        "diff --git a/.github/ci.yml b/.github/ci.yml",
        "diff --git malformed",
        "diff --git a/../../src/main.py b/src/main.py",
        "new file mode 120000",
    ],
)
def test_patch_cannot_hide_unsafe_metadata_behind_valid_headers(header: str) -> None:
    with pytest.raises(UnsafePatchError):
        validate_patch(header + "\n--- a/src/main.py\n+++ b/src/main.py\n-old\n+new")
