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


def test_all_prepared_inputs_are_scanned_before_the_provider_key_is_used() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    steps = document["jobs"]["analyze"]["steps"]
    names = [step.get("name", "") for step in steps]
    prepared = names.index("Prepare coding context")
    scanned = names.index("Scan the complete prepared model input")
    invoked = names.index("Analyze with tool-denied Flash model")
    assert prepared < scanned < invoked
    scan = steps[scanned]
    assert scan["if"] == steps[invoked]["if"]
    assert 'touch "$RUNNER_TEMP/pr.diff"' in steps[prepared]["run"]
    validated = next(
        step for step in steps if step.get("name") == "Validate analysis mode"
    )
    assert "review|audit|fix|standards" in validated["run"]
    assert "always()" not in steps[invoked]["if"]
    assert "AI_API_KEY" not in scan.get("env", {})
    for path in ("context.md", "pr.diff", "prompt.md"):
        assert path in scan["run"]
    assert " dir " in scan["run"]
    security = yaml.safe_load(
        Path(".github/workflows/security.yml").read_text(encoding="utf-8")
    )
    assert any(
        step.get("uses", "").startswith("gitleaks/gitleaks-action@")
        for step in security["jobs"]["secrets"]["steps"]
    )


def test_ai_schedules_and_proposals_follow_the_actual_default_branch() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    for name in ("analyze", "telemetry"):
        guard = document["jobs"][name]["if"]
        assert "github.event.repository.default_branch" in guard
        assert "refs/heads/main" not in guard
    proposal = next(
        step
        for step in document["jobs"]["propose-fix"]["steps"]
        if step.get("id") == "proposal"
    )
    assert proposal["with"]["base"] == "${{ github.event.repository.default_branch }}"
