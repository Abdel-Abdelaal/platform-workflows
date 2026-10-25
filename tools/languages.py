"""Decide which language-specific checks a repository needs, from what it contains.

Language shares come from GitHub's language statistics (the data behind each
repository's language bar), which already exclude vendored and generated code.
Manifests come from tracked files. Nothing in the repository is executed.

The plan drives the shared workflows: which CodeQL languages to analyse, which
language CI packs apply, and which Dependabot ecosystems should be configured.
Languages that are present but cannot be analysed are reported, never dropped.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

# A language counts once it is at least this share of the repository's code.
SIGNIFICANT_SHARE = 0.01

# GitHub linguist name -> CodeQL language. Only languages verified to analyse
# with `build-mode: none` in this fleet are scanned automatically.
CODEQL_AUTOMATIC = {
    "Python": "python",
    "JavaScript": "javascript-typescript",
    "TypeScript": "javascript-typescript",
    "Java": "java-kotlin",
    "Kotlin": "java-kotlin",
}
CODEQL_NOT_AUTOMATIC = {
    "C": "needs a full build for CodeQL (c-cpp)",
    "C++": "needs a full build for CodeQL (c-cpp)",
    "Objective-C": "needs a full build for CodeQL (c-cpp)",
    "Swift": "needs a macOS build for CodeQL (swift)",
    "Go": "CodeQL go uses autobuild; not yet verified in this fleet",
    "Rust": "CodeQL rust not yet verified in this fleet",
    "C#": "CodeQL csharp not yet verified in this fleet",
    "Ruby": "CodeQL ruby not yet verified in this fleet",
}

# Manifest file name -> Dependabot package ecosystem.
MANIFESTS = {
    "pyproject.toml": "uv",
    "requirements.txt": "pip",
    "package.json": "npm",
    "build.gradle": "gradle",
    "build.gradle.kts": "gradle",
    "settings.gradle.kts": "gradle",
    "go.mod": "gomod",
    "Cargo.toml": "cargo",
    "Dockerfile": "docker",
    "Gemfile": "bundler",
}
EXCLUDED_DIRECTORIES = {
    "node_modules",
    "vendor",
    "third_party",
    "dist",
    "build",
    ".venv",
}


@dataclass
class Plan:
    """What the shared workflows should run for one repository."""

    codeql: list[str] = field(default_factory=list[str])
    not_scanned: dict[str, str] = field(default_factory=dict[str, str])
    significant: list[str] = field(default_factory=list[str])
    python_ci: bool = False
    node_ci: bool = False
    gradle_wrapper: bool = False
    dependabot: dict[str, list[str]] = field(default_factory=dict[str, list[str]])


def significant_languages(language_bytes: dict[str, int]) -> list[str]:
    """Languages holding at least SIGNIFICANT_SHARE of the code, largest first."""
    total = sum(language_bytes.values())
    if total == 0:
        return []
    ranked = sorted(language_bytes.items(), key=lambda item: (-item[1], item[0]))
    return [name for name, size in ranked if size / total >= SIGNIFICANT_SHARE]


def manifest_directories(files: set[str]) -> dict[str, list[str]]:
    """Dependabot ecosystem -> directories holding its manifests."""
    found: dict[str, set[str]] = {}
    for name in files:
        path = PurePosixPath(name)
        if EXCLUDED_DIRECTORIES.intersection(path.parts[:-1]):
            continue
        ecosystem = MANIFESTS.get(path.name)
        if ecosystem:
            directory = "/" + str(path.parent) if str(path.parent) != "." else "/"
            found.setdefault(ecosystem, set()).add(directory)
    if any(name.startswith(".github/workflows/") for name in files):
        found.setdefault("github-actions", set()).add("/")
    if any(name.endswith(".tf") for name in files):
        found.setdefault("terraform", set()).add("/")
    return {ecosystem: sorted(dirs) for ecosystem, dirs in sorted(found.items())}


def plan(language_bytes: dict[str, int], files: set[str]) -> Plan:
    """Turn language shares and tracked files into the checks to run."""
    result = Plan(significant=significant_languages(language_bytes))
    codeql: set[str] = set()
    if any(name.startswith(".github/workflows/") for name in files):
        codeql.add("actions")
    for language in result.significant:
        if language in CODEQL_AUTOMATIC:
            codeql.add(CODEQL_AUTOMATIC[language])
        elif language in CODEQL_NOT_AUTOMATIC:
            result.not_scanned[language] = CODEQL_NOT_AUTOMATIC[language]
    result.codeql = sorted(codeql)
    result.python_ci = {"pyproject.toml", "uv.lock"} <= files
    result.node_ci = "package.json" in files and bool(
        {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"} & files
    )
    result.gradle_wrapper = "gradle/wrapper/gradle-wrapper.properties" in files
    result.dependabot = manifest_directories(files)
    return result


def repository_languages(repository: str) -> dict[str, int]:
    """GitHub's language byte counts for OWNER/NAME."""
    output = subprocess.run(
        ["gh", "api", f"repos/{repository}/languages"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout
    return {str(name): int(size) for name, size in json.loads(output).items()}


def tracked_files(root: Path) -> set[str]:
    """Tracked file names, without reading their contents."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return {name for name in result.stdout.decode("utf-8").split("\0") if name}


def main() -> None:
    """Write the plan as JSON and, in Actions, as step outputs and a summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="OWNER/NAME")
    parser.add_argument("--root", type=Path, required=True, help="checked-out repo")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--summary", type=Path)
    arguments = parser.parse_args()
    result = plan(
        repository_languages(arguments.repository), tracked_files(arguments.root)
    )
    arguments.output.write_text(json.dumps(asdict(result), indent=2), encoding="utf-8")
    if arguments.github_output:
        with arguments.github_output.open("a", encoding="utf-8") as outputs:
            outputs.write(f"codeql={json.dumps(result.codeql)}\n")
            outputs.write(f"gradle_wrapper={str(result.gradle_wrapper).lower()}\n")
    if arguments.summary:
        lines = [
            "### Detected languages",
            f"Significant (at least {SIGNIFICANT_SHARE:.0%} of code): "
            f"{', '.join(result.significant) or 'none'}",
            f"CodeQL: {', '.join(result.codeql) or 'none'}",
            *[
                f"- Not scanned by CodeQL: {lang} ({why})"
                for lang, why in result.not_scanned.items()
            ],
        ]
        with arguments.summary.open("a", encoding="utf-8") as summary:
            summary.write("\n".join(lines) + "\n")
    sys.stdout.write(json.dumps(asdict(result)) + "\n")


if __name__ == "__main__":  # pragma: no cover
    main()
