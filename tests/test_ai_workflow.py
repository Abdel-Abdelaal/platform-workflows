import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml


def test_output_scan_is_verified_and_confined_to_the_analysis_step() -> None:
    document = yaml.safe_load(Path(".github/workflows/ai.yml").read_text())
    steps = document["jobs"]["analyze"]["steps"]
    invoked = next(
        step
        for step in steps
        if step.get("name") == "Analyze with tool-denied Flash model"
    )
    scanner = invoked["env"]["AI_OUTPUT_SECRET_SCANNER"]
    assert scanner == "${{ runner.temp }}/gitleaks/gitleaks"
    before = steps[: steps.index(invoked)]
    assert any("sha256sum --check" in step.get("run", "") for step in before)
    for job in document["jobs"].values():
        for step in job.get("steps", []):
            if step is not invoked:
                assert "AI_OUTPUT_SECRET_SCANNER" not in step.get("env", {})


def test_audit_publication_is_serialized_across_caller_refs() -> None:
    document = yaml.safe_load(Path(".github/workflows/ai.yml").read_text())
    concurrency = document["jobs"]["publish-audit"]["concurrency"]
    assert concurrency["group"] == "ai-audit-publish-${{ github.repository }}"
    assert concurrency["cancel-in-progress"] is False


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


def assert_tooling_revision(document: dict[str, Any]) -> None:
    pins: set[str] = set()
    recorded: set[str] = set()
    for job in document["jobs"].values():
        inherited = {**document.get("env", {}), **job.get("env", {})}
        for step in job.get("steps", []):
            options = step.get("with", {})
            if options.get("repository") == "Abdel-Abdelaal/platform-workflows":
                assert re.fullmatch(r"actions/checkout@[a-f0-9]{40}", step["uses"])
                assert options["persist-credentials"] is False
                assert re.fullmatch(r"[a-f0-9]{40}", options["ref"])
                pins.add(options["ref"])
            revision = {**inherited, **step.get("env", {})}.get("TOOLING_COMMIT")
            if revision is not None:
                recorded.add(revision)
    assert len(pins) == 1
    assert recorded == pins


def test_all_ai_stages_and_evidence_use_one_immutable_tooling_revision() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    assert_tooling_revision(document)


@pytest.mark.parametrize("scope", ["workflow", "job"])
@pytest.mark.parametrize("stale", [False, True])
def test_tooling_revision_checks_inherited_evidence(scope: str, stale: bool) -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    producer = next(
        step
        for step in document["jobs"]["analyze"]["steps"]
        if "TOOLING_COMMIT" in step.get("env", {})
    )
    revision = producer["env"].pop("TOOLING_COMMIT")
    target = document if scope == "workflow" else document["jobs"]["analyze"]
    target["env"] = {"TOOLING_COMMIT": "a" * 40 if stale else revision}
    if stale:
        with pytest.raises(AssertionError):
            assert_tooling_revision(document)
    else:
        assert_tooling_revision(document)


@pytest.mark.parametrize("mutation", ["action", "ref", "evidence", "credentials"])
def test_tooling_revision_rejects_broken_workflow_contracts(mutation: str) -> None:
    document = yaml.safe_load(
        Path(".github/workflows/ai.yml").read_text(encoding="utf-8")
    )
    steps = document["jobs"]["analyze"]["steps"]
    checkout = next(
        step
        for step in steps
        if step.get("with", {}).get("repository") == "Abdel-Abdelaal/platform-workflows"
    )
    if mutation == "action":
        checkout["uses"] = "actions/checkout@v7"
    elif mutation == "ref":
        checkout["with"]["ref"] = "a" * 40
    elif mutation == "credentials":
        checkout["with"]["persist-credentials"] = True
    else:
        producer = next(
            step for step in steps if "TOOLING_COMMIT" in step.get("env", {})
        )
        producer["env"]["TOOLING_COMMIT"] = "a" * 40
    with pytest.raises(AssertionError):
        assert_tooling_revision(document)


def test_release_generation_updates_every_telemetry_release_identity() -> None:
    root = Path(__file__).resolve().parents[1]
    config = json.loads(
        (root / "release-please-config.json").read_text(encoding="utf-8")
    )
    assert ".github/workflows/ai.yml" in config["packages"]["."]["extra-files"]
    source = (root / ".github/workflows/ai.yml").read_text(encoding="utf-8")
    release = "v" + (root / "version.txt").read_text(encoding="utf-8").strip()
    workflow = yaml.safe_load(source)
    for job in ("analyze", "telemetry"):
        assert any(
            step.get("env", {}).get("PLATFORM_RELEASE") == release
            for step in workflow["jobs"][job]["steps"]
        )
    for line in source.splitlines():
        if "PLATFORM_RELEASE:" in line:
            assert (
                line.strip()
                == f"PLATFORM_RELEASE: {release} # x-release-please-version"
            )


def test_release_token_is_repo_scoped_and_can_update_workflow_files() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    document = yaml.safe_load(source)
    app = next(
        step for step in document["jobs"]["release"]["steps"] if step.get("id") == "app"
    )
    assert app["with"]["repositories"] == "${{ github.event.repository.name }}"
    assert app["with"]["permission-workflows"] == "write"
    assert "permission-administration" not in app["with"]
