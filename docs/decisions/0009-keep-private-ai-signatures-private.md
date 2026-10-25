---
status: accepted
date: 2026-10-25
---

# Sign private AI records without publishing confidential identities

## Context and problem statement

The fleet now includes confidential repositories. Their prompts, outputs and
identities must remain private, while public measurements demonstrate the system.
GitHub's documented private artifact-attestation feature requires Enterprise Cloud;
the owner requires strictly free services. Public Sigstore certificates/transparency
records disclose workflow/repository identity and are unsuitable for this data.

## Considered options

- Upgrade to Enterprise: violates the owner's free-only constraint.
- Publish private identities through public transparency: violates the approved policy.
- Sign locally with a repository-scoped key, retaining records in private storage.

## Decision outcome

Provide a dependency-free OpenSSL RSA/SHA-256 signer using the standard
[DSSE envelope and pre-authentication encoding](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md).
Verification requires an independently trusted RSA public key; an envelope cannot
supply its own trust anchor. The payload is the exact versioned record bytes.

Keep the signing key in a repository secret available only to the separate trusted
signing job. Never pass it to inference or source/patch execution. Temporary key
files use restricted permissions and are deleted after signing. OpenSSL receives
no GitHub, App or provider credentials. No signing network service is used.

Retain private records and DSSE bundles in that same private repository's monthly
Release assets. Public collection must never request those assets or identify the
repository. Public export of private data requires a separate allowlisted aggregate
format; raw records and identity-bearing signatures cannot be exported there.

### Consequences

The signature detects record modification against a trusted public key. It does
not independently prove GitHub workflow identity as a Sigstore certificate does.
The owner must protect/rotate keys and retain old trusted public keys for earlier
records. Source deletion and signing-key compromise remain separate risks.

This PR supplies and tests the signer only. Workflow wiring, key provisioning,
private retention and anonymous aggregate export are separate rollout steps and
must have hosted evidence before being described as active. No paid feature,
database schema change or visibility change is part of this decision.

GitHub documents [plan availability](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations)
and [public versus private Sigstore instances](https://docs.github.com/en/actions/concepts/security/artifact-attestations).
