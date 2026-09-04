"""Command-line validation for the engine-owned content-set contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))

from engine.server.content_set import (  # noqa: E402
    CONTENT_SET_MANIFEST_NAME,
    CONTENT_SET_SCHEMA_VERSION,
    RUNTIME_API_VERSION,
    ContentSetDefinition,
    ContentSetIssue,
    load_content_set,
    validate_content_set,
)

__all__ = [
    "CONTENT_SET_MANIFEST_NAME",
    "CONTENT_SET_SCHEMA_VERSION",
    "RUNTIME_API_VERSION",
    "ContentSetDefinition",
    "ContentSetIssue",
    "load_content_set",
    "validate_content_set",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a versioned content-set package.")
    parser.add_argument("content_set", nargs="?", default="content_sets/fantasy_frontier", help="Content-set directory or manifest path.")
    parser.add_argument("--runtime-api", default=RUNTIME_API_VERSION, help="Engine runtime API version.")
    args = parser.parse_args()

    definition, issues = load_content_set(Path(args.content_set), runtime_api=args.runtime_api)
    for issue in issues:
        prefix = "ERROR" if issue.severity == "error" else "WARN"
        print(f"[{prefix}] {issue.path} - {issue.message}")
    if definition is None:
        print("Content set is invalid.")
        raise SystemExit(1)
    print(
        f"Content set '{definition.content_set_id}' is valid "
        f"(data root: {definition.data_root}, start: {definition.start_region_id}:{definition.start_room_id})."
    )


if __name__ == "__main__":
    main()
