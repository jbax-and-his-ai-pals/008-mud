"""Command-line validation for a single content root's region-authoring
policy (level bands, biome/region_type classification, hazard coverage),
without requiring a full, loadable content set.

Meant for fast feedback while regions are still being authored or bulk-
generated -- e.g. by the Godot world editor, right after generation,
before a region is wired into a complete world with a manifest and a
start room. `content_set_validator.py`/`run_content_checks.py` remain the
complete, authoritative check once a full content set exists.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from engine.server.content_set import ContentSetIssue, validate_region_policy  # noqa: E402

__all__ = ["ContentSetIssue", "validate_region_policy"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate regions under a content root against a ruleset's region-authoring policy.")
    parser.add_argument("content_root", help="Directory containing a 'regions' subfolder (and 'combat/elements.json' if hazard coverage is checked).")
    parser.add_argument("--ruleset", required=True, help="Path to the ruleset JSON declaring world.regions policy.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of text lines.")
    args = parser.parse_args()

    issues = validate_region_policy(Path(args.content_root), Path(args.ruleset))
    error_count = sum(1 for issue in issues if issue.severity == "error")

    if args.json:
        print(json.dumps({
            "ok": error_count == 0,
            "error_count": error_count,
            "warning_count": len(issues) - error_count,
            "issues": [{"severity": i.severity, "path": i.path, "message": i.message} for i in issues],
        }))
    else:
        for issue in issues:
            prefix = "ERROR" if issue.severity == "error" else "WARN"
            print(f"[{prefix}] {issue.path} - {issue.message}")
        if error_count == 0:
            print("Region policy check passed.")
        else:
            print(f"Region policy check failed: {error_count} error(s).")

    raise SystemExit(1 if error_count else 0)


if __name__ == "__main__":
    main()
