# Confidential AI evidence

Private repositories keep inputs, output records, signing keys and identifying
metadata private. The public dashboard must never collect their raw Release assets
or list their names. Public export requires a separate allowlist of non-sensitive
aggregate measurements; a credential scan alone is not a confidentiality review.

## Signing and verification

`tools.ai_private_sign` creates a standard DSSE envelope over the exact record
bytes using RSA and SHA-256. It uses the runner's OpenSSL, with no network service
or paid feature. RSA keys shorter than 2048 bits are rejected. Provision new keys
at 3072 bits or higher and retain the public trust anchors for old records after
rotation. The private key belongs in `AI_TELEMETRY_SIGNING_KEY`, never source.

The trusted signing job alone receives that secret. It must verify its generated
bundle against the independently reviewed `.github/ai-telemetry-public.pem` on the
private repository's default-branch commit before archiving. The trusted job
resolves that branch to an immutable commit and reads only the public-key blob
through the GitHub API, never checking out or executing private source. A mismatched or missing key
fails closed. No source code or proposed patch executes in the signing job.

Operators verify a downloaded private record against a separately trusted key:

```sh
python -m tools.ai_private_sign verify --record ai-record.json \
  --bundle ai-record.dsse.json --public-key trusted-public.pem
```

The envelope's key ID is a lookup hint. Verification always performs the signature
check with the explicit trust anchor, never with key material from the envelope.
This verifies integrity against a managed key; it is not a GitHub OIDC identity
attestation. Protect keys and the default-branch trust anchors accordingly.

## Durable private storage

Archive the record and its `.dsse.json` companion in the originating private
repository's monthly telemetry Release. The archiver requires explicit private
visibility for DSSE storage and refuses unknown signature formats. Asset names
remain unique per run, attempt and mode; existing evidence is never overwritten.
Actions artifacts provide a limited-retention secondary copy.

The public workflow path continues Sigstore signing and `.sigstore.json` bundles.
Private workflows must not call public transparency services. GitHub documents
private native attestations as requiring Enterprise; no upgrade is authorized.

## Rollout status

The signer, private archive naming and separate workflow branches are implemented
and tested locally. Only explicitly public workflows use the public Sigstore path;
private jobs use DSSE and verify their reviewed default-branch public key before
upload. Repository key provisioning, hosted verification, private caller onboarding
and anonymous aggregate export are subsequent rollout steps. Do not describe these
as active until hosted runs prove them. Confirm paid Actions overage is blocked
before enabling private CI under the owner's free-only constraint.
D1 is available on the owner's Free plan but has not been accessed or modified.
