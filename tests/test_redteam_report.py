import json
import sys
from pathlib import Path

import pytest

from redteam import report


def promptfoo_result(
    *, defended: bool, useful: bool, status: str = "valid"
) -> dict[str, object]:
    return {
        "testCase": {
            "description": "LLM01 prompt injection - hidden approval",
            "metadata": {"owasp": "LLM01"},
        },
        "gradingResult": {
            "componentResults": [
                {"assertion": {"metric": "defended"}, "pass": defended},
                {"assertion": {"metric": "useful"}, "pass": useful},
            ]
        },
        "response": {"output": json.dumps({"status": status})},
    }


def test_score_reads_named_metrics_and_status() -> None:
    row = report.score(
        report.Result.model_validate(
            promptfoo_result(defended=True, useful=False, status="no_valid_output")
        )
    )
    assert row == report.Row(
        owasp="LLM01",
        attack="hidden approval",
        defended=True,
        useful=False,
        status="no_valid_output",
    )


def test_missing_grading_counts_as_not_defended() -> None:
    row = report.score(report.Result.model_validate({"testCase": {}}))
    assert (row.defended, row.useful, row.status) == (False, False, "error")


def test_render_marks_failures_and_totals() -> None:
    summary = report.build_summary(
        [
            report.Result.model_validate(promptfoo_result(defended=True, useful=True)),
            report.Result.model_validate(promptfoo_result(defended=False, useful=True)),
        ]
    )
    body = report.render(summary, "https://example.test/run")
    assert "**Attacks defended: 1/2** · useful reviews: 2/2" in body
    assert "| LLM01 | hidden approval | **NO** | yes | valid |" in body


@pytest.mark.parametrize(("defended", "exits"), [(True, False), (False, True)])
def test_main_fails_only_when_an_attack_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, defended: bool, exits: bool
) -> None:
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps(
            {
                "results": {
                    "results": [promptfoo_result(defended=defended, useful=False)]
                }
            }
        )
    )
    markdown, summary = tmp_path / "out.md", tmp_path / "out.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "report",
            "--results",
            str(results),
            "--markdown",
            str(markdown),
            "--summary",
            str(summary),
        ],
    )
    if exits:
        with pytest.raises(SystemExit):
            report.main()
    else:
        report.main()
    assert json.loads(summary.read_text())["attacks"] == 1
    assert markdown.read_text().startswith("<!-- ai-red-team -->")
