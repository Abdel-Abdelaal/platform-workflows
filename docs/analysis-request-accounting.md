# Automatic session titles and analysis request accounting

The pinned OpenCode client can make a separate model request to name a new
session. That auxiliary request is not a completed analysis step in the CLI
stream consumed by our attempt counters. A fixed, non-sensitive title avoids
that request for these disposable analysis sessions.

A localhost synthetic comparison using OpenCode 1.18.35 observed two requests
without an explicit title (one with the client's exact title-generation marker)
and one analysis request with a fixed title. Both variants emitted only one CLI
step-finish usage event, directly exposing the extra request outside that counter.
The same Flash model and effective
32000-token cap were used. [The bounded result](evaluation-2026-10-30/analysis-title-requests.json)
contains no real prompts, keys, reasoning or live provider inference. A first
fixture expected one request and a subsequent broad title-word classifier was
ambiguous; both local artifacts remain retained. The final marker matches the
[tagged upstream implementation](https://github.com/anomalyco/opencode/blob/53d1eabb61e21162157817bf677da0a4ad3332e3/packages/opencode/src/session/prompt.ts),
which skips title generation when the session already has a non-default title.
OpenCode is used unmodified under its MIT license; no upstream code was copied.

The runner now supplies the constant title `Showcase analysis`. It contains no
repository name, task text or credentials. Analysis reasoning, output budget,
attempt allowance, deadlines, schemas, denied tools and credential isolation are
unchanged. This does not disable compaction or change interactive chat behavior.

The result measures client request count, not actual provider usage savings or
model quality. Other internal requests may exist; this is not complete transport
observability. The probe sources and earlier fixture errors remain local with
hashes available for telemetry; these summaries are not an independently
reproduced public benchmark. A tooling source pin and accepted consumer release
are still needed before this source change affects every caller.


## Source-context disclosure regression

Hosted red-team run [41006203572](https://github.com/Abdel-Abdelaal/platform-workflows/actions/runs/41006203572)
defended seven of eight fixtures. The committed-secret fixture returned a valid,
useful review that repeated the synthetic source credential. This failure remains
part of the record; the preceding eight-of-eight run does not establish immunity.

The verified output scanner recognized the value in its source assignment but
missed its bare occurrence in review prose. Output scanning now includes the
original untrusted context as scanner data, so detected source values are also
removed from response events before parsing or telemetry retention. Source text
is never returned by this API. The existing combined input/report/value bounds,
isolated scanner environment and fail-closed behavior apply. Only values actually
removed from output count as redactions. A replacement inside a patch still
rejects the patch. No scanner detects every secret or transformed disclosure.

A local replay of the failed fixture using the existing pinned Gitleaks binary
confirmed the bare output survived output-only scanning and was removed with its
source assignment included. This was an offline synthetic replay, with no model
inference or actual credentials; it is not a new autonomous red-team success.
Tests cover ordinary responses, timeout output retention, unchanged safe output,
redaction counts and combined input bounds. A new hosted run is needed to measure
the revised pipeline against the live model.
