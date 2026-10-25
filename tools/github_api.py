"""Make structured GitHub API requests without shell interpolation."""

import json
import subprocess
from collections.abc import Mapping


def github_api(
    endpoint: str, method: str = "GET", body: Mapping[str, object] | None = None
) -> object:
    """Run gh with an argument list and optional JSON on standard input."""
    command = ["gh", "api", endpoint, "--method", method]
    if body is not None:
        command.extend(["--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(body) if body is not None else None,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None
