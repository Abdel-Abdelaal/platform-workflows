# Language coverage

Every repository gets checks for the languages it actually contains, without
anyone hand-maintaining a list. The fleet-wide policy (which tool checks which
language) is in the handbook:
[standards/languages.md](https://github.com/Abdel-Abdelaal/.github/blob/main/standards/languages.md).

## Detection

[`tools/languages.py`](../tools/languages.py) reads GitHub's language statistics
(the repository's language bar, which already excludes vendored and generated
code) and the tracked file list. It never runs repository code. It outputs:

- **CodeQL languages:** every language that is at least 1% of the code and that
  CodeQL can analyse without a build (`python`, `javascript-typescript`,
  `java-kotlin`), plus `actions` whenever workflows exist.
- **Not scanned, with the reason:** for example C/C++ (needs a full build) or
  Go/Rust (not yet verified in this fleet). These appear in the job summary, so
  silence is never mistaken for coverage.
- **CI packs:** Python CI when `pyproject.toml` + `uv.lock` exist, Node CI when
  `package.json` + a lockfile exist, and Gradle wrapper validation when a Gradle
  wrapper exists.
- **Expected Dependabot ecosystems** and their directories, skipping vendored paths.

## Reusable workflows

| Workflow | Languages | Blocks merges on |
|---|---|---|
| [`lint.yml`](../.github/workflows/lint.yml) | all (super-linter slim: ktlint, ESLint, Prettier, ShellCheck, shfmt, hadolint, tflint, yamllint, markdownlint, ruff and more) | lint errors in files the PR changes. A scheduled `full-scan: true` run reports the whole-repo backlog without failing. |
| [`python-ci.yml`](../.github/workflows/python-ci.yml) | Python (uv projects) | Ruff, strict Pyright, pytest + coverage, import contracts, deptry, vulture, jscpd, pip-audit |
| [`node-ci.yml`](../.github/workflows/node-ci.yml) | TypeScript / JavaScript | lockfile install (install scripts off by default), the project's `lint`, `typecheck` and `test` scripts, production dependency audit |
| [`security.yml`](../.github/workflows/security.yml) | every language | CodeQL per language, dependency review, secrets, workflow analysis |

Callers:

```yaml
jobs:
  lint:
    uses: Abdel-Abdelaal/platform-workflows/.github/workflows/lint.yml@<release-sha> # vX.Y.Z
    permissions:
      contents: read
    with:
      exclude: '^(third_party|vendor)/'   # optional: inherited code
```

Python linting in `lint.yml` deliberately runs only ruff. Formatting, typing and
the stricter rule set come from `python-ci.yml`, so the two never disagree.
