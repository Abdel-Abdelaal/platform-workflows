---
status: accepted
date: 2026-10-25
---

# Scan the complete prepared AI input before inference

## Context and problem statement

The AI source gate used a full-history scan after checkout fetched all branches.
A synthetic canary on an unrelated red-team branch consequently blocked a clean
production checkout. That scan also preceded health-report and current-reference
retrieval, so those appended inputs were outside its protection.

## Considered options

- Keep only the early full-history scan: misses subsequently appended input.
- Add a canary allowlist: creates an unnecessary exception at the provider boundary.
- Scan prepared input here and retain history scanning in the security workflow.

## Decision outcome

Scan the complete prepared input with the existing checksum-verified Gitleaks
binary immediately before supplying the runner's API key. Include bounded source,
handbook, glossary, diff, the selected prompt and all appended reference/issue data.
A finding fails the job before model invocation. Never allowlist the canary or
disable a scanner to make an AI run pass.

The independent security workflow continues its repository-history secret scan.
The provider boundary and history control serve different purposes and both stay
active. No source config, hook or model command is executed to construct context.

### Consequences

Unrelated branch history no longer blocks inference on clean input. Secrets in
appended issue/reference text are now covered. This does not establish that data
is non-confidential: private-repo payloads must remain private even when they pass
a credential-pattern scan. Scheduled analysis and fix targets use the repository's
actual default branch, including existing repositories that do not use `main`.
