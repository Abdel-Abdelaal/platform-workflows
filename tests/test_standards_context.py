import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock
from urllib.error import URLError

import pytest

from tools import standards_context


def test_html_reference_removes_non_content() -> None:
    html = (
        "<html><nav>navigation</nav><script>execute()</script>"
        "<style>hidden</style><main>real guidance</main></html>"
    )
    assert standards_context.visible_text(html) == "real guidance"
    assert (
        standards_context.visible_text("plain <type> markdown")
        == "plain <type> markdown"
    )


def test_current_sources_mark_unavailable_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        standards_context,
        "SOURCES",
        ("https://docs.example/one", "https://docs.example/two"),
    )
    monkeypatch.setattr(
        standards_context,
        "urlopen",
        Mock(side_effect=[URLError("offline"), BytesIO(b"current")]),
    )
    text = standards_context.collect_sources()
    assert "Reference unavailable" in text
    assert "UNTRUSTED CURRENT REFERENCE" in text
    assert "current" in text


def test_all_unavailable_sources_fail_instead_of_inventing_current_advice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(standards_context, "SOURCES", ("https://docs.example/one",))
    monkeypatch.setattr(standards_context, "urlopen", Mock(side_effect=TimeoutError))
    with pytest.raises(standards_context.CurrentDocsUnavailableError):
        standards_context.collect_sources()


def test_standards_cli_appends_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "context.md"
    output.write_text("source\n")
    monkeypatch.setattr(sys, "argv", ["tool", "--output", str(output)])
    monkeypatch.setattr(
        standards_context, "collect_sources", Mock(return_value="reference")
    )
    standards_context.main()
    assert output.read_text() == "source\nreference"
