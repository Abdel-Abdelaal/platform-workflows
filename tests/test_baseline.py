import sys
from pathlib import Path

import pytest

from tools.baseline import (
    FILES,
    MAX_FILE_BYTES,
    exceptions,
    main,
    synchronize,
    validate_path,
)


@pytest.fixture
def baseline(tmp_path: Path) -> tuple[Path, Path]:
    source, repository = tmp_path / "source", tmp_path / "repository"
    repository.mkdir()
    for name in FILES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"reviewed baseline\n")
    return source, repository


def test_sync_is_dry_by_default_and_idempotent(baseline: tuple[Path, Path]) -> None:
    source, repository = baseline
    assert set(synchronize(source, repository)) == FILES
    assert not list(repository.iterdir())
    assert set(synchronize(source, repository, apply=True)) == FILES
    assert synchronize(source, repository, apply=True) == []


def test_exceptions_preserve_local_changes(baseline: tuple[Path, Path]) -> None:
    source, repository = baseline
    (repository / ".baseline-ignore").write_text(
        "# reviewed exception\n\n.editorconfig\n"
    )
    (repository / ".editorconfig").write_text("local override")
    assert ".editorconfig" not in synchronize(source, repository, apply=True)
    assert (repository / ".editorconfig").read_text() == "local override"


@pytest.mark.parametrize(
    "entry", ["../escape", ".github/**", "arbitrary.py", "/absolute"]
)
def test_invalid_exception_fails_closed(
    baseline: tuple[Path, Path], entry: str
) -> None:
    _, repository = baseline
    (repository / ".baseline-ignore").write_text(entry)
    with pytest.raises(ValueError, match="exact managed"):
        exceptions(repository)


def test_all_inputs_validated_before_any_write(baseline: tuple[Path, Path]) -> None:
    source, repository = baseline
    (source / "ruff-base.toml").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    with pytest.raises(ValueError, match="size limit"):
        synchronize(source, repository, apply=True)
    assert not list(repository.iterdir())


def test_escape_rejected_without_writing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="escapes"):
        validate_path(tmp_path, "../outside")


def test_cli_dry_run(
    baseline: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    source, repository = baseline
    monkeypatch.setattr(sys, "argv", ["baseline", str(source), str(repository)])
    main()
    assert not list(repository.iterdir())
