from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any


@dataclass
class ServerSettings:
    host: str
    port: int
    save_file: str
    asset_db: str
    data_root: str | None
    feature_profile_path: str | None
    session_default_capabilities: list[str]
    session_default_entitlements: list[str]
    session_authz_detail_level: str
    session_gm_auth_token: str | None
    entitlement_policy: dict[str, Any]
    abuse_max_command_chars: int
    abuse_max_envelope_bytes: int
    abuse_command_rate_limit_per_sec: float
    abuse_command_burst: int
    world_bootstrap_starter_items: list[dict[str, Any] | str]
    session_require_character_creation: bool
    boot_warning_fail_codes: list[str]
    config_path: str | None


def load_server_config(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            parsed = json.load(f)
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def resolve_server_settings(
    transport: str,
    config_payload: dict[str, Any],
    cli_host: str | None,
    cli_port: int | None,
    cli_save: str | None,
    cli_asset_db: str | None,
    cli_data_root: str | None,
    cli_profile_path: str | None,
    config_path: str | None,
) -> ServerSettings:
    server_cfg = config_payload.get("server", {}) if isinstance(config_payload.get("server"), dict) else {}
    ws_cfg = config_payload.get("websocket", {}) if isinstance(config_payload.get("websocket"), dict) else {}
    profile_cfg = (
        config_payload.get("feature_profile", {})
        if isinstance(config_payload.get("feature_profile"), dict)
        else {}
    )
    session_cfg = (
        config_payload.get("session", {})
        if isinstance(config_payload.get("session"), dict)
        else {}
    )
    abuse_cfg = (
        config_payload.get("abuse_safeguards", {})
        if isinstance(config_payload.get("abuse_safeguards"), dict)
        else {}
    )
    world_bootstrap_cfg = (
        config_payload.get("world_bootstrap", {})
        if isinstance(config_payload.get("world_bootstrap"), dict)
        else {}
    )
    startup_diag_cfg = (
        config_payload.get("startup_diagnostics", {})
        if isinstance(config_payload.get("startup_diagnostics"), dict)
        else {}
    )
    default_caps: list[str] = []
    raw_caps = session_cfg.get("default_capabilities", [])
    if isinstance(raw_caps, list):
        for cap in raw_caps:
            text = str(cap).strip()
            if text:
                default_caps.append(text)
    gm_auth_token_raw = session_cfg.get("gm_auth_token", None)
    gm_auth_token: str | None = None
    if gm_auth_token_raw is not None:
        token_text = str(gm_auth_token_raw).strip()
        if token_text != "":
            gm_auth_token = token_text
    default_entitlements: list[str] = []
    raw_entitlements = session_cfg.get("default_entitlements", [])
    if isinstance(raw_entitlements, list):
        for ent in raw_entitlements:
            text = str(ent).strip()
            if text:
                default_entitlements.append(text)
    entitlement_cfg = (
        config_payload.get("entitlements", {})
        if isinstance(config_payload.get("entitlements"), dict)
        else {}
    )
    raw_authz_detail_level = str(session_cfg.get("authz_detail_level", "full")).strip().lower()
    authz_detail_level = "minimal" if raw_authz_detail_level == "minimal" else "full"
    starter_items: list[dict[str, Any] | str] = []
    raw_starters = world_bootstrap_cfg.get("starter_items", [])
    if isinstance(raw_starters, list):
        for entry in raw_starters:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    starter_items.append(text)
            elif isinstance(entry, dict):
                item_id = str(entry.get("item_id", "")).strip()
                if item_id:
                    starter_items.append(
                        {
                            "item_id": item_id,
                            "quantity": int(entry.get("quantity", 1)),
                        }
                    )
    boot_warning_fail_codes: list[str] = []
    raw_fail_codes = startup_diag_cfg.get("fail_on_warning_codes", [])
    if isinstance(raw_fail_codes, list):
        for code in raw_fail_codes:
            text = str(code).strip()
            if text:
                boot_warning_fail_codes.append(text)

    default_port = 8765 if transport == "tcp" else 8766
    config_port = int(ws_cfg.get("port", default_port)) if transport == "ws" else int(server_cfg.get("port", default_port))
    resolved_profile = cli_profile_path
    if resolved_profile is None:
        resolved_profile = profile_cfg.get("path") or server_cfg.get("feature_profile_path")
    return ServerSettings(
        host=cli_host or str(server_cfg.get("host", "127.0.0.1")),
        port=int(cli_port) if cli_port is not None else config_port,
        save_file=cli_save or str(server_cfg.get("save_file", "server_save.json")),
        asset_db=cli_asset_db or str(server_cfg.get("asset_db", ":memory:")),
        data_root=(
            str(cli_data_root).strip()
            if cli_data_root is not None and str(cli_data_root).strip() != ""
            else (
                str(server_cfg.get("data_root")).strip()
                if str(server_cfg.get("data_root", "")).strip() != ""
                else None
            )
        ),
        feature_profile_path=str(resolved_profile) if resolved_profile else None,
        session_default_capabilities=default_caps,
        session_default_entitlements=default_entitlements,
        session_authz_detail_level=authz_detail_level,
        session_gm_auth_token=gm_auth_token,
        entitlement_policy=entitlement_cfg,
        abuse_max_command_chars=int(abuse_cfg.get("max_command_chars", 512)),
        abuse_max_envelope_bytes=int(abuse_cfg.get("max_envelope_bytes", 8192)),
        abuse_command_rate_limit_per_sec=float(abuse_cfg.get("command_rate_limit_per_sec", 8.0)),
        abuse_command_burst=int(abuse_cfg.get("command_burst", 16)),
        world_bootstrap_starter_items=starter_items,
        session_require_character_creation=True,
        boot_warning_fail_codes=boot_warning_fail_codes,
        config_path=config_path,
    )
