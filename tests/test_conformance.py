# Tests execute only fixed Git commands in isolated temporary repositories.
# ruff: noqa: S603, S607
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.conformance import (
    REQUIRED,
    inspect,
    main,
    safe_read,
    tracked_files,
    workflow_findings,
)

SHA = "a" * 40


def workflow(reference: str, event: str = "[pull_request]") -> str:
    return f"on: {event}\npermissions: {{}}\njobs:\n  check:\n    uses: {reference}\n"


@pytest.mark.parametrize(
    "ref",
    [f"owner/repo/.github/workflows/check.yml@{SHA}", "./.github/workflows/check.yml"],
)
def test_pinned_and_local_references_pass(ref: str) -> None:
    assert workflow_findings("workflow.yml", workflow(ref)) == []


@pytest.mark.parametrize(
    "ref",
    [
        "owner/repo@main",
        "owner/repo@v1",
        "docker://image:latest",
        "${{ inputs.ref }}",
        f"owner/repo@{SHA}extra",
    ],
)
def test_every_remote_reference_is_immutable(ref: str) -> None:
    assert "full commit SHA" in workflow_findings("workflow.yml", workflow(ref))[0]


@pytest.mark.parametrize(
    "events",
    [
        "pull_request_target",
        "[pull_request, pull_request_target]",
        "{pull_request_target: {}}",
    ],
)
def test_privileged_events_rejected_for_all_yaml_forms(events: str) -> None:
    assert (
        "forbidden"
        in workflow_findings("workflow.yml", workflow(f"owner/repo@{SHA}", events))[0]
    )


def test_nested_step_references_and_inherited_secrets_checked() -> None:
    text = (
        "on: push\npermissions: {}\njobs:\n  check:\n"
        "    secrets: inherit\n    steps:\n      - {uses: 'owner/repo@main'}\n"
    )
    assert len(workflow_findings("x", text)) == 2


def test_default_token_permissions_rejected() -> None:
    assert (
        "permissions"
        in workflow_findings(
            "x",
            workflow(f"owner/repo@{SHA}").replace(
                "permissions: {}", "permissions: write-all"
            ),
        )[0]
    )


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    for name in REQUIRED:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("## Glossary\n", encoding="utf-8")
    (tmp_path / ".github/dependabot.yml").write_text(
        "updates:\n  - package-ecosystem: github-actions\n"
        "    cooldown:\n      default-days: 14\n",
        encoding="utf-8",
    )
    return tmp_path


def test_valid_repository_and_missing_file(repository: Path) -> None:
    assert inspect(repository, set(REQUIRED)) == []
    assert (
        "required tracked file" in inspect(repository, set(REQUIRED) - {"LICENSE"})[0]
    )


def test_untracked_files_do_not_satisfy_requirements(repository: Path) -> None:
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    assert "README.md" not in tracked_files(repository)
    subprocess.run(
        ["git", "-C", str(repository), "add", "."], check=True, capture_output=True
    )
    assert tracked_files(repository) == set(REQUIRED)


@pytest.mark.parametrize("days", [0, 13])
def test_cooldown_cannot_be_shortened(repository: Path, days: int) -> None:
    path = repository / ".github/dependabot.yml"
    path.write_text(path.read_text().replace("14", str(days)))
    assert "cooldown" in inspect(repository, set(REQUIRED))[0]


def test_each_ecosystem_needs_its_own_cooldown(repository: Path) -> None:
    path = repository / ".github/dependabot.yml"
    path.write_text(path.read_text() + "  - package-ecosystem: uv\n")
    assert inspect(repository, set(REQUIRED))


def test_glossary_hooks_and_python_lockfile(repository: Path) -> None:
    (repository / "AGENTS.md").write_text("# No glossary\n")
    (repository / ".pre-commit-config.yaml").write_text("repos:\n  - rev: v1\n")
    (repository / "pyproject.toml").write_text('[project]\nname="sample"\n')
    findings = inspect(
        repository, {*REQUIRED, ".pre-commit-config.yaml", "pyproject.toml"}
    )
    assert len(findings) == 4


def test_invalid_workflow_fails_closed(repository: Path) -> None:
    name = ".github/workflows/bad.yml"
    path = repository / name
    path.parent.mkdir()
    path.write_text("jobs: [not-a-mapping]\n")
    assert "invalid YAML" in inspect(repository, {*REQUIRED, name})[0]


def test_policy_file_cannot_escape_repository(repository: Path) -> None:
    with pytest.raises(ValueError, match="regular files"):
        safe_read(repository, "../outside")


def test_cli_exit_status(
    repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["conformance", str(repository)])
    monkeypatch.setattr(
        "tools.conformance.tracked_files", Mock(return_value=set(REQUIRED))
    )
    assert main() == 0
    assert "0 violation" in capsys.readouterr().out


def test_local_hooks_do_not_need_remote_revisions(repository: Path) -> None:
    name = ".pre-commit-config.yaml"
    (repository / name).write_text(
        "repos: [{repo: local}, {repo: meta}, {repo: https://example.com/hooks, rev: "
        + SHA
        + "}]"
    )
    assert inspect(repository, {*REQUIRED, name}) == []


def test_invalid_steps_fail_closed(repository: Path) -> None:
    name = ".github/workflows/invalid.yml"
    (repository / name).parent.mkdir()
    (repository / name).write_text(
        "on: push\npermissions: {}\njobs: {test: {steps: invalid}}"
    )
    assert inspect(repository, {*REQUIRED, name})


def test_invalid_configuration_cli_fails(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["conformance", str(repository)])
    monkeypatch.setattr(
        "tools.conformance.tracked_files", Mock(return_value=set(REQUIRED))
    )
    (repository / ".github/dependabot.yml").write_text("updates: invalid")
    assert main() == 1
