import base64
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools import ai_private_sign as signing


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, Path]:
    private = tmp_path / "test-private.pem"
    public = tmp_path / "test-public.pem"
    signing.openssl(
        [
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:2048",
            "-out",
            str(private),
        ]
    )
    public.write_bytes(signing.openssl(["pkey", "-in", str(private), "-pubout"]))
    return private, public


def test_real_sign_verify_rejects_tampering_and_wrong_keys(
    tmp_path: Path, keys: tuple[Path, Path]
) -> None:
    private, public = keys
    record = tmp_path / "record.json"
    bundle = tmp_path / "record.dsse.json"
    record.write_text(
        '{"schema_version":1,"summary":"Unicode: café"}', encoding="utf-8"
    )
    signing.sign(record, private.read_text(), bundle)
    signing.verify(record, bundle, public)
    envelope = json.loads(bundle.read_text())
    assert base64.b64decode(envelope["payload"]) == record.read_bytes()
    assert "PRIVATE KEY" not in bundle.read_text()
    # DSSE requires both standard and URL-safe base64 encodings to verify.
    envelope["payload"] = base64.urlsafe_b64encode(record.read_bytes()).decode()
    envelope["signatures"][0]["sig"] = (
        envelope["signatures"][0]["sig"].replace("+", "-").replace("/", "_")
    )
    bundle.write_text(json.dumps(envelope))
    signing.verify(record, bundle, public)
    record.write_text('{"schema_version":1,"summary":"tampered"}')
    with pytest.raises(signing.SignatureError):
        signing.verify(record, bundle, public)
    # Editing both payload and record still fails cryptographic verification.
    envelope["payload"] = base64.b64encode(record.read_bytes()).decode()
    bundle.write_text(json.dumps(envelope))
    with pytest.raises(signing.SignatureError):
        signing.verify(record, bundle, public)
    envelope["signatures"][0]["keyid"] = "0" * 64
    bundle.write_text(json.dumps(envelope))
    with pytest.raises(signing.SignatureError):
        signing.verify(record, bundle, public)


@pytest.mark.parametrize("change", ["type", "signatures", "oversized"])
def test_invalid_envelopes_fail_closed(
    tmp_path: Path, keys: tuple[Path, Path], change: str
) -> None:
    private, public = keys
    record = tmp_path / "record.json"
    bundle = tmp_path / "bundle.json"
    record.write_text('{"schema_version":1}')
    signing.sign(record, private.read_text(), bundle)
    envelope = json.loads(bundle.read_text())
    if change == "type":
        envelope["payloadType"] = "different-protocol"
    elif change == "signatures":
        envelope["signatures"] *= 2
    else:
        envelope["padding"] = "x" * (signing.MAX_RECORD_BYTES * 2)
    bundle.write_text(json.dumps(envelope))
    with pytest.raises(signing.SignatureError):
        signing.verify(record, bundle, public)


@pytest.mark.parametrize("value", ["[]", "{}", '{"schema_version":2}'])
def test_unsupported_records_cannot_be_signed(tmp_path: Path, value: str) -> None:
    record = tmp_path / "record.json"
    record.write_text(value)
    with pytest.raises(signing.SignatureError):
        signing.record_bytes(record)


def test_missing_key_and_oversized_record_are_rejected(tmp_path: Path) -> None:
    record = tmp_path / "record.json"
    record.write_bytes(b"x" * (signing.MAX_RECORD_BYTES + 1))
    with pytest.raises(signing.SignatureError):
        signing.record_bytes(record)
    with pytest.raises(signing.SignatureError):
        signing.sign(record, "", tmp_path / "bundle.json")


def test_openssl_environment_and_failure_do_not_expose_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_TELEMETRY_SIGNING_KEY", "private-material")
    monkeypatch.setenv("GH_TOKEN", "github-credential")
    run = Mock(
        return_value=subprocess.CompletedProcess([], 1, b"", b"private-material")
    )
    monkeypatch.setattr(signing.subprocess, "run", run)
    with pytest.raises(signing.SignatureError) as error:
        signing.openssl(["version"])
    assert "private-material" not in str(error.value)
    assert "GH_TOKEN" not in run.call_args.kwargs["env"]
    assert "AI_TELEMETRY_SIGNING_KEY" not in run.call_args.kwargs["env"]
    assert "shell" not in run.call_args.kwargs


def test_weak_rsa_key_is_not_accepted(tmp_path: Path) -> None:
    private = tmp_path / "weak-test-key.pem"
    signing.openssl(
        [
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:1024",
            "-out",
            str(private),
        ]
    )
    record = tmp_path / "record.json"
    record.write_text('{"schema_version":1}')
    bundle = tmp_path / "bundle.json"
    with pytest.raises(signing.SignatureError):
        signing.sign(record, private.read_text(), bundle)
    assert not bundle.exists()


@pytest.mark.parametrize("mode", ["sign", "verify", "missing-public"])
def test_cli_sign_verify_and_required_trust_anchor(
    tmp_path: Path, keys: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    private, public = keys
    record = tmp_path / "record.json"
    bundle = tmp_path / "bundle.json"
    record.write_text('{"schema_version":1}')
    monkeypatch.setenv("AI_TELEMETRY_SIGNING_KEY", private.read_text())
    args = [
        "signer",
        mode if mode != "missing-public" else "verify",
        "--record",
        str(record),
        "--bundle",
        str(bundle),
    ]
    if mode == "verify":
        signing.sign(record, private.read_text(), bundle)
        args += ["--public-key", str(public)]
    monkeypatch.setattr(sys, "argv", args)
    if mode == "missing-public":
        with pytest.raises(SystemExit):
            signing.main()
    else:
        signing.main()
        assert bundle.exists()


def test_cli_withholds_key_and_error_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "signer",
            "sign",
            "--record",
            str(tmp_path / "absent"),
            "--bundle",
            str(tmp_path / "bundle"),
        ],
    )
    monkeypatch.delenv("AI_TELEMETRY_SIGNING_KEY", raising=False)
    with pytest.raises(SystemExit, match="details withheld"):
        signing.main()
