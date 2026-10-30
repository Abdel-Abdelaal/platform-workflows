"""Keep the proposed maintenance identity separate from enrollment privileges."""

import json
from pathlib import Path


def test_maintenance_manifest_has_only_reviewed_maintenance_permissions():
    proposed = json.loads(
        Path("docs/maintenance-automation-app.json").read_text(encoding="utf-8")
    )
    enrollment = json.loads(
        Path("docs/fleet-automation-app.json").read_text(encoding="utf-8")
    )
    permissions = proposed["default_permissions"]
    assert permissions == {
        "metadata": "read",
        "contents": "write",
        "pull_requests": "write",
        "issues": "write",
        "workflows": "write",
    }
    assert set(permissions) - set(enrollment["default_permissions"]) == {"issues"}
    assert set(enrollment["default_permissions"]) - set(permissions) == {"secrets"}
    assert proposed["public"] is False
    assert proposed["default_events"] == []
