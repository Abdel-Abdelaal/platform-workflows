# Maintenance and release activation

The release source is implemented, but a successful workflow can still mean it
explicitly skipped. Platform run 40970778731 skipped because BOT_APP_ID and
BOT_APP_KEY were absent. The release labels are also unapplied. No release or
consumer rollout is implied by the draft version proposal in PR #82.

## Identity to review

[The exact maintenance App manifest](maintenance-automation-app.json) requests:

| Permission | Level | Purpose |
| --- | --- | --- |
| Metadata | Read | Identify installed repositories |
| Contents | Write | Push maintenance branches and publish accepted releases |
| Pull requests | Write | Open normal maintenance and release proposals |
| Issues | Write | Update release proposal labels and authorized maintenance reports |
| Workflows | Write | Propose baseline workflow-file changes through protected PRs |

It requests no administration, environments, repository secrets or billing
permissions. It subscribes to no webhook events. A private App can still access
private repositories if installed on them; public=false limits who can install
it, not the visibility of repositories it can access.

This is a separate identity from the existing enrollment App. Enrollment has
secret-write but no issue-write permission. Do not alias its ENROLLMENT_APP_ID
or ENROLLMENT_APP_KEY into BOT_APP_* or broaden its approved permissions to
activate unrelated maintenance jobs. No App token or private key reaches a model.

Review the manifest and installation scope before creating or installing it:

- Selected public repositories keep private repositories outside the installation.
  Add each future public repository to that installation before maintenance runs.
- An all-repositories installation includes current and future private repositories.
  That broader access needs explicit owner approval. The existing enrollment
  approval does not approve this separate identity or its issue access.

The seven public, active, non-fork repositories observed on 30 October are .github,
platform-workflows, shortlink, github-governance, agent-dispatcher, ello and
youtube-knowledge-distillation. Re-discover and verify visibility before setup;
this list is an observation, not an authorization or a permanent allowlist.

## Activation sequence

- Verify the intended App's actual permissions and selected installation targets.
  Keep webhooks disabled. Store its ID/key as BOT_APP_ID/BOT_APP_KEY only in
  approved caller repositories. Use encrypted repository-secret input; never
  print the key or put it in source, logs, artifacts or model context.
- Review the existing jobs that receive BOT_APP_* before provisioning it. Setup
  can activate baseline proposals and AI draft fixes as well as release proposals.
  Each reusable caller must pass secrets explicitly; repository secrets are not
  automatically shared with other repositories. Existing scoped token requests
  restrict each job to its repository and the permissions it needs.
- The governance-owned labels autorelease: pending and autorelease: tagged must
  be applied from the reviewed desired state. Follow governance's owner-controlled
  apply rule; this guide does not authorize a Terraform apply or a protection change.
- Dispatch release-please.yml on trusted main and require an actual generated
  release proposal. Verify App authorship and normal required checks. Replace the
  handwritten draft proposal rather than merge duplicate version/changelog edits.
- Merge the generated proposal through ordinary protection, then verify the
  immutable release tag, release notes and full release commit. A workflow exit
  code alone is insufficient proof. Never force or move an immutable version tag.
- Update the reviewed enrollment constant and public consumer pins in separate
  PRs. Verify current callers and one newly enrolled public caller. Record signed
  evidence before describing fleet-wide activation as complete.

## Boundaries and evidence

This proposal creates no App, changes no permissions or secrets, applies no
infrastructure and publishes no release. Existing enrollment continues under its
separate approved identity. Registration, installation and hosted activation must
be evidenced separately. Services remain free; there is no paid fallback, personal
access-token fallback, subscription purchase or provider budget change.
