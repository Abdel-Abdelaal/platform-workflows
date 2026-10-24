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
    assert ai_context.snapshot(tmp_path) == ""


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
def test_context_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, with_diff: bool
) -> None:
    output = tmp_path / "context.md"
    args = ["tool", "--repository", str(tmp_path), "--output", str(output)]
    if with_diff:
        diff = tmp_path / "diff.txt"
        diff.write_text("diff")
        args.extend(["--diff", str(diff)])
    monkeypatch.setattr(sys, "argv", args)
    monkeypatch.setattr(ai_context, "snapshot", Mock(return_value="source"))
    ai_context.main()
    assert "source" in output.read_text()
