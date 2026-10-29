# Advisory AI: local, CI and server use

The runner is locked OpenCode 1.18.35, configured for **Xiaomi MiMo 2.6 Flash** at
the Amsterdam Token Plan endpoint. Both the main and small-model roles use Flash.
There is no fallback to a different model. Source, prompts and output contracts
live here so the same implementation can run locally, in Actions or on a server.

## Credential handling

The caller passes `AI_API_KEY` explicitly as an Actions secret. `AI_BASE_URL` is
a non-secret variable, defaulting to `https://token-plan-ams.xiaomimimo.com/v1`.
No key is stored in source, prompts or artifacts. Missing keys skip with a notice;
fork PRs and Dependabot PRs never receive the key. Local shells use the same names.

In GitHub Actions, a checksum-verified Gitleaks binary scans the fully prepared
model input before the runner receives its provider key: bounded source/handbook,
the PR diff, selected prompt and appended health/current-reference data. The
independent security workflow continues repository-history scanning. Local/server
operators must scan their prepared input and checkout before provider use.
Context includes Python/Terraform, Android Kotlin/Java, JavaScript/TypeScript,
Go/Rust, shell and SQL implementation plus text configuration and UI resources.
Generated build and dependency directories are excluded even when tracked.
Context prioritizes implementation/tests and attaches only standards/*.md from
the handbook, rather than its baseline/workflow bulk. File reads and metadata are
bounded; omitted/truncated files and partial diffs are explicit so absence cannot
be mistaken for a missing control. It includes the AGENTS.md glossary as data and
excludes credential files, executable agent/config/plugin files and symlinks.
Monthly standards review also collects current official documentation and marks
failed retrievals explicitly. Retrieved text is never treated as instructions.

OpenCode starts in a clean temporary directory with `--pure`, isolated config/data
paths, project configuration and external skills disabled, and **every tool denied**.
The model process receives its provider key and necessary OS variables, with no
GitHub or App credential. Before validation or attempt recording, the actual
provider credential is replaced in response events, including nested JSON strings
and ordinary JSON escapes. This exact-value guard also covers failed attempts;
it is not a general confidential-data detector. Gitleaks still gates input and
evidence uploads. Pydantic validates and bounds the returned JSON.
Context is delimited stdin data, with explicit EOF. It stays outside the command
line and does not consume an internal file-attachment read step. OpenCode1.18.35
reads noninteractive stdin before starting; inheriting an open stdin can hang.
A real child-process regression checks that large context reaches EOF. At most
three attempts run, each bounded to ten minutes for whole-repository audits. The
32768-token completion budget includes reasoning as well as JSON output. With the
whole repository plus handbook (~155k characters), Flash spent all 32k tokens on
reasoning and returned no text, so audits failed with `json_invalid`.

**Reasoning switch.** Measured against the Token Plan endpoint on 2026-10-25:
`thinking: {"type": "disabled"}` drops reasoning tokens to 0, while
`reasoning_effort` and `enable_thinking` are ignored. `response_format: json_object`
is served; strict `json_schema` is not. Whole-repository modes (audit, fix,
standards) run with reasoning disabled and JSON mode on (`--thinking disabled`);
diff review keeps reasoning, but can also exhaust the completion budget. In four
full-context reproductions without reasoning, three produced validated output within the three
attempts. The remaining schema failures were invented comment fields and too many
comments; those prompts now require an empty `comments` array, since only the
summary is published. **Trade-off:** without reasoning, Flash is shallower (it
missed a simple primality check that it gets right with reasoning), so audit
findings need human verification. They are advisory anyway.
Output objects retain their smaller schema limits.
Logs expose only exception categories, never raw provider
output. These boundaries reduce prompt-injection impact; they do not prove AI correctness.

The tooling and reusable workflows are implemented and tested. Fleet activation
is tracked by consumer PRs; a configured file is not evidence of a successful run.

### Evidence-driven retries

The runner retains the configured thinking setting, completion budget and
per-attempt deadline. It does not silently disable reasoning to obtain an answer.
A completed provider step reporting `length` with no answer text is recorded as
`CompletionBudgetExhaustedError` and stops that analysis. Repeating the identical
request under the same exhausted budget is skipped; the workflow fails explicitly
and retains usage, finish reasons and the failed attempt. This is not a successful
review, a time cutoff, or a checkpoint for resuming provider reasoning.
A valid JSON answer is still accepted when the provider reports `length`.
Missing finish metadata and ordinary malformed answers retain the existing
maximum of three attempts.

Recoverable schema failures receive at most five diagnostics, each with at most
six location components. Diagnostics contain only allowlisted schema field names
and validation error codes. Unknown field names and codes become fixed markers;
model values, messages, repository paths and raw output never become retry
instructions. Scanner failure remains terminal, and tools/privileged credentials
remain unavailable to the model.

The motivation was the shortlink PR64 advisory run
[40942984936](https://github.com/Abdel-Abdelaal/shortlink/actions/runs/40942984936):
three completed attempts returned no answer, each reporting `length`. Together
they consumed 96,002 reported output tokens, including 96,000 reasoning tokens,
and about 19 minutes of inference. New regression fixtures reproduce that event
shape without calling a provider. Before this change the fixture ran three
attempts; afterward it stops after one and records the specific cause. This is
replay evidence for retry behavior, not proof of improved model correctness or a
measurement of live savings. The historical failed run is unchanged.

## Workflows

| Workflow | Purpose | Write capability |
| --- | --- | --- |
| `ai-review.yml` | PR diff review | separate publisher updates one summary and notice annotations |
| `ai-audit.yml` | weekly whole-repo coding audit | health issue and bounded proposed tickets |
| `ai-fix.yml` | one focused proposal from the health report | tested patch, then one draft App-authored PR |
| `ai-standards-review.yml` | monthly handbook/current-doc comparison | standards-only draft PR |

### Audit proposals

Audits may return up to 20 structured findings alongside their summary. Each
validated finding has a short title, category, stable rule, severity, relative
file path, evidence and suggested fix. Legacy outputs without findings remain
valid; the publisher does not guess tickets from prose. Schema validation does
not establish that the model's claim is correct.

The separate publisher creates at most five new issues per run, highest severity
first, with exactly `agent:proposed` and one of `bug`, `security`, `documentation`
or `task`. It never adds `agent:ready`. Abdel verifies a proposal and adds that
label himself before agent-dispatcher can run. Model instructions in issue text
have no authority; HTML, Markdown and mentions are neutralized in audit prose.

A versioned SHA-256 marker identifies repository, category/rule, relative path
and normalized title. The publisher paginates open and closed issues and only
accepts markers at the start of its own GitHub Actions bot issues. It preserves
every closed proposal, including not-planned/wontfix, without reopening it.
Changing a title's meaning or rule can create a new identity; deduplication is
deterministic rather than semantic. Repeated findings within a run count once.

The health issue retains every finding with a ticket reference or a cap deferral;
bounded excerpts keep it within GitHub's body limit. Publication receipts retain
ticket numbers, fingerprints and created/existing/closed/deferred decisions,
including successful writes before a later failure. No additional secret or
dispatcher permission is needed. Hosted activation requires the separately
reviewed executable tooling pin; source code alone does not activate proposals.

Every caller pins the workflow release commit. The workflow itself pins a separate,
reviewed tooling commit containing its scripts, prompts and lockfiles; callers cannot
choose executable tooling through an input. Internal relative workflow calls are
tied to the release commit. Do not use `secrets: inherit`.
The wrapper's permission ceiling is contents write, actions read, issues write,
pull-requests write, checks write, id-token write and attestations write. Individual
jobs narrow it to their purpose. Only the separate telemetry job receives archive
and signing writes; the provider job keeps contents/issues read.
Review and audit only need the API key. Fix/standards jobs additionally need the
automation App ID/key and skip explicitly until those are configured.

## Advisory means no merge gate

Review findings use Conventional Comments wording marked non-blocking, a sticky
summary and **notice annotations on a neutral check**. The publisher never creates
approval events or unresolved review threads. That matters because the repository
correctly requires review threads to be resolved before merging. AI job/check names
must never be added to required branch checks.

## Fix boundaries

Model output is a small unified diff, not a command or executable instruction.
Only Python in `src/` and `tests/`, Markdown in `docs/` and `standards/`, and README
are allowed. Workflow/config/agent/credential changes, traversal, symlinks, binary
patches, renames and executable modes are rejected. Proposals are capped at five
files and 400 lines. Standards review is further restricted to `standards/`.

A separate job applies and tests the candidate **without AI or App credentials**.
Only after it passes does another job mint a narrowly scoped App token, apply the
same validated proposal without executing source, and open/update one draft PR.
It does not merge. Missing App setup cannot silently fall back to a personal token.

## Local/server commands

From this repository, with Node 18+ and Python 3.12/uv installed:

```sh
set -e
uv sync --locked
npm ci
export PATH="$PWD/node_modules/.bin:$PATH"
export AI_BASE_URL=https://token-plan-ams.xiaomimimo.com/v1
# Set AI_API_KEY through your shell or secret manager, never a committed file.
gitleaks git /absolute/path/to/repo --redact --exit-code 1
uv run python -m tools.ai_context --repository /absolute/path/to/repo --output /tmp/context.md
uv run python -m tools.ai_runner --context /tmp/context.md --prompt prompts/audit.md --output /tmp/analysis.json
```

On a server, use those same commands from a scheduler. Keep report artifacts private
until reviewed, give publisher credentials only to the publishing process, and keep
AI output advisory. Raw key files are not part of this interface or repository.

## Evidence and tests

The boundary tests cover schema failures, forged inline locations, path traversal,
workflow/credential edits, unsafe modes, source filtering, environment isolation,
idempotent comments/issues and real Git patch application. The platform runs its
own lint, strict types, tests/coverage, dependency audit and security workflows.
The live provider smoke test uses Flash through the same isolated runner.

See [ADR 0004](decisions/0004-isolate-ai-and-keep-feedback-advisory.md).

The hosted workflow scans the fully prepared input, including handbook data,
immediately before analysis.
It scans generated evidence before upload, then joins publication receipts and job
outcomes in a separate signing job. Records and Sigstore bundles are archived as
public Release assets. See [AI telemetry](ai-telemetry.md) for privacy boundaries,
querying and verification. This is prospective collection, not historical coverage.
Only `standards/*.md` enters the context; handbook files are data and are never
executed. Provider jobs install locked runtime dependencies with `--no-dev`.
The separate hook validation and test jobs install developer tools without provider
or App credentials. CI audits runtime and default development dependencies.
