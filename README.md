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
    uses: Abdel-Abdelaal/platform-workflows/.github/workflows/pr-title.yml@c047928d7555f1f9e6e2ab56e6e9d3bfa79cdc2c # v1.2.0
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

## Tested advisory AI

The [AI integration](docs/ai.md) uses locked OpenCode and Xiaomi MiMo 2.6 Flash.
Review and audit jobs treat source as data in an isolated process without GitHub
credentials; separate publishers produce neutral notices and idempotent reports.
Fixes are bounded patches tested without provider/App credentials, then proposed
as draft PRs. AI never approves, merges or becomes a required check.

Reusable entry points are `ai-review.yml`, `ai-audit.yml`, `ai-fix.yml` and
`ai-standards-review.yml`. Pin their release commit; executable tooling is fixed to a separately reviewed
commit inside the workflow. Explicitly pass only the named secrets needed by the mode.

## Validate the platform itself

```sh
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest --cov --cov-branch --cov-report=xml --cov-report=term-missing
```

The platform runs its own reusable Python and security workflows. Tests exercise
prompt-injection boundaries, output contracts, credential isolation, source/path
filters, idempotent publishing and actual Git patch application. npm's lockfile
pins the coding CLI and native packages; Dependabot monitors npm, uv and Actions.

## Python quality gates

Call `python-ci.yml` pinned to the reviewed release commit SHA as job `ci` with `contents: read`, then require its real
check names after the first successful consumer run. Inputs: `python-version`
(default 3.12) and `coverage-min` (default 90). Optional SONAR_TOKEN is passed
explicitly; analysis also needs verified sonar-project.properties in the consumer.
The audit exports runtime dependencies from the lockfile and scans them with
pip-audit. Fork PRs never receive provider or deployment credentials.

## Security checks

Call `security.yml` pinned to the reviewed release commit SHA with a JSON `languages` input, such as `["python","actions"]`.
Caller permissions must include contents read, pull-requests write and
security-events write; each job narrows that set. Fork and Dependabot dependency
reviews do not try to post privileged comments. No PR source receives App keys.

Dependency review starts warn-only until 2026-10-31, then enforces high-severity
findings and the approved license list automatically. Review the initial findings
before that date. CodeQL, secret scanning and workflow checks enforce immediately.
The platform runs the same security workflow against itself through a local call.
Every remote action and workflow is SHA-pinned, including our own releases.

Managed callers pin release commit SHAs; Dependabot proposes reviewed updates.
The `v1` tag remains available for discovery, while fleet execution is reproducible.

## Advisory AI maintenance

Same-repository PRs receive an isolated MiMo 2.6 Flash review; fork and Dependabot
PRs skip. Findings are non-blocking summaries and neutral notice annotations.
Weekly audits maintain one health issue. A bounded, tested draft fix PR is possible
only after the automation App is configured; otherwise that step skips explicitly.
No AI check is required for merging, and no AI workflow can merge or approve.
See [the isolation design](https://github.com/Abdel-Abdelaal/platform-workflows/blob/main/docs/ai.md).

## Reviewed maintenance workflows

`conformance.yml` inspects tracked policy configuration as data using immutable,
tested tooling; it never executes checked-out repository code. `baseline-sync.yml`
prepares only allowlisted files and opens a normal PR on `bot/baseline-sync`.
It skips explicitly until the automation App is configured. Because the managed
baseline includes a Scorecard workflow, the narrowly repository-scoped token needs
contents, pull-requests and workflows write permissions. No baseline job can merge.
AI workflows use the same reviewed tooling commit, including bounded JSON retries
and sanitized failure handling. Consumers must upgrade their pinned workflow SHA
to obtain these changes; a moving tag does not change an existing pinned caller.
