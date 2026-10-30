import base64
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import yaml

from tools import fleet_onboarding as fleet

PUBLIC: dict[str, Any] = {
    "full_name": "Abdel-Abdelaal/example",
    "name": "example",
    "private": False,
    "fork": False,
    "archived": False,
    "default_branch": "master",
}
SHA = "a" * 40


def api_for_proposal(entries: list[dict[str, str]]) -> Mock:
    return Mock(
        side_effect=[
            PUBLIC,
            {"commit": {"sha": SHA}, "protected": True},
            {"truncated": False, "sha": SHA, "tree": entries},
        ]
    )


@pytest.mark.parametrize("installation", [True, False])
def test_discovery_filters_private_unknown_forks_and_archives(
    monkeypatch: pytest.MonkeyPatch, installation: bool
) -> None:
    batch = [
        PUBLIC,
        {**PUBLIC, "private": True},
        {**PUBLIC, "private": None},
        {**PUBLIC, "fork": True},
        {**PUBLIC, "archived": True},
        {**PUBLIC, "full_name": "other/example"},
    ]
    api = Mock(return_value={"repositories": batch} if installation else batch)
    monkeypatch.setattr(fleet, "github_api", api)
    assert fleet.repositories(installation=installation) == [PUBLIC]
    assert api.call_args.args[0].startswith(
        "installation/repositories" if installation else "users/Abdel-Abdelaal/repos"
    )


def test_discovery_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    api = Mock(side_effect=[[PUBLIC] * fleet.PAGE_SIZE, []])
    monkeypatch.setattr(fleet, "github_api", api)
    assert len(fleet.repositories(installation=False)) == fleet.PAGE_SIZE
    assert "page=2" in api.call_args.args[0]


def test_apply_never_falls_back_to_personal_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock(side_effect=subprocess.CalledProcessError(403, "gh", stderr="sensitive"))
    monkeypatch.setattr(fleet, "github_api", api)
    with pytest.raises(subprocess.CalledProcessError):
        fleet.repositories(installation=True)
    assert api.call_count == 1


def test_missing_only_and_default_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    api = api_for_proposal([{"path": "README.md", "type": "blob"}])
    monkeypatch.setattr(fleet, "github_api", api)
    plan = fleet.proposal(
        PUBLIC,
        {
            "README.md": "replace original",
            "AGENTS.md": "placeholder",
            ".github/workflows/pr.yml": "branches: [main]\nname: REPO-NAME",
        },
    )
    assert "README.md" not in plan["files"]
    assert "placeholder" not in plan["files"]["AGENTS.md"]
    assert 'branches: ["master"]' in plan["files"][".github/workflows/pr.yml"]
    assert "name: example" in plan["files"][".github/workflows/pr.yml"]
    assert plan["parent"] == SHA


def test_existing_enrollment_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fleet,
        "github_api",
        api_for_proposal(
            [{"path": ".github/workflows/conformance-checks.yml", "type": "blob"}]
        ),
    )
    assert fleet.proposal(PUBLIC, {"README.md": "new"})["files"] == {}


@pytest.mark.parametrize("protected", [True, False, None])
def test_enrollment_marker_does_not_hide_missing_protection(
    monkeypatch: pytest.MonkeyPatch, protected: bool | None
) -> None:
    monkeypatch.setattr(
        fleet,
        "github_api",
        Mock(
            side_effect=[
                PUBLIC,
                {"commit": {"sha": SHA}, "protected": protected},
                {
                    "truncated": False,
                    "sha": SHA,
                    "tree": [
                        {
                            "path": ".github/workflows/conformance-checks.yml",
                            "type": "blob",
                        }
                    ],
                },
            ]
        ),
    )
    plan = fleet.proposal(PUBLIC, {})
    assert plan["default_branch_protected"] is protected
    assert bool(plan["blocking_findings"]) is (protected is not True)


@pytest.mark.parametrize(
    "metadata",
    [{**PUBLIC, "private": True}, {**PUBLIC, "default_branch": "bad\nbranch"}],
)
def test_proposal_rechecks_metadata(
    monkeypatch: pytest.MonkeyPatch, metadata: dict[str, Any]
) -> None:
    monkeypatch.setattr(fleet, "github_api", Mock(return_value=metadata))
    with pytest.raises(ValueError, match=r"public enrollment|default branch"):
        fleet.proposal(PUBLIC, {})


