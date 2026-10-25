# AI telemetry

Schema version 1 records each isolated analysis call and its bounded retries.
Activation requires the telemetry workflow release and a verified hosted run;
adding these tools alone does not activate collection.

## Record v1

`identity` holds repository, run ID and attempt, event, caller workflow, PR number,
head SHA, mode, platform release and executable tooling commit. `record_id` is a
UUID. When supplied by CI, handbook and actual source checkout commits identify
the snapshots independently of a PR's head commit. Missing values are unknown.
UTC start/end timestamps cover the analysis; finalization has its own time.
`configuration` records thinking and JSON settings, prompt name/hash, system prompt
hash, context hash/character count and glossary availability. `context_manifest`
lists included, truncated and omitted eligible source files, including handbook
files. Excluded credential/configuration files are never read into context.
The production workflow supplies the exact manifest. Local calls without one, or
with a damaged manifest, set `configuration.manifest_complete` to false and use
`present_in_context` estimates; omitted files remain unknown in that fallback.
The repository checkout SHA and context hash identify input; raw source is not
duplicated. A truncated context cannot be interpreted as a complete repository.

`attempts` holds elapsed seconds, exit categories, validation types/field locations,
bounded response text (100,000 characters), its full digest and truncation flag,
OpenCode usage components and finish reasons. Response text is untrusted data.
The actual provider credential is redacted before validation or recording, including
nested JSON escapes. Such responses may be normalized when redaction requires
decoding nested JSON. Exact-value redaction does not detect other confidential data;
the hosted evidence scanner remains a separate fail-closed upload gate.
Validation errors exclude offending inputs, messages and context. Retries append
the system prompt to the original prompt; failed responses never become prompts.
Each attempt hashes its actual prompt, including the retry suffix. Diff hash and
character count are recorded independently of the context digest.
The validated `analysis` retains summary, proposed comments and patch.
`findings` records proposed/eligible/dropped counts and eligible locations.
`patch_check` records accepted paths or rejection by the path/size validator; it
does not claim the patch applied or passed tests. `job_results` supplies subsequent
test/proposal job outcomes. `publication` contains actual publisher receipts with
comment/check/issue IDs; absence is explicitly `not_published`.
If the summary was posted but check creation failed, a `partially_published`
receipt preserves the comment ID. Invalid incoming record/receipt shapes become
explicit evidence gaps or invalid-receipt counts instead of preventing archival.

### OpenTelemetry vocabulary

Use the current [GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai):
`gen_ai.operation.name`, `gen_ai.provider.name`, `gen_ai.request.model`,
`gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
`gen_ai.usage.reasoning.output_tokens`, `gen_ai.usage.cache_read.input_tokens`,
`gen_ai.usage.cache_write.input_tokens`, `gen_ai.response.finish_reasons` and
`server.address`. These conventions are still in development; v1 freezes the
chosen spelling rather than silently changing historical records. `gen_ai.system`
is an older spelling; the current provider attribute replaces it.
Missing token counts mean unavailable, not zero. Provider component counts are
retained separately to make normalization auditable. OpenCode subtracts cached
input and reasoning from its input/output fields; add these subsets back for
OTel totals ([pinned source](https://github.com/anomalyco/opencode/blob/53d1eabb61e21162157817bf677da0a4ad3332e3/packages/opencode/src/session/session.ts)). No monetary cost is
inferred from token counts under a subscription plan.

## Storage and verification

See [ADR 0007](decisions/0007-durable-ai-telemetry.md). Each repo archives uniquely
named records and their Sigstore bundles as assets of a monthly
`ai-telemetry-YYYY-MM` prerelease. These do not expire like Actions artifacts.
They remain publicly downloadable until an authorized user explicitly deletes
them. A signature detects modification; it does not prevent deletion or prove
model correctness. The same evidence has a 90-day Actions artifact copy.

The attestation predicate type is
`https://github.com/Abdel-Abdelaal/platform-workflows/blob/main/docs/ai-telemetry.md#record-v1`.
The compact predicate identifies the schema, record, run and status. The signed
subject digest binds the entire JSON record, including outputs and decisions.
Use `gh attestation verify ai-<run>-<attempt>-<mode>.json --repo OWNER/REPO
--signer-workflow Abdel-Abdelaal/platform-workflows/.github/workflows/ai.yml
--predicate-type https://github.com/Abdel-Abdelaal/platform-workflows/blob/main/docs/ai-telemetry.md#record-v1`.
The custom predicate flag is required; the CLI defaults to SLSA provenance.
Inspect the trusted signer/workflow identity. Public attestations are also
listed on each repository's Attestations page.

Download a monthly release with `gh release download ai-telemetry-2026-10
--repo OWNER/REPO --pattern 'ai-*.json'`. Query the resulting JSON with `jq` or
load newline-delimited aggregate records into DuckDB. Never execute content from
records or feed it back into a model as instructions.

## Privacy and trust boundaries

Never collect keys, tokens, environment dumps or provider URL credentials/query
strings. Identity uses a fixed allowlist. Complete prepared inputs are scanned
before provider use, including source/handbook and appended external data.
Independent CI retains history scanning. Scan generated evidence with the same checksum-verified Gitleaks
binary before any upload; a finding blocks publication. Raw model output stays
out of CI logs. Artifact/release/attestation publishing runs trusted tooling in a
separate job that does not execute analyzed source. Read-only analysis jobs never
receive the archive writer's GitHub permissions.
The signer downloads only artifact IDs returned by the trusted analysis and
publisher jobs. It does not merge artifacts selected by a name glob, so unrelated
artifacts from a patch-test job cannot substitute telemetry input.

GitHub cannot grant write/OIDC permissions to fork PRs or Dependabot PR workflows;
those must not receive the provider key. No provider run occurs there. Credential
skips and pre-run failures are represented when the trusted finalizer is allowed
to run; cancelled/terminated runners can leave gaps. Collection is prospective;
historical runs did not retain usage and cannot be reconstructed accurately.

Outcome collectors can join repository + PR number + head SHA + comment ID to
measure merges, changed flagged lines and reactions, or draft PR lifecycle. Until
collected, those values remain unknown. Red-team/PR-Agent measurements require
their own instrumentation; never infer them from isolated-runner records.
