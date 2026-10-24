import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import ai_patch
from tools.ai_contract import Analysis, UnsafePatchError

PATCH = "--- a/src/main.py\n+++ b/src/main.py\n@@ -1 +1 @@\n-old\n+new\n"


def test_empty_proposal_does_not_modify_files(tmp_path: Path) -> None:
    assert not ai_patch.apply_proposal(
        tmp_path, Analysis(summary="No safe fix"), tmp_path / "proposal.diff"
    )


def test_real_git_apply_checks_before_changing_source(tmp_path: Path) -> None:
    subprocess.run(  # noqa: S603 - fixed local git initialization, no shell
        ["git", "init", "--quiet", str(tmp_path)],  # noqa: S607
        check=True,
        capture_output=True,
    )
    source = tmp_path / "src/main.py"
    source.parent.mkdir()
    source.write_text("old\n", newline="\n")
    assert ai_patch.apply_proposal(
        tmp_path, Analysis(summary="Fix", patch=PATCH), tmp_path / "proposal.diff"
    )
    assert source.read_text() == "new\n"


def test_symlink_target_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(Path, "is_symlink", Mock(return_value=True))
    with pytest.raises(UnsafePatchError):
        ai_patch.apply_proposal(
            tmp_path, Analysis(summary="Fix", patch=PATCH), tmp_path / "proposal.diff"
        )


def test_resolved_path_must_remain_in_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ai_patch, "validate_patch", Mock(return_value=["../outside.py"])
    )
    with pytest.raises(UnsafePatchError):
        ai_patch.apply_proposal(
            tmp_path, Analysis(summary="Fix", patch=PATCH), tmp_path / "proposal.diff"
        )


def test_patch_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    analysis = tmp_path / "analysis.json"
    analysis.write_text('{"summary":"no change"}')
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tool",
            "--analysis",
            str(analysis),
            "--repository",
            str(tmp_path),
            "--output",
            str(tmp_path / "proposal.diff"),
        ],
    )
    apply = Mock(return_value=False)
    monkeypatch.setattr(ai_patch, "apply_proposal", apply)
    ai_patch.main()
    assert apply.call_count == 1


def test_standards_proposals_cannot_change_application_code(tmp_path: Path) -> None:
    with pytest.raises(UnsafePatchError):
        ai_patch.apply_proposal(
            tmp_path,
            Analysis(summary="Fix", patch=PATCH),
            tmp_path / "proposal.diff",
            standards_only=True,
        )


def test_standards_proposal_can_target_only_the_handbook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    patch = PATCH.replace("src/main.py", "standards/python.md")
    monkeypatch.setattr(ai_patch.subprocess, "run", Mock())
    assert ai_patch.apply_proposal(
        tmp_path,
        Analysis(summary="Fix guidance", patch=patch),
        tmp_path / "proposal.diff",
        standards_only=True,
    )
