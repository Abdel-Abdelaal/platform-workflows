# Public dependency maintenance

The fleet controller runs on the platform's default branch every six hours, or
manually. A manual run defaults to a read-only plan. Activation requires the
reviewed workflow to be merged and an actual hosted run to succeed.

It discovers current and future public owner repositories, limits the maintenance
App token to those repositories, and rechecks eligibility before each mutation.
Private, archived, disabled and fork repositories are excluded. No PR checkout,
dependency installation, model call or AI/provider secret is involved.

Only an unchanged, GitHub-verified Dependabot commit with explicit patch/minor
metadata can qualify. Every member of a dependency group must qualify. Unknown
metadata, majors, pre-1.0 minor updates, and OpenCode/promptfoo runtime updates
remain for maintainer review. The verified-commit metadata convention follows
[dependabot/fetch-metadata](https://github.com/dependabot/fetch-metadata), MIT.
No upstream source was copied. Dependabot's configured cooldown remains in force;
security updates still receive normal required checks and review.

The controller requires a protected default branch with nonempty strict required
checks and a currently clean merge state. GitHub enforces protection at the merge;
the request supplies the exact inspected head SHA and squash method. It cannot
approve a review, bypass protection, update a branch, resolve a thread or push to
the default branch. At most one update per repository merges per cycle. Behind,
conflicting or failing PRs stay open with a reason in the public run artifact.

This central workflow covers repositories that lack a local auto-merge workflow.
The old `dependabot-automerge.yml` workflows remain opt-in and their variable stays
unset: Dependabot PR events receive a read-only token, so those workflows are not
the fleet merge controller. Merely enabling GitHub's auto-merge repository setting
does not queue any PR.

Every run retains a public plan/result artifact for 30 days; scheduled failures
open the existing maintenance-failure issue. This is operational evidence, not an
AI run or an autonomous coding-quality measurement.
