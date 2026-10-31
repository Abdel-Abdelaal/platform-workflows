# Explicit analysis budget experiments

This source prepares the frozen output-budget/deadline study. It does not add a
live-dispatch workflow, change production callers or establish a quality gain.
Do not invoke it with a real key through an ad hoc launcher. A real study still
needs a reviewed trusted workflow, frozen scanned inputs and signed evidence.

The runner CLI accepts an explicit `--experiment-profile` of `32000-600`,
`32000-3600`, `131072-600` or `131072-3600` for that future trusted workflow.
It requires an evidence record, a well-formed nonempty input manifest and thinking
enabled before invoking analysis. Refused manifests retain the intended profile
and an evidence-gap record. Omitting the option preserves production defaults.
This CLI preparation alone does not authorize a live local launcher or establish
that the endpoint accepts every requested profile.
The manifest preflight checks structure; it does not authenticate source entries
or bind them to prepared input bytes. The future trusted workflow must freeze and
verify context, prompt, manifest and diff hashes before invoking this CLI.

## Trusted workflow

`.github/workflows/ai-budget-study.yml` is that workflow. It runs only by manual
dispatch from `main`. Its inputs are frozen in `docs/budget-study-inputs.json`:
the review of agent-dispatcher#48 at pinned base, head and handbook commits, the
review prompt, and the SHA-256 of the exact context, manifest, diff and prompt
bytes. Each run rebuilds the inputs with `tools.ai_context` and
`tools.budget_study verify` stops it before any provider call if a hash differs.

With `live` unset (the default) the run only builds and verifies inputs and
reports every condition as unattempted; the provider key isn't exposed. With
`live` set, it runs each of the four profiles once in a random order seeded by
the run id and attempt, with thinking enabled and the exact Amsterdam Token Plan
endpoint. If a profile ends without valid output within 120 seconds, the provider
refused it (quota, credentials or endpoint), so the run stops and records the
rest as unattempted instead of retrying.

The summary lists every planned condition with fixed-shape metadata: status,
exit categories, durations, finish reasons, response hashes and usage totals,
with no response text. Correctness stays "awaiting independent adjudication".
Records, analyses, the ledger and the summary are secret-scanned with the pinned
gitleaks, then attested and uploaded. Nothing is published if the scan fails.
Changing the prompt or any frozen input needs a reviewed change to the spec.

The trusted Python caller can explicitly pass an ExperimentBudget to analyze.
Only `output_tokens` values of 32000 or 131072 crossed with `timeout_seconds`
values of 600 or 3600 are
accepted; booleans and other limits are rejected. The normal interface still uses
its existing 32768 declaration, 600-second timeout and three analysis attempts.
The pinned client currently caps ordinary output at 32000.
Ambient experimental output overrides are not inherited into the default worker.

Experimental mode requires the exact Amsterdam Token Plan endpoint, thinking
requested explicitly as enabled, an active telemetry record, and a configured
output secret scanner. It sets
both the model output declaration and the OpenCode global cap, so the latter
cannot silently keep the request at 32000. Both model roles remain the same Flash
model; tool denial and exclusion of GitHub/App credentials remain in force.

Each experimental invocation gets one analysis-process attempt. That is not a
promise of one underlying HTTP request: internal retries and auxiliary SDK calls
are not fully measured. The fixed-title correction is included before a real study. Existing completion-budget, schema, output-scanning and
error-handling rules remain active. Failures are retained, not converted into
successful results or automatic quota resets. A caller must stop the study when
allowance is unavailable; this library preparation does not implement that study
controller or silently retry another profile.

The telemetry configuration records the requested output cap, process timeout
and attempt count. Correctness is marked awaiting independent adjudication.
A valid JSON analysis alone is not a correctness or coding-quality result.
Preflight scanner failure retains the intended profile and an evidence-gap reason
without executing the provider.

Offline tests verify all four profiles, endpoint/thinking refusal, credential
isolation, mandatory scanning, one-process behavior, configuration provenance and
unchanged default behavior. A local dummy-only pinned-client probe also confirmed
that the four controlled configurations emit the requested 32000/131072 `max_tokens`
and `thinking: {type: enabled}`. Its subprocesses used a 60-second synthetic deadline; it
therefore does not demonstrate real 600/3600-second execution or endpoint acceptance.
The initial one-request fixture assumption failed because of automatic session
naming; that result is retained separately. No live inference was used.

Before publication of comparative results, freeze the task/context/prompt receipt,
randomize condition order, provide sufficient whole-job headroom, retain failed
and unattempted conditions, and apply the same independent correctness criteria
to every result. Do not compare this small pilot with unrelated leaderboard scores
or resume unbound failed tasks. No paid endpoint, purchase or reset credit is used.
