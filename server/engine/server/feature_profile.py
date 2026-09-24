from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


_ALLOWED_MODES: dict[str, set[str]] = {
    "world.mode": {"", "single_player_story", "co_op_party", "persistent_shard", "readonly_archive", "finite_adventure"},
    "combat.mode": {"enabled", "disabled"},
    "weather.mode": {"builtin", "disabled", "custom"},
    "world_effects.mode": {"enabled", "disabled", "custom"},
    "authoring.mode": {"all", "gm_only", "disabled"},
    "world_mutation.mode": {"mutable", "readonly"},
    "mods.mode": {"enabled", "disabled"},
    "permadeath.mode": {"enabled", "disabled"},
}


# Categories whose `provider_id` names a plugin provider (read by
# headless/world_effects.py::_configured_custom_provider_id, only in "custom").
PROVIDER_CATEGORIES = ("weather", "world_effects")

# The policy sections the server reads beside the modes, and what each key's
# reader acts on. A list is the values it distinguishes (the first is its
# default); "bool", "seconds", "text" and "campaign" are typed values. Written
# from the readers in headless/party.py, shard.py and finite_adventure.py.
PROFILE_POLICIES: dict[str, dict[str, Any]] = {
    "party": {
        "loot_policy": ["round_robin", "leader_discretion", "finder_keep"],
        "shared_rewards_policy": ["split", "leader_claims"],
        "shared_quest_policy": ["leader_driven", "mirror_all"],
        "offline_invites_supported": "bool",
    },
    "persistent_shard": {
        "session_resume_policy": ["enabled", "disabled"],
        "late_join_policy": ["enabled", "disabled"],
        "disconnect_timeout_policy": ["indefinite", "grace_window"],
        "disconnect_timeout_seconds": "seconds",
        "initial_runtime_state": ["normal", "drain", "freeze", "maintenance"],
        "initial_runtime_message": "text",
    },
    "finite_adventure": {
        "default_campaign_id": "campaign",
        "replay_supported": "bool",
        "checkpoint_policy": ["manual_save", "disabled"],
    },
}
# `shard` is read as another name for `persistent_shard` (shard.py).
POLICY_ALIASES = {"shard": "persistent_shard"}
# Words the readers treat as "disabled" for these policies.
POLICY_SYNONYMS: dict[str, dict[str, str]] = {
    "session_resume_policy": {"forbidden": "disabled", "off": "disabled"},
    "late_join_policy": {"forbidden": "disabled", "off": "disabled", "closed": "disabled"},
    "checkpoint_policy": {"off": "disabled", "none": "disabled"},
}


def allowed_modes() -> dict[str, list[str]]:
    """Each category's modes, the default first (for the editor's parity check)."""
    defaults = FeatureProfile()
    out: dict[str, list[str]] = {}
    for path, values in _ALLOWED_MODES.items():
        category = path.split(".")[0]
        default = getattr(defaults, f"{category}_mode")
        out[category] = [default] + sorted(value for value in values if value != default)
    return out


@dataclass
class FeatureProfile:
    world_mode: str = ""
    combat_mode: str = "enabled"
    weather_mode: str = "builtin"
    world_effects_mode: str = "enabled"
    authoring_mode: str = "all"
    world_mutation_mode: str = "mutable"
    mods_mode: str = "enabled"
    permadeath_mode: str = "disabled"
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FeatureProfile":
        warnings: list[str] = []

        def _mode(path: str, default: str) -> str:
            root, leaf = path.split(".")
            root_obj = payload.get(root, {})
            if not isinstance(root_obj, dict):
                return default
            raw_value = root_obj.get(leaf, default)
            value = str(raw_value).strip().lower() or default
            allowed = _ALLOWED_MODES.get(path, set())
            if allowed and value not in allowed:
                warnings.append(
                    f"Invalid mode '{raw_value}' for {path}; using default '{default}'."
                )
                return default
            return value

        world_effects_mode = _mode("world_effects.mode", "enabled")

        return cls(
            world_mode=_mode("world.mode", ""),
            combat_mode=_mode("combat.mode", "enabled"),
            weather_mode=_mode("weather.mode", "builtin"),
            world_effects_mode=world_effects_mode,
            authoring_mode=_mode("authoring.mode", "all"),
            world_mutation_mode=_mode("world_mutation.mode", "mutable"),
            mods_mode=_mode("mods.mode", "enabled"),
            permadeath_mode=_mode("permadeath.mode", "disabled"),
            raw=payload,
            warnings=warnings,
        )

    @classmethod
    def load(cls, path: str | None) -> "FeatureProfile":
        if not path:
            return cls()
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                parsed = json.load(f)
        except Exception:
            return cls()
        if not isinstance(parsed, dict):
            return cls()
        return cls.from_dict(parsed)

    def set_mode(self, category: str, value: str) -> tuple[bool, str]:
        path = f"{category}.mode"
        if path not in _ALLOWED_MODES:
            return False, f"Unknown category '{category}'"
        
        if value not in _ALLOWED_MODES[path]:
            return False, f"Invalid mode '{value}' for {category}. Allowed: {', '.join(_ALLOWED_MODES[path])}"
        
        attr_name = f"{category}_mode"
        setattr(self, attr_name, value)
        return True, f"Set {category} mode to {value}."

    def resolved_world_mode(self) -> str:
        explicit = str(self.world_mode).strip().lower()
        if explicit in {"single_player_story", "co_op_party", "persistent_shard", "readonly_archive", "finite_adventure"}:
            return explicit
        if self.world_mutation_mode == "readonly" and self.authoring_mode == "disabled":
            return "readonly_archive"
        return "persistent_shard"

    def authoring_allowed(self) -> bool:
        return self.authoring_mode in {"all", "gm_only"}

    def world_mutation_allowed(self) -> bool:
        return self.world_mutation_mode == "mutable"

    def weather_enabled(self) -> bool:
        return self.weather_mode != "disabled"

    def world_effects_enabled(self) -> bool:
        return self.world_effects_mode != "disabled"
        
    def permadeath_enabled(self) -> bool:
        return self.permadeath_mode == "enabled"
