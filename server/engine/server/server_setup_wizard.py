from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


_DEFAULT_ENTITLEMENT_GATES: dict[str, dict[str, list[str]]] = {
    "operator.profile.apply": {"requires": ["operator.profile.apply"]},
    "operator.world_effects.manage": {"requires": ["operator.world_effects.manage"]},
    "operator.feature_profile.toggle": {"requires": ["operator.feature_profile.toggle"]},
    "operator.world.debug": {"requires": ["operator.world.debug"]},
    "creator_sdk.authoring": {"requires": ["creator_sdk.authoring"]},
}


@dataclass(frozen=True)
class WizardPreset:
    preset_id: str
    feature_profile: dict[str, Any]
    session_default_capabilities: list[str]
    session_default_entitlements: list[str]
    authz_detail_level: str
    gm_auth_token_required: bool
    starter_items: list[dict[str, Any]]


_PRESETS: dict[str, WizardPreset] = {
    "static_world": WizardPreset(
        preset_id="static_world",
        feature_profile={
            "combat": {"mode": "disabled"},
            "weather": {"mode": "disabled"},
            "world_effects": {"mode": "disabled"},
            "authoring": {"mode": "disabled"},
            "world_mutation": {"mode": "readonly"},
            "mods": {"mode": "disabled"},
        },
        session_default_capabilities=[],
        session_default_entitlements=[],
        authz_detail_level="minimal",
        gm_auth_token_required=False,
        starter_items=[],
    ),
    "social_no_combat": WizardPreset(
        preset_id="social_no_combat",
        feature_profile={
            "combat": {"mode": "disabled"},
            "weather": {"mode": "builtin"},
            "world_effects": {"mode": "custom", "provider_id": "sample.effects.balance"},
            "authoring": {"mode": "gm_only"},
            "world_mutation": {"mode": "mutable"},
            "mods": {"mode": "enabled"},
        },
        session_default_capabilities=[],
        session_default_entitlements=[],
        authz_detail_level="full",
        gm_auth_token_required=True,
        starter_items=[],
    ),
    "creator_sandbox": WizardPreset(
        preset_id="creator_sandbox",
        feature_profile={
            "combat": {"mode": "enabled"},
            "weather": {"mode": "builtin"},
            "world_effects": {"mode": "enabled"},
            "authoring": {"mode": "all"},
            "world_mutation": {"mode": "mutable"},
            "mods": {"mode": "enabled"},
        },
        session_default_capabilities=["authoring.gm"],
        session_default_entitlements=[
            "creator_sdk.authoring",
            "operator.profile.apply",
            "operator.world_effects.manage",
            "operator.feature_profile.toggle",
            "operator.world.debug",
        ],
        authz_detail_level="full",
        gm_auth_token_required=False,
        starter_items=[],
    ),
}


def list_wizard_presets() -> list[str]:
    return sorted(_PRESETS.keys())


def build_server_bootstrap_artifacts(
    preset_id: str,
    *,
    server_name: str,
    content_set_path: str,
    host: str = "127.0.0.1",
    tcp_port: int = 8765,
    ws_port: int = 8766,
    save_file: str = "server_save.json",
    asset_db: str = ":memory:",
    gm_auth_token: str = "",
) -> dict[str, Any]:
    preset = _PRESETS.get(str(preset_id).strip().lower())
    if preset is None:
        supported = ", ".join(list_wizard_presets())
        raise ValueError(f"Unknown preset_id '{preset_id}'. Supported presets: {supported}")
    if str(server_name).strip() == "":
        raise ValueError("server_name is required")

    package_path = Path(content_set_path).resolve()
    package_root = package_path if package_path.is_dir() else package_path.parent
    if not (package_root / "content_set.manifest.json").is_file():
        raise ValueError("content_set_path must resolve to a content-set package or manifest")
    profile_filename = f"{str(server_name).strip().lower().replace(' ', '_')}.profile.json"
    config_filename = f"{str(server_name).strip().lower().replace(' ', '_')}.server_config.json"
    profile_path = str(package_root / "data" / "profiles" / profile_filename)

    resolved_gm_auth_token = str(gm_auth_token).strip()
    if preset.gm_auth_token_required and resolved_gm_auth_token == "":
        resolved_gm_auth_token = "replace-with-strong-token"

    config_payload: dict[str, Any] = {
        "server": {
            "host": str(host),
            "port": int(tcp_port),
            "save_file": str(save_file),
            "asset_db": str(asset_db),
        },
        "websocket": {
            "port": int(ws_port),
        },
        "feature_profile": {
            "path": profile_path,
        },
        "world_bootstrap": {
            "starter_items": list(preset.starter_items),
        },
        "session": {
            "default_capabilities": list(preset.session_default_capabilities),
            "default_entitlements": list(preset.session_default_entitlements),
            "authz_detail_level": preset.authz_detail_level,
            "gm_auth_token": resolved_gm_auth_token,
        },
        "entitlements": {
            "default_session_grants": [],
            "gates": dict(_DEFAULT_ENTITLEMENT_GATES),
        },
    }

    return {
        "preset_id": preset.preset_id,
        "server_name": str(server_name).strip(),
        "profile_path": profile_path,
        "profile_filename": profile_filename,
        "config_filename": config_filename,
        "profile_payload": dict(preset.feature_profile),
        "config_payload": config_payload,
    }
