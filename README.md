# platform-workflows

[![AI telemetry](https://img.shields.io/endpoint?url=https%3A%2F%2Fabdel-abdelaal.github.io%2Fgithub-governance%2Fbadge.json)](https://abdel-abdelaal.github.io/github-governance/)
[![AI red team](https://github.com/Abdel-Abdelaal/platform-workflows/actions/workflows/ai-redteam.yml/badge.svg?branch=main)](docs/ai-security.md#red-team-v1)

Shared GitHub Actions workflows for my repositories. Each service repo calls these
instead of copying CI logic around, so a fix or a new check lands everywhere at once.

This is the "golden path" pattern: a platform team owns how code gets checked and
shipped, and product repos opt in with a few lines of YAML.

## Workflows

| Workflow | What it checks | Called with |
|---|---|---|
| [`security.yml`](.github/workflows/security.yml) | CodeQL, dependency review, secret scanning, actionlint and zizmor | PR, push and schedule through caller |
| [`python-ci.yml`](.github/workflows/python-ci.yml) | format, lint, strict types, branch coverage, dependency audit (pip-audit, plus advisory OSV-Scanner); when the caller installs them: import-linter contracts, deptry, vulture; jscpd duplication at most 3%; optional Sonar | `workflow_call` |
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
    uses: Abdel-Abdelaal/platform-workflows/.github/workflows/pr-title.yml@f06eb74320f169fa6ce3690b0cd44ccfba8f199b # v1.8.0
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

### Attacked on purpose

The [AI red team](.github/workflows/ai-redteam.yml) runs eight attacks against the real
reviewer every week and on every change to it: prompt injection, key and secret
exfiltration, system-prompt leakage, tool execution, review escalation and a
CI-weakening patch. They're mapped to the OWASP Top 10 for LLM Applications in
[docs/ai-security.md](docs/ai-security.md), together with each control and its known
gaps. Results are public in the
[AI red-team results](https://github.com/Abdel-Abdelaal/platform-workflows/issues?q=is%3Aissue+%22AI+red-team+results%22)
issue and signed on the Attestations page. The badge turns red if any attack succeeds.

### Signed AI telemetry

The [public AI observatory](https://abdel-abdelaal.github.io/github-governance/)
calculates metrics from signature-verified records, with a downloadable JSONL
dataset. [Record schema and privacy rules](docs/ai-telemetry.md) describe input
hashes/manifests, per-attempt tokens and latency, validation failures, validated
output, patch/filtering decisions and GitHub publication receipts.

Records are secret-scanned, signed using GitHub/Sigstore attestations and archived
with their bundles as public monthly Release assets in each originating repo.
The provider job remains read-only; only a separate trusted job signs and archives.
Shortlink [review run 40190530711](https://github.com/Abdel-Abdelaal/shortlink/actions/runs/40190530711)
and [audit run 40191001176](https://github.com/Abdel-Abdelaal/shortlink/actions/runs/40191001176)
proved the complete path, including an explicit signed credential-skip record for
fix mode. Collection is prospective and follows caller adoption.
Outcome quality and red-team rates remain unavailable until collected; PR-Agent's
separate trial is outside the isolated-runner dataset.

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

## Maintenance activation

The new shared release carries the corrected JSON prompts, explicit stdin EOF,
reasoning-aware completion/time budgets and code-first bounded context. Provider
analysis installs only locked Python runtime dependencies; hook/test tooling runs
without provider or App credentials. The Python audit covers development tools as
well as runtime packages, so the full toolchain cannot hide behind a clean service
runtime export.

`hooks.yml` validates frozen hooks; native Dependabot updates the central baseline.
`stale.yml` supports dry-run and refuses mutations until the canonical label exists.
`release.yml` uses the maintenance App only after setup/label checks, creates normal
release proposals and moves the platform discovery tag after stable major-one
releases. It has no personal-token fallback. Missing App setup skips explicitly.

Release-please's pinned engine17.6.0 needs `.name.value` in the uv.lock TOML selector;
that selector was tested against real lock data and changes only the root package.
App-based release creation still needs owner setup and a live integration run.

Managed callers pin full platform release commits. Verified telemetry adoption is
visible in the public observatory rather than inferred from configuration. Frozen hook checks
run where a hook configuration is supported; native Dependabot maintains baseline
hook revisions. Stale/release mutations remain explicitly gated on canonical
labels and maintenance App setup. The Python audit includes development tooling.
