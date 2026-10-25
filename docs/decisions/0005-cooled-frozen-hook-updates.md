# Select eligible hook releases before freezing their revisions

Status: accepted

`pre-commit autoupdate --freeze` selects the newest upstream tag. It cannot select
the newest release that has already passed the fleet's fourteen-day cooldown.
Discarding every too-fresh update would starve frequently released tools of updates.

Use a small metadata adapter around the existing pre-commit configuration. It
queries each approved GitHub upstream's published releases, excludes drafts,
prereleases and releases younger than fourteen days, selects the highest eligible
semantic version and resolves it to an immutable commit. It changes revision lines
only and preserves the configured hooks and arguments. Missing publication evidence,
archived upstreams, unsupported layouts and downgrades fail closed before writes.
The normal pre-commit validator and hook execution remain responsible for checking
the proposed configuration; the adapter does not implement hook installation or
execution. Updates are PRs, never direct main writes or automatic merges.

The command defaults to dry-run. The scheduled publisher requires the automation
App, uses immutable reviewed tooling, validates hooks without App credentials and
only then mints a repository-scoped token to propose the update. Missing App setup
skips explicitly. Provider credentials are never needed by hook maintenance.

The Python CLI is locked to pre-commit4.6.0:4.7.0 was uploaded on2026-10-12 and
was still younger than fourteen days when this decision was implemented. A fresh
resolver cutoff selected eligible dependencies; subsequent updates remain reviewed.
