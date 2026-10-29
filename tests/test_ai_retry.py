import json

from pydantic import ValidationError

from tools.ai_retry import validation_feedback


def test_feedback_bounds_errors_and_locations_and_never_echoes_custom_fields() -> None:
    error = ValidationError.from_exception_data(
        "test",
        [
            {
                "type": "bool_type",
                "loc": (
                    "comments",
                    index,
                    "private-secret",
                    "line",
                    "body",
                    "summary",
                    "path",
                ),
                "input": "private input",
            }
            for index in range(100)
        ],
    )
    feedback = validation_feedback(error)
    diagnostics = json.loads(feedback[feedback.index("[{") :])
    assert len(diagnostics) == 5
    assert all(
        item == {"field": "comments[].<field>.line.body.summary", "issue": "invalid"}
        for item in diagnostics
    )
    assert "private" not in feedback
    assert len(feedback) < 1000


def test_other_failures_do_not_become_schema_instructions() -> None:
    assert validation_feedback(ValueError("private error")) == ""
