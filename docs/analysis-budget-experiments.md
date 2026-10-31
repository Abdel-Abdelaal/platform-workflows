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
