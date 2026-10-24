---
status: accepted
date: 2026-10-24
---

# Isolate the coding model from GitHub credentials and executable repo config

## Context and problem statement

A code reviewer reads attacker-controlled diffs. Running an agent directly in a PR
checkout could load its opencode config, plugins or instructions before permissions
are applied. Separately, even non-blocking inline review comments create unresolved
threads, which our branch rules correctly block until resolved.

## Considered options

- Run an agent in the checkout with a GitHub write token.
- Allow only a few shell commands and resolve its review threads automatically.
- Run a tool-denied model on bounded source data in a clean temporary directory,
  validate its JSON, and publish feedback through separate trusted jobs.

## Decision outcome

Use pinned OpenCode with --pure, a clean working directory, isolated XDG paths,
and every tool explicitly denied. Never load project agent/config/plugin files.
The child environment contains the AI key but no GitHub/App credential. Both model
roles are fixed to the owner's Xiaomi MiMo 2.6 Flash choice. Sharing is disabled.

Source and diffs are data; output passes a strict bounded Pydantic schema. Publish
findings as notice annotations plus a sticky summary, not unresolved review threads
or approval events. AI checks are never required for merging.

AI fixes may only produce a bounded patch in application/tests/docs paths. Trusted
code validates paths and git apply, tests run without AI/App credentials, and a
separate job may use an App token to open a draft PR. No AI process merges or applies
infrastructure. Missing credentials skip with an explicit notice.

### Consequences

- Prompt injection cannot grant the model shell, filesystem or GitHub tool access.
- The model can still make mistakes; schema validation is not correctness proof.
- Real tests and human review remain necessary for proposed patches.
- Notice annotations preserve inline feedback without violating advisory-only policy.
- Fresh source-document context must be collected by trusted code before monthly
  standards review; the model itself has no web access.
