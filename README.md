# platform-workflows

Shared GitHub Actions workflows for my repositories. Each service repo calls these
instead of copying CI logic around, so a fix or a new check lands everywhere at once.

This is the "golden path" pattern: a platform team owns how code gets checked and
shipped, and product repos opt in with a few lines of YAML.

## Workflows

| Workflow | What it checks | Called with |
|---|---|---|
| [`security.yml`](.github/workflows/security.yml) | CodeQL, dependency review, secret scanning, actionlint and zizmor | PR, push and schedule through caller |
| [`python-ci.yml`](.github/workflows/python-ci.yml) | format, lint, strict types, branch coverage, runtime dependency audit; optional Sonar | `workflow_call` |
| [`report-failure.yml`](.github/workflows/report-failure.yml) | idempotent issue for scheduled failures | failed scheduled caller |
| [`pr-title.yml`](.github/workflows/pr-title.yml) | PR title follows [Conventional Commits](https://www.conventionalcommits.org/) | `pull_request` |

## Usage

```yaml
# .github/workflows/pr.yml in a service repo
on:
  pull_request:
    types: [opened, edited, synchronize, reopened]

permissions: {}

jobs:
  pr-title:
    uses: Abdel-Abdelaal/platform-workflows/.github/workflows/pr-title.yml@v1
    permissions:
      pull-requests: read
```

## Versioning

Releases are tagged `vX.Y.Z`. The major tag (`v1`) moves to the latest compatible
release, so callers get fixes without editing their workflows. Breaking changes get
a new major tag.

## Standards

See the [engineering handbook](https://github.com/Abdel-Abdelaal/.github/tree/main/standards).
Community policies and templates are inherited from the shared `.github` repo.

## Python quality gates

Call `python-ci.yml@v1` as job `ci` with `contents: read`, then require its real
check names after the first successful consumer run. Inputs: `python-version`
(default 3.12) and `coverage-min` (default 90). Optional SONAR_TOKEN is passed
explicitly; analysis also needs verified sonar-project.properties in the consumer.
The audit exports runtime dependencies from the lockfile and scans them with
pip-audit. Fork PRs never receive provider or deployment credentials.

## Security checks

Call `security.yml@v1` with a JSON `languages` input, such as `["python","actions"]`.
Caller permissions must include contents read, pull-requests write and
security-events write; each job narrows that set. Fork and Dependabot dependency
reviews do not try to post privileged comments. No PR source receives App keys.

Dependency review starts warn-only until 2026-10-31, then enforces high-severity
findings and the approved license list automatically. Review the initial findings
before that date. CodeQL, secret scanning and workflow checks enforce immediately.
The platform runs the same security workflow against itself through a local call.
Only the controlled platform release tags are exempt from SHA pinning.
