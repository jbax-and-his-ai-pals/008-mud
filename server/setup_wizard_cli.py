from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from engine.server.feature_profile import FeatureProfile
from engine.server.server_config import resolve_server_settings
from engine.server.server_setup_wizard import (
    build_server_bootstrap_artifacts,
    list_wizard_presets,
)


def _write_json_file(path: Path, payload: dict, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate validated server/profile bootstrap files from wizard presets.")
    parser.add_argument("--preset", required=True, choices=list_wizard_presets())
    parser.add_argument("--server-name", required=True)
    parser.add_argument("--content-set", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--tcp-port", type=int, default=8765)
    parser.add_argument("--ws-port", type=int, default=8766)
    parser.add_argument("--save-file", default="server_save.json")
    parser.add_argument("--asset-db", default=":memory:")
    parser.add_argument("--gm-auth-token", default="")
    parser.add_argument("--config-dir", default="server/config")
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    args = parser.parse_args(argv)

    artifact = build_server_bootstrap_artifacts(
        args.preset,
        server_name=args.server_name,
        content_set_path=args.content_set,
        host=args.host,
        tcp_port=args.tcp_port,
        ws_port=args.ws_port,
        save_file=args.save_file,
        asset_db=args.asset_db,
        gm_auth_token=args.gm_auth_token,
    )

    profile_path = Path(artifact["profile_path"])
    config_path = Path(args.config_dir) / artifact["config_filename"]

    # Validate generated profile + config through existing runtime contracts.
    profile = FeatureProfile.from_dict(artifact["profile_payload"])
    _ = resolve_server_settings(
        "tcp",
        artifact["config_payload"],
        None,
        None,
        None,
        None,
        None,
        None,
        str(config_path),
    )
    if profile.warnings:
        print("Profile warnings:")
        for warning in profile.warnings:
            print(f"- {warning}")

    _write_json_file(profile_path, artifact["profile_payload"], force=args.force)
    _write_json_file(config_path, artifact["config_payload"], force=args.force)

    print(
        json.dumps(
            {
                "status": "ok",
                "preset": args.preset,
                "server_name": args.server_name,
                "profile_path": str(profile_path),
                "config_path": str(config_path),
            }
        )
    )
    return 0


def main() -> None:
    try:
        code = run()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
