"""Sign confidential AI records with DSSE, without a public transparency service."""

import argparse
import base64
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

from tools.ai_telemetry import mapping

PAYLOAD_TYPE = "application/vnd.showcase.ai-record.v1+json"
MAX_RECORD_BYTES = 2_000_000
MIN_RSA_SIGNATURE_BYTES = 256


class SignatureError(Exception):
    """Signing or verification failed; key and subprocess output are withheld."""


def openssl(arguments: list[str]) -> bytes:
    """Run the runner's OpenSSL with no provider, App or GitHub credentials."""
    environment = {
        name: os.environ[name]
        for name in ("PATH", "SYSTEMROOT", "WINDIR")
        if name in os.environ
    }
    result = subprocess.run(
        ["openssl", *arguments],
        capture_output=True,
        check=False,
        env=environment,
        timeout=30,
    )
    if result.returncode:
        raise SignatureError from None
    return result.stdout


def pae(payload: bytes) -> bytes:
    """Use DSSE's standard pre-authentication encoding, with byte lengths."""
    kind = PAYLOAD_TYPE.encode("utf-8")
    return (
        b"DSSEv1 "
        + str(len(kind)).encode()
        + b" "
        + kind
        + b" "
        + str(len(payload)).encode()
        + b" "
        + payload
    )


def record_bytes(record: Path) -> bytes:
    """Bound local input and require a v1 JSON object before signing."""
    with record.open("rb") as source:
        payload = source.read(MAX_RECORD_BYTES + 1)
    if len(payload) > MAX_RECORD_BYTES:
        raise SignatureError
    document = json.loads(payload)
    version = mapping(document).get("schema_version")
    if type(version) is not int or version != 1:
        raise SignatureError
    return payload


def sign(record: Path, private_key: str, bundle: Path) -> None:
    """Create a DSSE RSA/SHA-256 envelope; keep private key material temporary."""
    if not private_key:
        raise SignatureError
    payload = record_bytes(record)
    with tempfile.TemporaryDirectory(prefix="ai-private-sign-") as temporary:
        directory = Path(temporary)
        directory.chmod(0o700)
        key = directory / "key.pem"
        # Create with restricted permissions before writing any key bytes.
        descriptor = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as target:
            target.write(private_key)
        message = directory / "pae.bin"
        message.write_bytes(pae(payload))
        signature = openssl(["dgst", "-sha256", "-sign", str(key), str(message)])
        if len(signature) < MIN_RSA_SIGNATURE_BYTES:
            raise SignatureError
        public_key = openssl(["pkey", "-in", str(key), "-pubout", "-outform", "DER"])
        # Reject non-RSA keys: algorithm selection is fixed, never bundle-controlled.
        openssl(["rsa", "-in", str(key), "-check", "-noout"])
    envelope = {
        "payloadType": PAYLOAD_TYPE,
        "payload": base64.b64encode(payload).decode("ascii"),
        "signatures": [
            {
                "keyid": hashlib.sha256(public_key).hexdigest(),
                "sig": base64.b64encode(signature).decode("ascii"),
            }
        ],
    }
    bundle.write_text(json.dumps(envelope), encoding="utf-8")


def _verify(record: Path, bundle: Path, public_key: Path) -> None:
    """Verify against an explicitly trusted public key, never an embedded key."""
    if bundle.stat().st_size > MAX_RECORD_BYTES * 2:
        raise SignatureError
    envelope = json.loads(bundle.read_text(encoding="utf-8"))
    payload = record_bytes(record)
    if (
        envelope["payloadType"] != PAYLOAD_TYPE
        or base64.b64decode(envelope["payload"], altchars=b"-_", validate=True)
        != payload
        or len(envelope["signatures"]) != 1
    ):
        raise SignatureError
    signature = envelope["signatures"][0]
    openssl(["rsa", "-pubin", "-in", str(public_key), "-noout"])
    trusted = openssl(["pkey", "-pubin", "-in", str(public_key), "-outform", "DER"])
    if signature["keyid"] != hashlib.sha256(trusted).hexdigest():
        raise SignatureError
    with tempfile.TemporaryDirectory(prefix="ai-private-verify-") as temporary:
        message = Path(temporary) / "pae.bin"
        signature_path = Path(temporary) / "signature.bin"
        message.write_bytes(pae(payload))
        decoded = base64.b64decode(signature["sig"], altchars=b"-_", validate=True)
        if len(decoded) < MIN_RSA_SIGNATURE_BYTES:
            raise SignatureError
        signature_path.write_bytes(decoded)
        openssl(
            [
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                "-signature",
                str(signature_path),
                str(message),
            ]
        )


def verify(record: Path, bundle: Path, public_key: Path) -> None:
    """Reject all unavailable, malformed or invalid evidence with one safe error."""
    try:
        _verify(record, bundle, public_key)
    except (
        SignatureError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        subprocess.SubprocessError,
    ):
        raise SignatureError from None


def main() -> None:
    """Sign privately or verify offline without an account or network service."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["sign", "verify"])
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--public-key", type=Path)
    args = parser.parse_args()
    if args.command == "verify" and not args.public_key:
        parser.error("verify requires --public-key")
    try:
        if args.command == "sign":
            sign(
                args.record, os.environ.get("AI_TELEMETRY_SIGNING_KEY", ""), args.bundle
            )
        elif args.public_key:
            verify(args.record, args.bundle, args.public_key)
    except (
        SignatureError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        subprocess.SubprocessError,
    ):
        message = "Private AI evidence signing/verification failed; details withheld."
        raise SystemExit(message) from None


if __name__ == "__main__":
    main()
