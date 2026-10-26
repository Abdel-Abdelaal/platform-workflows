# Agent attempt evidence

## Agent batch v1

The shared registry accepts `agent-dispatcher.attempt/v1` records. Each bounded
public batch is an `agent-batch/v1` document with `schema_version: 1`. Up to 25
attempts form one subject, at most one megabyte. The full canonical list of
attempts determines `batch_id` (SHA-256). Record IDs identify individual attempts
across delivery retries. Supported stages are triage, plan, implement, review,
repair, CI repair/review, gate, route and publish.

Retained fields identify the task/repository, run/attempt, provider/harness/model,
effort, difficulty, timing, outcome, prompt/context/output hashes, bounded final
text excerpts, measured usage and gate decisions. Unknown fields are discarded
by an explicit allowlist. Unknown usage remains null; missing counters are not
zero. Provider-reported cost is an estimate, not a billing receipt. Full prompts,
source context and full outputs are not retained by this producer. An excerpt
is at most 2,000 characters; the original hash/length describes the full text.

## Trust and confidentiality

The dispatcher writes local JSONL without signing or publishing. A separate sender
validates its schema, queries fresh GitHub repository metadata, excludes private,
unknown, archived and fork repositories, and rejects PR joins outside the target
repository. Required Gitleaks scanning redacts matched values before any upload.
Scanning is bounded and cannot identify every kind of confidential information.
Malformed records or unavailable scanning fail closed without logging payloads.

Only the account owner's existing authenticated CLI can upload. No new credential
or service is required. The sender runs outside agent/model processes; GitHub and
signing credentials are never added to model children. Private records remain
local and are never sent to this public endpoint. Their existing private workflow
DSSE storage is separate; this endpoint does not claim private agent publication.

Hosted ingestion downloads only an owner-uploaded, hash-named asset from the fixed
platform repository, repeats public classification/schema/redaction checks, and
secret-scans the complete publication subject/predicate. A protected-main workflow
signs the batch using GitHub/Sigstore and archives both JSON and bundle in monthly
`ai-telemetry-YYYY-MM` Releases. The attestation predicate type is this document's
`#agent-batch-v1` URI.

**This attests hosted ingestion of controller-reported data.** It does not assert
that local agents executed on hosted runners, that model claims are correct or
that a hash proves retention of the original text. Consumers must preserve this
source-assurance distinction and verify the workflow, main source ref, subject
digest and predicate type before counting records.

## Sender contract

Use the reviewed platform checkout and an explicitly verified Gitleaks executable.
The normal Python dependency lock applies. For example, in PowerShell:

```powershell
$env:AI_OUTPUT_SECRET_SCANNER = 'D:/trusted-tools/gitleaks.exe'
python -m tools.ai_agent_ingest submit --source D:/showcase/agent-dispatcher/runs/telemetry/attempts-2026-10.jsonl --ledger D:/showcase/work/agent-telemetry-delivery.json
```

The source file is read without executing anything in it. The sender prepares one
batch per invocation, uploads an immutable `agent-input-<hash>.json` asset to a
monthly `ai-agent-incoming-YYYY-MM` prerelease, then dispatches the fixed
`ai-agent-ingest.yml` workflow on main. Input selectors are validated and passed
as arguments/environment data, never interpolated into shell source.

The ledger first stores a pending batch. Later invocations verify a hosted signed
batch before acknowledging its record IDs; a dispatch acknowledgement alone is
not delivery. Failed ingestion is retried using the same input. Immutable final
assets include the ingestion run ID so partial uploads can be retried without
overwriting bytes. Consumers deduplicate individual `record_id` values. A batch
crossing a month boundary keeps its original source month. Local source records
are never deleted by this tool. Failed hosted ingestion opens the standard
failure report rather than silently claiming complete coverage.

The sender should be invoked by the controller host's existing scheduler after
new local records exist. Do not add a model call just to send telemetry. Historical
tasks that ran before instrumentation remain explicitly unmeasured.

## Activation status

The source and workflow require their normal checked PR merge, a real controller
attempt, verified hosted ingestion and dashboard integration before being called
active. Unit-test records are not production evidence. Fleet release/enrollment
rollout is tracked in `CLAUDE_COORDINATION.md` and `CODEX_PROGRESS.md`.
