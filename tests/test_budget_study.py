"""The budget study verifies frozen inputs and accounts for every condition."""

import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from tools import budget_study
from tools.ai_runner import EXPERIMENT_PROFILES
from tools.budget_study import StudyError

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs/budget-study-inputs.json"
WORKFLOW = ROOT / ".github/workflows/ai-budget-study.yml"


def inputs(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    files: dict[str, Path] = {}
    for name in budget_study.INPUTS:
        files[name] = tmp_path / name
        files[name].write_bytes(f"{name}\n".encode())
    spec = {
        "task": "t",
        "sha256": {
            name: budget_study.file_sha256(path) for name, path in files.items()
        },
    }
    return spec, files


def record(
    path: Path, *, status: str, durations: list[float], gap: bool = False
) -> Path:
    path.write_text(
        json.dumps(
            {
                "record_id": "r1",
                "status": status,
                "evidence_gap": gap,
                "configuration": {"requested_experiment_profile": "32000-600"},
                "attempts": [
                    {
                        "exit_category": "ok"
                        if status == "valid"
                        else "AnalysisUnavailableError",
                        "duration_seconds": seconds,
                        "gen_ai.response.finish_reasons": ["stop"],
                        "response": "private response text",
                        "response_sha256": "abc",
                    }
                    for seconds in durations
                ],
                "usage_totals": {
                    "gen_ai.usage.output_tokens": 10,
                    "gen_ai.usage.input_tokens": 5.0,
                    "other": 99,
                    "gen_ai.usage.flag": True,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_committed_spec_names_every_input_and_pins_full_commits() -> None:
    spec = budget_study.load_spec(SPEC)
    for key in ("base", "head"):
        assert len(spec[key]) == 40
    assert len(spec["handbook"]["commit"]) == 40
    assert (ROOT / spec["prompt"]).is_file()


def test_committed_prompt_still_matches_its_frozen_hash() -> None:
    spec = budget_study.load_spec(SPEC)
    assert budget_study.file_sha256(ROOT / spec["prompt"]) == spec["sha256"]["prompt"]


@pytest.mark.parametrize(
    "hashes",
    [{}, {"context": "x" * 64}, {name: "short" for name in budget_study.INPUTS}],
)
def test_spec_without_every_full_hash_is_refused(
    tmp_path: Path, hashes: dict[str, str]
) -> None:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps({"sha256": hashes}), encoding="utf-8")
    with pytest.raises(StudyError):
        budget_study.load_spec(path)


def test_verify_accepts_exact_bytes_and_names_changed_inputs(tmp_path: Path) -> None:
    spec, files = inputs(tmp_path)
    assert budget_study.verify(spec, files) == spec["sha256"]
    files["context"].write_bytes(b"context\r\n")
    files["diff"].write_bytes(b"changed\n")
    with pytest.raises(StudyError, match="context, diff"):
        budget_study.verify(spec, files)


def test_plan_is_a_reproducible_permutation_of_all_profiles() -> None:
    order = budget_study.plan("123-1")
    assert sorted(order) == sorted(EXPERIMENT_PROFILES)
    assert budget_study.plan("123-1") == order
    assert len({tuple(budget_study.plan(str(seed))) for seed in range(40)}) > 1


def test_outcome_keeps_metadata_and_drops_response_text(tmp_path: Path) -> None:
    path = record(tmp_path / "r.json", status="valid", durations=[900.5])
    result = budget_study.outcome("32000-600", path, 0)
    assert result["status"] == "valid"
    assert result["requested_profile"] == "32000-600"
    assert result["attempts"] == [
        {
            "exit_category": "ok",
            "duration_seconds": 900.5,
            "finish_reasons": ["stop"],
            "response_sha256": "abc",
        }
    ]
    assert result["usage_totals"] == {
        "gen_ai.usage.output_tokens": 10,
        "gen_ai.usage.input_tokens": 5.0,
    }
    assert "private response text" not in json.dumps(result)


def test_missing_or_corrupt_record_is_retained_as_missing(tmp_path: Path) -> None:
    assert (
        budget_study.outcome("32000-600", tmp_path / "absent.json", 124)["status"]
        == "missing_record"
    )
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    result = budget_study.outcome("32000-600", broken, 1)
    assert result == {
        "profile": "32000-600",
        "exit_code": 1,
        "status": "missing_record",
        "attempts": [],
    }
    assert budget_study.early_failure(result) is True


@pytest.mark.parametrize(
    ("status", "durations", "stop"),
    [
        ("valid", [5.0], False),
        ("no_valid_output", [5.0], True),
        ("no_valid_output", [], True),
        ("no_valid_output", [5.0, 3000.0], False),
        ("no_valid_output", [600.2], False),
    ],
)
def test_only_early_refusals_stop_the_study(
    tmp_path: Path, status: str, durations: list[float], stop: bool
) -> None:
    path = record(tmp_path / "r.json", status=status, durations=durations)
    assert (
        budget_study.early_failure(budget_study.outcome("131072-600", path, 1)) is stop
    )


def test_summary_lists_unattempted_conditions_in_planned_order(tmp_path: Path) -> None:
    spec = budget_study.load_spec(SPEC)
    seed = "7-1"
    first = budget_study.plan(seed)[0]
    done = budget_study.outcome(
        first, record(tmp_path / "r.json", status="no_valid_output", durations=[2]), 1
    )
    summary = budget_study.summarize(spec, seed, [done], unattempted_reason="stopped")
    assert summary["order"] == budget_study.plan(seed)
    assert [c["profile"] for c in summary["conditions"]] == summary["order"]
    assert summary["conditions"][0] == done
    assert all(
        c == {"profile": c["profile"], "status": "unattempted", "reason": "stopped"}
        for c in summary["conditions"][1:]
    )
    assert summary["correctness"] == "awaiting independent adjudication"
    assert summary["input_sha256"] == spec["sha256"]


def test_cli_records_ledger_and_summarizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger = tmp_path / "ledger.jsonl"
    path = record(tmp_path / "r.json", status="no_valid_output", durations=[3])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "study",
            "record",
            "--profile",
            "32000-600",
            "--record",
            str(path),
            "--exit-code",
            "1",
            "--ledger",
            str(ledger),
        ],
    )
    budget_study.main()
    assert capsys.readouterr().out.strip() == "stop"
    output = tmp_path / "summary.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "study",
            "summarize",
            "--spec",
            str(SPEC),
            "--seed",
            "s",
            "--ledger",
            str(ledger),
            "--unattempted-reason",
            "stopped",
            "--output",
            str(output),
        ],
    )
    budget_study.main()
    summary = json.loads(output.read_text(encoding="utf-8"))
    statuses = {c["profile"]: c["status"] for c in summary["conditions"]}
    assert statuses.pop("32000-600") == "no_valid_output"
    assert set(statuses.values()) == {"unattempted"}


