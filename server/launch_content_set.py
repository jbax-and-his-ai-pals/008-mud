"""Launch a selected content-set package through the TCP or WebSocket server."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTENT_SET = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"
DEFAULT_CONFIG = REPOSITORY_ROOT / "server" / "config" / "server_config.json"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Launch a versioned content set through the TCP or WebSocket server."
    )
    parser.add_argument("--transport", choices=["tcp", "ws"], default="tcp")
    parser.add_argument(
        "--content-set",
        default=str(DEFAULT_CONTENT_SET),
        help="Content-set directory or manifest path (defaults to Fantasy Frontier).",
    )
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Server configuration JSON path.")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved launch command without starting it.")
    args, passthrough = parser.parse_known_args()

    content_set_path = Path(args.content_set).resolve()
    manifest_path = content_set_path / "content_set.manifest.json" if content_set_path.is_dir() else content_set_path
    if not manifest_path.is_file():
        raise SystemExit(f"Content-set manifest not found: {manifest_path}")

    script_name = "poc_server.py" if args.transport == "tcp" else "poc_ws_server.py"
    script_path = REPOSITORY_ROOT / "server" / script_name
    command = [
        sys.executable,
        str(script_path),
        "--config",
        str(Path(args.config).resolve()),
        "--content-set",
        str(content_set_path),
        *passthrough,
    ]
    print(
        json.dumps(
            {
                "transport": args.transport,
                "content_set": str(content_set_path),
                "manifest": str(manifest_path),
                "command": command,
            }
        )
    )
    if args.dry_run:
        return
    raise SystemExit(subprocess.call(command, cwd=str(REPOSITORY_ROOT)))


if __name__ == "__main__":
    main()
