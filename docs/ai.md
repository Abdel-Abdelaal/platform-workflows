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

In GitHub Actions, a checksum-verified Gitleaks binary scans the source before
the provider key is supplied. Local/server operators must scan the checkout first.
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
GitHub or App credential. Pydantic validates and bounds the returned JSON.
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
diff review keeps reasoning, which it can afford. In four full-context
reproductions without reasoning, three produced validated output within the three
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

## Workflows

| Workflow | Purpose | Write capability |
|---|---|---|
| `ai-review.yml` | PR diff review | separate publisher updates one summary and notice annotations |
| `ai-audit.yml` | weekly whole-repo coding audit | separate publisher maintains one health issue |
| `ai-fix.yml` | one focused proposal from the health report | tested patch, then one draft App-authored PR |
| `ai-standards-review.yml` | monthly handbook/current-doc comparison | standards-only draft PR |

Every caller pins the workflow release commit. The workflow itself pins a separate,
reviewed tooling commit containing its scripts, prompts and lockfiles; callers cannot
choose executable tooling through an input. Internal relative workflow calls are
tied to the release commit. Do not use `secrets: inherit`.
The complete permission set required by the wrapper is contents read, issues write,
pull-requests write and checks write; individual jobs narrow it to their purpose.
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

The hosted workflow also scans the protected handbook snapshot before analysis.
Only `standards/*.md` enters the context; handbook files are data and are never
executed. Provider jobs install locked runtime dependencies with `--no-dev`.
The separate hook validation and test jobs install developer tools without provider
or App credentials. CI audits runtime and default development dependencies.