def test_cli_plan_and_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["study", "plan", "--seed", "s"])
    budget_study.main()
    assert capsys.readouterr().out.split() == budget_study.plan("s")
    spec, files = inputs(tmp_path)
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    args = [f"--{name}={path}" for name, path in files.items()]
    monkeypatch.setattr(
        sys, "argv", ["study", "verify", "--spec", str(spec_path), *args]
    )
    budget_study.main()
    assert json.loads(capsys.readouterr().out) == spec["sha256"]


def test_summary_without_ledger_reports_every_condition_unattempted(
    tmp_path: Path,
) -> None:
    summary = budget_study.summarize(
        budget_study.load_spec(SPEC),
        "s",
        budget_study.read_ledger(tmp_path / "none"),
        unattempted_reason="dry run",
    )
    assert {c["status"] for c in summary["conditions"]} == {"unattempted"}


def test_workflow_is_manual_main_only_and_keeps_the_key_out_of_dry_runs() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert set(workflow[True]) == {"workflow_dispatch"}
    assert workflow["permissions"] == {}
    job = workflow["jobs"]["study"]
    assert job["if"] == "github.ref == 'refs/heads/main'"
    assert job["permissions"] == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }
    steps = job["steps"]
    keyed = [step for step in steps if "secrets.AI_API_KEY" in json.dumps(step)]
    assert [step["name"] for step in keyed] == [
        "Run each profile once in recorded random order"
    ]
    assert keyed[0]["if"] == "inputs.live"
    names = [step.get("name", step.get("uses", "")) for step in steps]
    assert names.index(
        "Build and verify frozen inputs before any provider call"
    ) < names.index(keyed[0]["name"])
    for step in steps:
        if (
            "upload-artifact" in step.get("uses", "")
            or step.get("name") == "Sign the evidence"
        ):
            assert "steps.scan.outcome == 'success'" in step["if"]
        if "checkout" in step.get("uses", ""):
            assert step["with"]["persist-credentials"] is False
    run = next(step for step in steps if step.get("id") == "run")
    assert run["env"]["AI_BASE_URL"] == "https://token-plan-ams.xiaomimimo.com/v1"
    assert "--thinking enabled" in run["run"]
