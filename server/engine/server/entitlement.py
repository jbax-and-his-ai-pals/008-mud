# engine/server/entitlement.py
"""
Product entitlement and feature-gating hooks.

Entitlements control which product features a session has access to. They
are loaded at server startup via the feature profile and can be extended by
operator config or plugins.

Gating Model:
  - Each product feature has a gate name (e.g. "pack.sample_world", "creator_sdk").
  - Sessions carry an entitlement list (from config, session bootstrap, or runtime grant).
  - The EntitlementGuard checks the session list against active gates before a feature is used.

Config (in server_config.json):
  "entitlements": {
    "default_session_grants": ["pack.sample_world"],
    "gates": {
      "creator_sdk": { "requires": ["creator_sdk"] },
      "pack.sample_world": { "requires": ["pack.sample_world"] }
    }
  }
"""
from __future__ import annotations
from typing import Any


class EntitlementGuard:
    """
    Checks session entitlements against configured feature gates.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        config = config or {}
        # Default grants applied to every new session
        self.default_grants: list[str] = list(config.get("default_session_grants", []))
        # Gate definitions: gate_name -> {"requires": [entitlement, ...]}
        self.gates: dict[str, dict[str, Any]] = dict(config.get("gates", {}))

    def apply_defaults(self, session_entitlements: list[str]) -> list[str]:
        """Merge default grants into a session entitlement list."""
        merged = list(session_entitlements)
        for g in self.default_grants:
            if g not in merged:
                merged.append(g)
        return merged

    def check(self, gate_name: str, session_entitlements: list[str]) -> tuple[bool, str]:
        """
        Returns (allowed, reason). If gate is not defined, access is allowed.
        """
        gate = self.gates.get(gate_name)
        if gate is None:
            # Undefined gate = open (whitelist model requires explicit gates)
            return True, ""

        required = gate.get("requires", [])
        for req in required:
            if req not in session_entitlements:
                return False, f"Feature '{gate_name}' requires entitlement '{req}'."
        return True, ""

    def describe_gates(self) -> dict[str, list[str]]:
        """Returns a mapping of gate name -> list of required entitlements."""
        return {name: gate.get("requires", []) for name, gate in self.gates.items()}
