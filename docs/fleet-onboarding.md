# Future repository enrollment

`python -m tools.fleet_onboarding --output plan.json` is read-only. It discovers
public, non-fork, non-archived repositories owned by Abdel-Abdelaal and compares
them with the reviewed starter at the immutable `BASELINE_COMMIT` in the tool.
The public dashboard independently discovers those repositories; discovery alone
does not install any engineering processes.

The daily default-branch `fleet-enrollment.yml` controller plans with read-only
permissions. Without App credentials it uploads a public plan and explicitly
skips writing. Automatic enrollment proposals are **not active** until the App
is configured and a real hosted enrollment proves them. No personal access token fallback exists.
`--apply` first requires the installation-repositories endpoint to work.

## Reviewable changes

The tool proposes missing files from a fixed allowlist: common repository files,
ownership, Dependabot cooldowns and nine shared callers (PR title, security,
conformance, Scorecard, AI review, weekly AI maintenance, baseline sync, stale
items, language-aware lint). Security uses automatic language detection. Existing
files, application commands, licensing and domain instructions
are preserved. The actual default branch replaces the starter's main filter.
The generated draft PR requires review of licensing, language-specific checks
and instructions. It never merges, pushes the default branch, force-pushes an
existing bot branch, executes repository code or applies Terraform.

An existing conformance caller is an enrollment marker, not proof every process
is healthy. The plan reports missing or unverified default-branch protection as a
blocking finding, even for an existing enrollment marker. A draft proposal can
still be reviewed, but enrollment remains incomplete until governance protection
is configured. Existing repos continue through fleet health and conformance checks.
If a fixed bot branch exists without an open PR, creation fails safely for manual
inspection. Incomplete trees and symlink parent directories are rejected.

## Automation App setup to review

Use a separate automation App from the administration-capable governance App.
The enrollment controller needs repository contents, pull requests and workflows
write, plus metadata read. Automatic provisioning of a missing `AI_API_KEY` also
needs repository secrets write. Existing secrets are preserved, including when
they occur after the first API page. The committed controller requests that scope;
for manual provisioning, review a change removing its `permission-secrets` input
and `AI_API_KEY` environment entry before omitting that App permission.
No App private key or token is ever given to a model.

The exact owner-only App permission proposal is
[`fleet-automation-app.json`](fleet-automation-app.json), using the
[GitHub App manifest format](https://github.com/github/docs/blob/main/content/apps/sharing-github-apps/registering-a-github-app-from-a-manifest.md).
It requests no administration, public transparency, webhook, model or billing
access. App creation/installation requires the owner's review of these permissions.

Store the App ID/private key only in the controller repository's `BOT_APP_ID` and
`BOT_APP_KEY` secrets. Before minting its write token, the eventual controller
discovers and scopes the token to eligible public repository names; do not
place private installation metadata in a public artifact or log. Restrict the
controller to trusted default-branch schedule/dispatch events. The tool rechecks
visibility before proposal creation. Public output includes only eligible public
repository names, missing paths and draft PR links.

Private repositories require the separate private telemetry profile and a
confirmed $0 Actions overage limit before execution. This public controller must
not bootstrap their signing keys or disclose their identities. GitHub settings
and required-check enforcement still require a governance inventory PR and
reviewed import/apply; adding callers does not prove enforcement is configured.

## Local verification

The offline tests cover private filtering, pagination, immutable templates,
default branches, preserving existing source, metadata changes, scoped paths,
secret preservation, draft-only creation and withheld external error details.
Run the normal platform Ruff, Pyright and pytest gates. A public dry-run can
verify discovery against current GitHub state without creating anything.
