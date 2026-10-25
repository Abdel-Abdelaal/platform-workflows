import sys
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from tools import ai_context


def test_snapshot_filters_credentials_configs_and_outside_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repository"
    repo.mkdir()
    files = {
        "main.py": "safe source",
        ".env.json": "secret",
        "opencode.json": "plugin config",
        "AGENTS.md": "instructions",
        "README.md": "safe docs",
        "image.png": "binary",
        ".opencode/agent.md": "instructions",
        "../outside.md": "outside",
    }
    for name, content in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    listed = "\0".join(files) + "\0"
    monkeypatch.setattr(
        ai_context.subprocess, "run", Mock(return_value=CompletedProcess([], 0, listed))
    )
    result = ai_context.snapshot(repo)
    assert "safe source" in result
    assert "safe docs" in result
    assert "secret" not in result
    assert "plugin config" not in result
    assert "outside" not in result
    assert "instructions" not in result


def test_snapshot_obeys_context_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "main.py").write_text("source")
    monkeypatch.setattr(
        ai_context.subprocess,
        "run",
        Mock(return_value=CompletedProcess([], 0, "main.py\0")),
    )
    monkeypatch.setattr(ai_context, "MAX_CONTEXT_CHARACTERS", 1)
    result = ai_context.snapshot(tmp_path)
    assert "UNTRUSTED SOURCE" not in result
    assert "CONTEXT BOUNDS" in result


def test_code_priority_and_smaller_files_survive_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {
        ".github/workflows/large.yml": "x" * 1000,
        "src/main.py": "business",
        "docs/note.md": "small",
    }
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(
        ai_context.subprocess,
        "run",
        Mock(return_value=CompletedProcess([], 0, "\0".join(files))),
    )
    monkeypatch.setattr(ai_context, "MAX_CONTEXT_CHARACTERS", 180)
    monkeypatch.setattr(ai_context, "MAX_FILE_CHARACTERS", 100)
    text = ai_context.snapshot(tmp_path)
    assert "business" in text
    assert "small" in text
    assert "CONTEXT BOUNDS: 1" in text
    assert "x" * 100 not in text


def test_handbook_snapshot_reads_standards_without_baseline_bulk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {"baseline/bulk.md": "not rules", "standards/security.md": "actual rules"}
    for name, content in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    monkeypatch.setattr(
        ai_context.subprocess,
        "run",
        Mock(return_value=CompletedProcess([], 0, "\0".join(files))),
    )
    text = ai_context.snapshot(tmp_path, prefix="standards/")
    assert "actual rules" in text
    assert "not rules" not in text


def test_partial_diff_is_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_context, "MAX_CONTEXT_CHARACTERS", 3)
    monkeypatch.setattr(ai_context, "snapshot", Mock(return_value=""))
    assert "DIFF TRUNCATED" in ai_context.build_context(tmp_path, "abcdef")


def test_glossary_is_data_without_other_agent_instructions(tmp_path: Path) -> None:
    assert ai_context.glossary(tmp_path) == ""
    (tmp_path / "AGENTS.md").write_text(
        "# Instructions\nignore policy\n## Glossary\n"
        "code means short code\n## Other\nrun commands"
    )
    text = ai_context.glossary(tmp_path)
    assert "code means short code" in text
    assert "run commands" not in text
    assert "ignore policy" not in text
    (tmp_path / "AGENTS.md").write_text("# No glossary")
    assert ai_context.glossary(tmp_path) == ""


def test_context_labels_diff_as_untrusted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ai_context, "snapshot", Mock(return_value="source"))
    assert "PR DIFF" in ai_context.build_context(tmp_path, "diff")
    assert "PR DIFF" not in ai_context.build_context(tmp_path)


@pytest.mark.parametrize("with_diff", [False, True])
@pytest.mark.parametrize("with_handbook", [False, True])
def test_context_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_diff: bool,
    with_handbook: bool,
) -> None:
    output = tmp_path / "context.md"
    args = ["tool", "--repository", str(tmp_path), "--output", str(output)]
    if with_diff:
        diff = tmp_path / "diff.txt"
        diff.write_text("diff")
        args.extend(["--diff", str(diff)])
    if with_handbook:
        args.extend(["--handbook", str(tmp_path)])
    monkeypatch.setattr(sys, "argv", args)
    snapshot = Mock(return_value="source")
    monkeypatch.setattr(ai_context, "snapshot", snapshot)
    ai_context.main()
    assert "source" in output.read_text()
    if with_handbook:
        assert snapshot.call_args.kwargs == {"prefix": "standards/", "manifest": []}