def test_invalid_commit_truncated_tree_and_parent_symlink(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for responses in (
        [PUBLIC, {"commit": {"sha": "main"}}],
        [PUBLIC, {"commit": {"sha": SHA}, "protected": True}, {"truncated": True}],
        [
            PUBLIC,
            {"commit": {"sha": SHA}, "protected": True},
            {
                "truncated": False,
                "sha": SHA,
                "tree": [{"path": ".github", "type": "blob"}],
            },
        ],
    ):
        monkeypatch.setattr(fleet, "github_api", Mock(side_effect=responses))
        with pytest.raises(ValueError, match=r"immutable|incomplete|regular tree"):
            fleet.proposal(PUBLIC, {})


def test_templates_are_fixed_pinned_regular_bounded_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blob = {
        "type": "file",
        "encoding": "base64",
        "content": base64.b64encode(b"reviewed").decode(),
    }
    api = Mock(return_value=blob)
    monkeypatch.setattr(fleet, "github_api", api)
    assert set(fleet.templates()) == set(fleet.FILES)
    assert all(fleet.BASELINE_COMMIT in call.args[0] for call in api.call_args_list)
    for invalid in (
        {**blob, "type": "symlink"},
        {
            **blob,
            "content": base64.b64encode(b"x" * (fleet.MAX_FILE_BYTES + 1)).decode(),
        },
    ):
        api.return_value = invalid
        with pytest.raises(ValueError, match=r"regular encoded blob|size bound"):
            fleet.templates()


def test_owned_callers_use_reviewed_release_without_changing_third_parties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = (
        f"uses: {fleet.OWNER}/platform-workflows/.github/workflows/lint.yml@"
        + "a" * 40
        + " # old release\n"
        + "uses: third-party/action@"
        + "b" * 40
        + " # retained\n"
    )
    monkeypatch.setattr(
        fleet,
        "github_api",
        Mock(
            return_value={
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(source.encode()).decode(),
            }
        ),
    )
    rendered = fleet.templates()[".github/workflows/lint.yml"]
    assert f"@{fleet.PLATFORM_COMMIT} # {fleet.PLATFORM_RELEASE}" in rendered
    assert "uses: third-party/action@" + "b" * 40 + " # retained\n" in rendered


def test_preserve_provider_secret_in_later_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_API_KEY", "test-only-value")
    api = Mock(
        side_effect=[
            {"secrets": [{"name": "other"}] * fleet.PAGE_SIZE},
            {"secrets": [{"name": "AI_API_KEY"}]},
        ]
    )
    run = Mock()
    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    fleet.provision_provider_key(PUBLIC["full_name"])
    run.assert_not_called()


def test_provider_key_uses_stdin_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    api, run = Mock(return_value={"secrets": []}), Mock()
    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    fleet.provision_provider_key(PUBLIC["full_name"])
    api.assert_not_called()
    monkeypatch.setenv("AI_API_KEY", "test-only-value")
    fleet.provision_provider_key(PUBLIC["full_name"])
    assert run.call_args.kwargs["input"] == "test-only-value"
    assert "test-only-value" not in str(run.call_args.args)
    assert run.call_args.kwargs["capture_output"] is True


def test_publish_draft_only_without_force_or_main_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = {
        "repository": PUBLIC["full_name"],
        "files": {"README.md": "new"},
        "parent": SHA,
        "tree": SHA,
        "base": "master",
    }
    api = Mock(
        side_effect=[
            PUBLIC,
            [],
            {"sha": SHA},
            {"sha": SHA},
            None,
            {"html_url": "https://github.com/example/pull/1"},
        ]
    )
    monkeypatch.setattr(fleet, "github_api", api)
    key = Mock()
    monkeypatch.setattr(fleet, "provision_provider_key", key)
    assert fleet.publish(plan) == "https://github.com/example/pull/1"
    writes = [call for call in api.call_args_list if len(call.args) > 1]
    assert len(writes) == 4
    assert all(call.args[1] == "POST" for call in writes)
    assert writes[-2].args[2]["ref"] == "refs/heads/ci/fleet-onboarding"
    assert writes[-1].args[2]["draft"] is True
    assert writes[-1].args[2]["base"] == "master"
    assert all("force" not in call.args[2] for call in writes)


def test_existing_pr_and_empty_plan_do_not_change_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = Mock(side_effect=[PUBLIC, [{"html_url": "existing"}], PUBLIC, []])
    monkeypatch.setattr(fleet, "github_api", api)
    provision = Mock()
    maintenance = Mock()
    monkeypatch.setattr(fleet, "provision_maintenance_app", maintenance)
    monkeypatch.setattr(fleet, "provision_provider_key", provision)
    plan: dict[str, Any] = {"repository": PUBLIC["full_name"], "files": {}}
    assert fleet.publish(plan) == "existing"
    assert fleet.publish(plan) is None
    assert provision.call_count == maintenance.call_count == 2
    assert all(
        call.args == (PUBLIC["full_name"],) for call in maintenance.call_args_list
    )
    assert all(len(call.args) == 1 for call in api.call_args_list)


def test_visibility_flip_and_unallowlisted_paths_block_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for metadata, files in (
        ({**PUBLIC, "private": True}, {}),
        (PUBLIC, {"../../escape": "bad"}),
    ):
        api = Mock(side_effect=[metadata, []])
        monkeypatch.setattr(fleet, "github_api", api)
        with pytest.raises(ValueError, match=r"eligible|allowlist"):
            fleet.publish({"repository": PUBLIC["full_name"], "files": files})
        assert all(len(call.args) == 1 for call in api.call_args_list)


def test_cli_default_is_read_only_and_error_is_scrubbed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "plan.json"
    monkeypatch.setattr(sys, "argv", ["fleet", "--output", str(output)])
    monkeypatch.setattr(fleet, "repositories", Mock(return_value=[PUBLIC]))
    monkeypatch.setattr(fleet, "templates", Mock(return_value={}))
    monkeypatch.setattr(
        fleet,
        "proposal",
        Mock(
            return_value={
                "repository": PUBLIC["full_name"],
                "status": "proposal",
                "files": {},
            }
        ),
    )
    publish = Mock()
    monkeypatch.setattr(fleet, "publish", publish)
    fleet.main()
    publish.assert_not_called()
    assert json.loads(output.read_text())["repositories"][0]["pull_request"] is None
    monkeypatch.setattr(fleet, "templates", Mock(side_effect=ValueError("sensitive")))
    with pytest.raises(SystemExit, match="credentials withheld") as error:
        fleet.main()
    assert "sensitive" not in str(error.value)


def test_malformed_collections_are_rejected() -> None:
    with pytest.raises(TypeError):
        fleet.objects({})


def test_controller_limits_write_credentials_to_trusted_public_targets() -> None:
    document = yaml.safe_load(
        Path(".github/workflows/fleet-enrollment.yml").read_text(encoding="utf-8")
    )
    assert document["permissions"] == {}
    job = document["jobs"]["enroll"]
    assert job["permissions"] == {"contents": "read"}
    assert job["if"] == "github.ref_name == github.event.repository.default_branch"
    steps = job["steps"]
    app = next(step for step in steps if step.get("id") == "app")
    assert app["with"]["repositories"] == "${{ steps.targets.outputs.repositories }}"
    assert "secrets.ENROLLMENT_APP_ID" in app["with"]["app-id"]
    assert "secrets.ENROLLMENT_APP_KEY" in app["with"]["private-key"]
    assert "steps.targets.outputs.repositories != ''" in app["if"]
    assert "permission-administration" not in app["with"]
    key_steps = [step for step in steps if "AI_API_KEY" in step.get("env", {})]
    assert len(key_steps) == 1
    assert key_steps[0]["env"]["BOT_APP_ID"] == "${{ secrets.BOT_APP_ID }}"
    assert key_steps[0]["env"]["BOT_APP_KEY"] == "${{ secrets.BOT_APP_KEY }}"
    assert sum("BOT_APP_KEY" in step.get("env", {}) for step in steps) == 1
    assert "--apply" in key_steps[0]["run"]
    app_output_reference = "${{ steps.app.outputs.token }}"
    assert key_steps[0]["env"]["GH_TOKEN"] == app_output_reference
    assert len(fleet.CALLERS) == 9
    assert "lint.yml" in fleet.CALLERS


@pytest.mark.parametrize("source", ["none", "partial", "complete"])
def test_maintenance_pair_uses_fresh_public_metadata_and_stdin(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    for name in ("BOT_APP_ID", "BOT_APP_KEY"):
        monkeypatch.delenv(name, raising=False)
    if source != "none":
        monkeypatch.setenv("BOT_APP_ID", "test-app-id")
    if source == "complete":
        monkeypatch.setenv("BOT_APP_KEY", "test-private-value")
    api = Mock(
        side_effect=[
            {**PUBLIC, "visibility": "public", "disabled": False},
            {"secrets": []},
        ]
    )
    run = Mock()
    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    if source == "partial":
        with pytest.raises(ValueError, match="complete pair"):
            fleet.provision_maintenance_app(PUBLIC["full_name"])
        api.assert_not_called()
    else:
        fleet.provision_maintenance_app(PUBLIC["full_name"])
    assert run.call_count == (2 if source == "complete" else 0)
    if source == "complete":
        assert [c.args[0][3] for c in run.call_args_list] == [
            "BOT_APP_ID",
            "BOT_APP_KEY",
        ]
        assert [c.kwargs["input"] for c in run.call_args_list] == [
            "test-app-id",
            "test-private-value",
        ]
        assert all(c.kwargs["capture_output"] for c in run.call_args_list)
        assert "test-private-value" not in str(run.call_args_list[1].args)


@pytest.mark.parametrize(
    "mutation", ["private", "fork", "archived", "disabled", "owner", "unknown"]
)
def test_maintenance_pair_refuses_ineligible_or_unknown_targets(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    monkeypatch.setenv("BOT_APP_ID", "test-id")
    monkeypatch.setenv("BOT_APP_KEY", "test-value")
    metadata = {**PUBLIC, "visibility": "public", "disabled": False}
    if mutation in {"private", "fork", "archived", "disabled"}:
        metadata[mutation] = True
    elif mutation == "owner":
        metadata["full_name"] = "someone/else"
    else:
        metadata.pop("visibility")
    api, run = Mock(return_value=metadata), Mock()
    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    with pytest.raises(ValueError, match="verified public"):
        fleet.provision_maintenance_app(PUBLIC["full_name"])
    run.assert_not_called()
    assert api.call_count == 1


@pytest.mark.parametrize("destination", ["complete", "partial"])
def test_existing_maintenance_identity_is_never_overwritten_even_on_later_pages(
    monkeypatch: pytest.MonkeyPatch, destination: str
) -> None:
    monkeypatch.setenv("BOT_APP_ID", "test-id")
    monkeypatch.setenv("BOT_APP_KEY", "test-value")
    names = (
        ["BOT_APP_ID", "BOT_APP_KEY"] if destination == "complete" else ["BOT_APP_ID"]
    )
    api = Mock(
        side_effect=[
            {**PUBLIC, "visibility": "public", "disabled": False},
            {"secrets": [{"name": "other"}] * fleet.PAGE_SIZE},
            {"secrets": [{"name": name} for name in names]},
        ]
    )
    run = Mock()
    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    if destination == "partial":
        with pytest.raises(ValueError, match="partial maintenance"):
            fleet.provision_maintenance_app(PUBLIC["full_name"])
    else:
        fleet.provision_maintenance_app(PUBLIC["full_name"])
    run.assert_not_called()
    assert "page=2" in api.call_args.args[0]


def test_partial_maintenance_pair_stops_before_creating_any_git_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOT_APP_ID", "test-id")
    monkeypatch.setenv("BOT_APP_KEY", "test-value")
    run = Mock()

    def api(path: str, method: str = "GET", _data: Any = None) -> Any:
        assert method == "GET", "credentials must be checked before writing Git objects"
        if "/pulls?" in path:
            return []
        if "/actions/secrets?" in path:
            return {"secrets": [{"name": "BOT_APP_ID"}]}
        return {**PUBLIC, "visibility": "public", "disabled": False}

    monkeypatch.setattr(fleet, "github_api", api)
    monkeypatch.setattr(fleet.subprocess, "run", run)
    plan = {
        "repository": PUBLIC["full_name"],
        "files": {"README.md": "starter"},
        "parent": SHA,
        "tree": SHA,
        "base": "master",
    }
    with pytest.raises(ValueError, match="partial maintenance"):
        fleet.publish(plan)
    run.assert_not_called()
