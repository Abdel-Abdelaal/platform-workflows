"""Run a tool-denied model in a clean directory without GitHub credentials."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from tools.ai_contract import Analysis, extract_text, parse_analysis

MODEL = "mimo/mimo-v2.6-flash"
BASE_URL = "https://token-plan-ams.xiaomimimo.com/v1"
SAFE_ENVIRONMENT = {
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "COMSPEC",
    "PATHEXT",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "WINDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
}


class MissingRunnerError(Exception):
    """Install the pinned OpenCode CLI before running coding analysis."""


def runner_config() -> dict[str, object]:
    """Fix both primary and small models to the owner's selected Flash model."""
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": MODEL,
        "small_model": MODEL,
        "enabled_providers": ["mimo"],
        "autoupdate": False,
        "share": "disabled",
        "provider": {
            "mimo": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Xiaomi MiMo Flash",
                "options": {
                    "baseURL": os.environ.get("AI_BASE_URL", BASE_URL),
                    "apiKey": "{env:AI_API_KEY}",
                },
                "models": {
                    "mimo-v2.6-flash": {
                        "name": "MiMo 2.6 Flash",
                        "limit": {"context": 1048576, "output": 8192},
                    }
                },
            }
        },
        "permission": {"*": "deny"},
        "agent": {
            "review": {
                "description": "Tool-denied coding analysis",
                "mode": "primary",
                "steps": 3,
                "permission": {"*": "deny"},
            }
        },
        "default_agent": "review",
    }


def isolated_environment(workspace: Path, key: str) -> dict[str, str]:
    """Pass OS plumbing and only the AI key, excluding GitHub and App credentials."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() in SAFE_ENVIRONMENT
    }
    environment.update(
        {
            "AI_API_KEY": key,
            "OPENCODE_CONFIG_CONTENT": json.dumps(runner_config()),
            "XDG_CONFIG_HOME": str(workspace / "config"),
            "XDG_DATA_HOME": str(workspace / "data"),
            "XDG_CACHE_HOME": str(workspace / "cache"),
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_DISABLE_CLAUDE_CODE": "true",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "true",
            "OPENCODE_DISABLE_DEFAULT_PLUGINS": "true",
            "OPENCODE_DISABLE_LSP_DOWNLOAD": "true",
            "OPENCODE_DISABLE_MODELS_FETCH": "true",
        }
    )
    return environment


def analyze(context: str, prompt: str, key: str) -> Analysis:
    """Return validated analysis without executing project config or model tools."""
    executable = shutil.which("opencode")
    if executable is None:
        raise MissingRunnerError
    with tempfile.TemporaryDirectory(prefix="showcase-ai-") as directory:
        workspace = Path(directory)
        context_file = workspace / "context.md"
        context_file.write_text(context, encoding="utf-8")
        result = subprocess.run(
            [
                executable,
                "run",
                "--pure",
                "--agent",
                "review",
                "--format",
                "json",
                "--file",
                str(context_file),
                "--",
                prompt,
            ],
            cwd=workspace,
            env=isolated_environment(workspace, key),
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
        )
    return parse_analysis(extract_text(result.stdout))


def main() -> None:
    """Read a prepared context and trusted prompt, then save validated model JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    key = os.environ.get("AI_API_KEY", "")
    if not key:
        args.output.write_text('{"skipped": "AI_API_KEY missing"}', encoding="utf-8")
        return
    result = analyze(
        args.context.read_text(encoding="utf-8"),
        args.prompt.read_text(encoding="utf-8"),
        key,
    )
    args.output.write_text(result.model_dump_json(indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
