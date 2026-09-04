import json
import os
import sys
import importlib.util
from typing import Dict, Any, List, Optional
import traceback

class PermissionError(Exception):
    pass

PLUGIN_MANIFEST_SCHEMA_VERSION = "1"
ENGINE_API_VERSION = "1.0"
ALLOWED_PLUGIN_CAPABILITIES = {
    "command_registration",
    "world_modification",
    "server_broadcast",
    "system_provider_registration",
}


def _parse_version(value: str):
    text = str(value).strip()
    if text == "":
        return None
    parts = text.split(".")
    out = []
    for p in parts:
        if not p.isdigit():
            return None
        out.append(int(p))
    return tuple(out)


def _version_in_range(current: str, min_v: str, max_v: str) -> bool:
    c = _parse_version(current)
    mn = _parse_version(min_v)
    mx = _parse_version(max_v)
    if c is None or mn is None or mx is None:
        return False
    return mn <= c <= mx


def validate_plugin_manifest(manifest: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_str = [
        "plugin_id",
        "name",
        "version",
        "manifest_schema_version",
        "engine_api_min",
        "engine_api_max",
    ]
    for field in required_str:
        value = manifest.get(field)
        if not isinstance(value, str) or value.strip() == "":
            errors.append(f"Manifest missing/invalid '{field}'")
    schema_version = str(manifest.get("manifest_schema_version", "")).strip()
    if schema_version != "" and schema_version != PLUGIN_MANIFEST_SCHEMA_VERSION:
        errors.append(
            f"Unsupported manifest_schema_version '{schema_version}' "
            f"(expected '{PLUGIN_MANIFEST_SCHEMA_VERSION}')"
        )
    min_v = str(manifest.get("engine_api_min", "")).strip()
    max_v = str(manifest.get("engine_api_max", "")).strip()
    if min_v and max_v:
        min_parsed = _parse_version(min_v)
        max_parsed = _parse_version(max_v)
        if min_parsed is None or max_parsed is None:
            errors.append("engine_api_min/engine_api_max must be dotted numeric versions")
        elif min_parsed > max_parsed:
            errors.append("engine_api_min must be <= engine_api_max")
        elif not _version_in_range(ENGINE_API_VERSION, min_v, max_v):
            errors.append(
                f"Engine API {ENGINE_API_VERSION} is outside plugin supported "
                f"range {min_v}..{max_v}"
            )
    caps = manifest.get("capabilities")
    if not isinstance(caps, list):
        errors.append("Manifest 'capabilities' must be an array")
    else:
        for cap in caps:
            cap_text = str(cap).strip()
            if cap_text not in ALLOWED_PLUGIN_CAPABILITIES:
                errors.append(f"Unknown capability '{cap_text}'")
    return errors

class PluginAPI:
    """The safe extension API surface exposed to mods."""
    def __init__(self, game_manager, manifest: Dict[str, Any]):
        self._game = game_manager
        self._manifest = manifest
        self._capabilities = set(manifest.get("capabilities", []))
        self.plugin_id = manifest.get("plugin_id", "unknown_plugin")
        
    def _check_cap(self, cap: str):
        if cap not in self._capabilities:
            raise PermissionError(f"Plugin '{self.plugin_id}' lacks the '{cap}' capability required for this action.")

    def register_command(self, name: str, aliases: List[str] = None, category: str = "other", help_text: str = ""):
        """Register a new command to the MUD engine using a decorator."""
        self._check_cap("command_registration")
        from engine.commands.command_system import command
        
        def decorator(handler):
            decorated = command(
                name=name, 
                aliases=aliases, 
                category=category, 
                help_text=help_text, 
                plugin_id=self.plugin_id
            )(handler)
            return decorated
        return decorator

    def spawn_npc(self, npc_id: str, location_id: str):
        """Spawn an NPC into the world."""
        self._check_cap("world_modification")
        # In a real implementation this would safely interact with world/spawner
        if hasattr(self._game, "world") and hasattr(self._game.world, "spawn_npc"):
            return self._game.world.spawn_npc(npc_id, location_id)
        return None

    def broadcast_message(self, message: str):
        """Broadcast a server-wide message."""
        self._check_cap("server_broadcast")
        if hasattr(self._game, "headless_server"):
            self._game.headless_server.broadcast(message)

    def register_weather_provider(self, provider_id: str, provider: Any):
        """Register a custom weather provider implementation."""
        self._check_cap("system_provider_registration")
        if hasattr(self._game, "register_weather_provider"):
            self._game.register_weather_provider(provider_id, provider)

    def register_world_field_provider(self, provider_id: str, provider: Any):
        """Register a custom world-field provider implementation."""
        self._check_cap("system_provider_registration")
        if hasattr(self._game, "register_world_field_provider"):
            self._game.register_world_field_provider(provider_id, provider)

    def register_world_effects_provider(self, provider_id: str, provider: Any):
        """Register a custom world-effects provider implementation."""
        self._check_cap("system_provider_registration")
        if hasattr(self._game, "register_world_effects_provider"):
            self._game.register_world_effects_provider(provider_id, provider)

class PluginManager:
    """Handles discovery, capability validation, and failure-safe loading of mods."""
    def __init__(self, game_manager, mods_dir: str = "mods"):
        self.game = game_manager
        self.mods_dir = mods_dir
        self.plugins: Dict[str, Any] = {}
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.load_errors: Dict[str, str] = {}

    def load_all_plugins(self):
        if not os.path.exists(self.mods_dir):
            return
            
        for entry in os.listdir(self.mods_dir):
            plugin_path = os.path.join(self.mods_dir, entry)
            if os.path.isdir(plugin_path):
                self.load_plugin(plugin_path)

    def load_plugin(self, plugin_path: str):
        manifest_path = os.path.join(plugin_path, "manifest.json")
        if not os.path.exists(manifest_path):
            self.load_errors[plugin_path] = "Missing manifest.json"
            return
            
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except Exception as e:
            self.load_errors[plugin_path] = f"Invalid manifest.json: {e}"
            return
            
        plugin_id = manifest.get("plugin_id")
        if not plugin_id:
            self.load_errors[plugin_path] = "Manifest missing plugin_id"
            return

        manifest_errors = validate_plugin_manifest(manifest)
        if manifest_errors:
            self.load_errors[plugin_id] = "Manifest validation failed: " + "; ".join(manifest_errors)
            return
            
        main_script = os.path.join(plugin_path, "plugin.py")
        if not os.path.exists(main_script):
            self.load_errors[plugin_id] = "Missing plugin.py"
            return
            
        # Failure-safe import
        try:
            spec = importlib.util.spec_from_file_location(plugin_id, main_script)
            module = importlib.util.module_from_spec(spec)
            sys.modules[plugin_id] = module
            spec.loader.exec_module(module)
            
            if not hasattr(module, "setup"):
                self.load_errors[plugin_id] = "plugin.py missing 'setup(api)' function"
                return
                
            # Create restricted API context based on capabilities
            api = PluginAPI(self.game, manifest)
            
            # Execute setup
            module.setup(api)
            
            self.plugins[plugin_id] = module
            self.manifests[plugin_id] = manifest
            print(f"[PluginManager] Successfully loaded plugin: {plugin_id}")
            
        except Exception as e:
            error_trace = traceback.format_exc()
            self.load_errors[plugin_id] = f"Runtime error during load:\n{error_trace}"
            print(f"[PluginManager] Failed to load plugin '{plugin_id}': {e}")

    def unload_plugin(self, plugin_id: str):
        from engine.commands.command_system import unregister_plugin_commands
        if plugin_id in self.plugins:
            # Unregister any commands this plugin registered
            unregister_plugin_commands(plugin_id)
            
            # If the plugin has a teardown method, call it
            module = self.plugins[plugin_id]
            if hasattr(module, "teardown"):
                try:
                    module.teardown()
                except Exception as e:
                    print(f"[PluginManager] Error during teardown of '{plugin_id}': {e}")
            
            del self.plugins[plugin_id]
            del self.manifests[plugin_id]
            if plugin_id in sys.modules:
                del sys.modules[plugin_id]
            print(f"[PluginManager] Unloaded plugin: {plugin_id}")
