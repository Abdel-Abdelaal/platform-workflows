# ADR 0007: signed per-repository AI records in public Release assets

Status: accepted for implementation; activation needs hosted verification.

## Context

Actions artifacts expire. The automation App is not configured, and a cross-repo
workflow token cannot be assumed to download other repositories' authenticated
Actions archives. We need public durable evidence without new accounts or paid
services. Records contain untrusted model output and must remain data.

## Decision

Each repository uploads secret-scanned JSON and its Sigstore bundle to its own
monthly telemetry prerelease using its own `GITHUB_TOKEN`. A separate job has
contents write, attestations write and id-token write; the model job has none of
those writes. Do not overwrite existing assets. Use a unique run/attempt/mode
filename. Keep a 90-day Actions artifact as a second copy. Sign the final record
after joining publisher receipts and job outcomes.

The public fleet dashboard aggregates public release assets, which can be read
without cross-repository credentials. Its dataset and metrics must derive solely
from records. An empty dataset shows an explicit empty state, never sample numbers.

GitHub documents [public release asset reads and contents-write uploads](https://docs.github.com/en/rest/releases/assets).
[Custom attestations](https://github.com/actions/attest/tree/v4.2.2)
bind the complete record digest to an OIDC-authenticated workflow identity.
Use the pinned v4.2.2 action; disable registry storage records (not applicable to
files) to avoid unnecessary artifact-metadata permission.

## Consequences

No new repo, account or App is required. Release assets are public and have no
automatic artifact retention expiry. Repository writers can delete assets;
attestations detect replacement, not availability loss. Backups can mirror the
public records. Monthly releases are prereleases and do not become the latest
software release. A high-volume fleet may eventually exceed practical release
asset limits; partition further or move to an App-owned dataset repository then.

When the App exists, an aggregation repo can maintain an append-only Git dataset
and reconcile expected workflow runs against collected records. That upgrade is
separate from collection and must preserve original signed bytes. No self-hosted
observability service is introduced.
