# Use native Dependabot for the shared hook baseline

Status: accepted; supersedes ADR0005

GitHub now supports the `pre-commit` ecosystem. Its updater handles full commit
revisions, frozen/version comments and cooldown selection. This was verified in
the current official supported-ecosystem reference and Dependabot's parser,
updater and update-checker source. The custom metadata adapter is therefore removed.

Configure a weekly pre-commit update entry for `/baseline` in the handbook repo,
with the same fourteen-day cooldown as other routine version updates. Dependabot
opens normally checked PRs with its existing integration identity; no maintenance
App credential is needed to propose these updates. Reviewed baseline distribution
remains a separate App-gated PR workflow.

Keep the locked pre-commit CLI for validation and hook execution. Conformance still
rejects mutable hook revisions, so an upstream updater regression cannot silently
replace a full SHA with a tag. Security updates are reviewed promptly rather than
waiting for the routine version-update cooldown.

References:
- [Supported ecosystems](https://docs.github.com/en/code-security/reference/supply-chain-security/supported-ecosystems-and-repositories)
- [Cooldown semantics](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#cooldown)
- [Native pinned-ref handling](https://github.com/dependabot/dependabot-core/blob/main/pre_commit/lib/dependabot/pre_commit/update_checker.rb)

The decision keeps one maintained update engine and removes code, tests and an
extra credential-dependent scheduler that would otherwise duplicate it.
