from pathlib import Path

import yaml


def test_signer_consumes_only_artifact_ids_from_trusted_producers() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    jobs = document["jobs"]
    downloads = [
        step
        for step in jobs["telemetry"]["steps"]
        if step.get("uses", "").startswith("actions/download-artifact@")
    ]
    assert len(downloads) == 2
    for step in downloads:
        options = step["with"]
        assert "pattern" not in options
        assert "name" not in options
        assert "artifact-ids" in options
        assert "validate-fix" not in options["artifact-ids"]
    assert (
        "needs.analyze.outputs.evidence_artifact"
        in downloads[0]["with"]["artifact-ids"]
    )
    for producer in ("publish-review", "publish-audit", "propose-fix"):
        assert (
            f"needs.{producer}.outputs.receipt_artifact"
            in downloads[1]["with"]["artifact-ids"]
        )
        assert any(
            step.get("id") == "receipt"
            and step["uses"].startswith("actions/upload-artifact@")
            for step in jobs[producer]["steps"]
        )
    assert jobs["analyze"]["permissions"] == {"contents": "read", "issues": "read"}
