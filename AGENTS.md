# AGENTS.md

Reusable GitHub Actions workflows. Follow the shared handbook at
https://github.com/Abdel-Abdelaal/.github/tree/main/standards.

## Commands

- Workflow validation: actionlint, zizmor and YAML parsing.
- Python tools (once added): uv sync --locked; uv run pytest; uv run ruff check .
- Inspect changes with git diff --check and test reusable workflows in a caller.

## Rules

- Conventional Commit branches and PRs; no direct pushes to main.
- Third-party actions: full SHA, version comment, 14-day release cooldown.
- Top-level permissions: {}; least privilege per job; timeout-minutes on jobs.
- harden-runner first; checkout persist-credentials: false unless pushing.
- Use pull_request; never pull_request_target or untrusted text in run commands.
- Release new workflows as minor versions and move the v1 tag after validation.
- No secrets in source, output, artifacts or AI context.

## Glossary

| Name | Meaning |
|---|---|
| caller | repo workflow invoking a reusable workflow |
| platform | this repository of reusable automation |
| baseline | common files distributed from the .github repository |
