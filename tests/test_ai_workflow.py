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


def test_private_records_use_only_the_private_signer_and_default_branch_trust() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    jobs = document["jobs"]
    steps = jobs["telemetry"]["steps"]
    attest = next(step for step in steps if step.get("id") == "attest")
    private = next(step for step in steps if step.get("id") == "private-sign")
    assert attest["if"] == "github.event.repository.visibility == 'public'"
    assert private["if"] == "github.event.repository.visibility == 'private'"
    assert "tools.ai_private_sign sign" in private["run"]
    assert "tools.ai_private_sign verify" in private["run"]
    assert private["run"].index(" verify ") < private["run"].index("GITHUB_OUTPUT")
    trust = next(
        step
        for step in steps
        if step.get("name", "").startswith("Read the private repository")
    )
    assert trust["if"] == private["if"]
    assert 'metadata["default_branch"]' in trust["run"]
    assert 'commit = reference["object"]["sha"]' in trust["run"]
    assert "?ref={commit}" in trust["run"]
    assert "pull_request.head" not in trust["run"]
    assert "uses" not in trust
    for name, job in jobs.items():
        for step in job.get("steps", []):
            if "AI_TELEMETRY_SIGNING_KEY" in step.get("env", {}):
                assert name == "telemetry"
                assert step.get("id") == "private-sign"
    archive = next(
        step for step in steps if step.get("name", "").startswith("Archive signed")
    )
    assert "--signature-format" in archive["run"]
    assert (
        archive["env"]["REPOSITORY_VISIBILITY"]
        == "${{ github.event.repository.visibility }}"
    )
    assert "steps.private-sign.outputs.bundle_path" in archive["env"]["BUNDLE"]


def test_all_reusable_ai_wrappers_pass_the_private_key_explicitly() -> None:
    for name in (
        "ai-audit.yml",
        "ai-fix.yml",
        "ai-review.yml",
        "ai-standards-review.yml",
    ):
        document = yaml.load(
            Path(".github/workflows", name).read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,  # noqa: S506 -- only strings/containers; preserves YAML's on key
        )
        assert "AI_TELEMETRY_SIGNING_KEY" in document["on"]["workflow_call"]["secrets"]
        assert (
            document["jobs"]["ai"]["secrets"]["AI_TELEMETRY_SIGNING_KEY"]
            == "${{ secrets.AI_TELEMETRY_SIGNING_KEY }}"
        )
