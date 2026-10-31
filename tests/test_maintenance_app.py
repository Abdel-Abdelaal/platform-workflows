"""Keep the proposed maintenance identity separate from enrollment privileges."""

import json
from pathlib import Path


def test_maintenance_manifest_has_only_reviewed_maintenance_permissions():
    root = Path(__file__).resolve().parents[1]
    proposed = json.loads(
        (root / "docs/maintenance-automation-app.json").read_text(encoding="utf-8")
    )
    enrollment = json.loads(
        (root / "docs/fleet-automation-app.json").read_text(encoding="utf-8")
    )
    permissions = proposed["default_permissions"]
    assert permissions == {
        "metadata": "read",
        "contents": "write",
        "pull_requests": "write",
        "issues": "write",
        "workflows": "write",
    }
    assert "secrets" not in permissions
    assert "issues" not in enrollment["default_permissions"]
    assert proposed["public"] is False
    assert proposed["default_events"] == []
