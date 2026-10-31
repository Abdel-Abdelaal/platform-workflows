import json

import pytest

from redteam import provider

SKIP = {"status": "no_valid_output", "published": "", "missing_key": True}


def test_run_attack_without_key_returns_structured_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert provider.run_attack("diff --git a/src/app.py b/src/app.py", "review") == SKIP


def test_call_api_without_key_returns_structured_skip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AI_API_KEY", raising=False)
    response = provider.call_api(
        "diff --git a/src/app.py b/src/app.py", {}, {"vars": {"mode": "review"}}
    )
    assert json.loads(response["output"]) == SKIP


def test_analysis_unavailable_still_returns_no_valid_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_API_KEY", "fake-test-key")

    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise provider.AnalysisUnavailableError("unavailable")

    monkeypatch.setattr(provider, "analyze", unavailable)
    assert provider.run_attack("diff --git a/src/app.py b/src/app.py", "review") == {
        "status": "no_valid_output",
        "published": "",
    }
