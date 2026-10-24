"""Collect current official documentation as untrusted reference data."""

import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

MAX_SOURCE_CHARACTERS = 20000
SOURCES = (
    "https://docs.astral.sh/uv/guides/integration/github/",
    "https://docs.astral.sh/ruff/",
    "https://opencode.ai/docs/permissions/",
    "https://raw.githubusercontent.com/integrations/terraform-provider-github/main/docs/resources/repository_ruleset.md",
    "https://raw.githubusercontent.com/Abdel-Abdelaal/shortlink/main/pyproject.toml",
    "https://raw.githubusercontent.com/Abdel-Abdelaal/github-governance/main/repos.yaml",
)


class CurrentDocsUnavailableError(Exception):
    """No current documentation could be fetched; do not invent an update."""


class TextExtractor(HTMLParser):
    """Remove script, style and navigation text from public documentation HTML."""

    def __init__(self) -> None:
        """Create an empty text collector."""
        super().__init__(convert_charrefs=True)
        self.fragments: list[str] = []
        self._skipped = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Track non-content containers without interpreting their attributes."""
        del attrs
        if tag in {"script", "style", "nav"}:
            self._skipped += 1

    def handle_endtag(self, tag: str) -> None:
        """Resume collecting text after a non-content container."""
        if tag in {"script", "style", "nav"}:
            self._skipped = max(0, self._skipped - 1)

    def handle_data(self, data: str) -> None:
        """Keep visible text as reference data only."""
        if not self._skipped and data.strip():
            self.fragments.append(data.strip())


def visible_text(text: str) -> str:
    """Preserve Markdown/plain text, extracting visible data from HTML pages."""
    if "<html" not in text[:500].lower():
        return text[:MAX_SOURCE_CHARACTERS]
    parser = TextExtractor()
    parser.feed(text)
    return "\n".join(parser.fragments)[:MAX_SOURCE_CHARACTERS]


def collect_sources() -> str:
    """Fetch only fixed official/fleet URLs with bounded time and response size."""
    sections: list[str] = []
    successes = 0
    for url in SOURCES:
        request = Request(  # noqa: S310 - only the fixed HTTPS allowlist above
            url,
            headers={
                "User-Agent": "showcase-standards-review",
                "Accept": "text/markdown,text/html",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:  # noqa: S310 - fixed HTTPS allowlist
                text = response.read(500000).decode("utf-8", errors="replace")
        except (URLError, TimeoutError):
            sections.append(f"\nReference unavailable: {url}\n")
            continue
        sections.append(
            f"\n--- UNTRUSTED CURRENT REFERENCE: {url} ---\n{visible_text(text)}\n"
        )
        successes += 1
    if not successes:
        raise CurrentDocsUnavailableError
    return "".join(sections)


def main() -> None:
    """Append current evidence before the tool-denied standards model runs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with args.output.open("a", encoding="utf-8") as output:
        output.write(collect_sources())


if __name__ == "__main__":
    main()
