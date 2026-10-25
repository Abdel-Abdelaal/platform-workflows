import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import languages

ELLO_SHARES = {
    "Kotlin": 81_930,
    "JavaScript": 10_110,
    "C++": 2_140,
    "TypeScript": 1_960,
    "Python": 1_810,
    "Java": 560,
    "Rust": 40,
}


def test_significant_languages_use_a_one_percent_share() -> None:
    assert languages.significant_languages(ELLO_SHARES) == [
        "Kotlin",
        "JavaScript",
        "C++",
        "TypeScript",
        "Python",
    ]


def test_empty_repository_has_no_languages() -> None:
    assert languages.significant_languages({}) == []


def test_android_repo_scans_kotlin_and_reports_cpp_as_not_scanned() -> None:
    result = languages.plan(
        ELLO_SHARES,
        {
            ".github/workflows/ci.yml",
            "settings.gradle.kts",
            "gradle/wrapper/gradle-wrapper.properties",
        },
    )
    assert result.codeql == [
        "actions",
        "java-kotlin",
        "javascript-typescript",
        "python",
    ]
    assert result.not_scanned == {"C++": "needs a full build for CodeQL (c-cpp)"}
    assert result.gradle_wrapper is True
    assert result.python_ci is False


def test_python_ci_needs_a_uv_project_and_node_ci_a_lockfile() -> None:
    python_only = languages.plan({"Python": 100}, {"pyproject.toml", "uv.lock"})
    assert (python_only.python_ci, python_only.node_ci) == (True, False)
    unlocked_node = languages.plan({"TypeScript": 100}, {"package.json"})
    assert unlocked_node.node_ci is False
    locked_node = languages.plan(
        {"TypeScript": 100}, {"package.json", "pnpm-lock.yaml"}
    )
    assert locked_node.node_ci is True


def test_dependabot_ecosystems_skip_vendored_directories() -> None:
    files = {
        "package.json",
        "web/package.json",
        "node_modules/x/package.json",
        "app/build.gradle.kts",
        "Dockerfile",
        "infra/main.tf",
        ".github/workflows/ci.yml",
    }
    assert languages.manifest_directories(files) == {
        "docker": ["/"],
        "github-actions": ["/"],
        "gradle": ["/app"],
        "npm": ["/", "/web"],
        "terraform": ["/"],
    }


def test_main_writes_plan_outputs_and_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        languages, "repository_languages", Mock(return_value={"Python": 10, "Go": 90})
    )
    monkeypatch.setattr(
        languages, "tracked_files", Mock(return_value={".github/workflows/a.yml"})
    )
    output, github_output, summary = (
        tmp_path / "plan.json",
        tmp_path / "out",
        tmp_path / "summary.md",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "languages",
            "--repository",
            "owner/name",
            "--root",
            str(tmp_path),
            "--output",
            str(output),
            "--github-output",
            str(github_output),
            "--summary",
            str(summary),
        ],
    )
    languages.main()
    assert json.loads(output.read_text())["codeql"] == ["actions", "python"]
    assert 'codeql=["actions", "python"]' in github_output.read_text()
    assert "Not scanned by CodeQL: Go" in summary.read_text(encoding="utf-8")
