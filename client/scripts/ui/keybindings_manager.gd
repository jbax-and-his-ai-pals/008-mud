extends Node
class_name KeybindingsManager

## Keybindings manager — loads, stores, validates, and saves key remappings.
##
## Usage (from main_controller.gd):
##   keybindings_manager.load()
##   if keybindings_manager.is_key_for_action("mud_history_prev", event.keycode): ...
##   # In-game remap:
##   keybindings_manager.set_action_keys("mud_history_prev", PackedStringArray(["Home"]))
##   keybindings_manager.save()
##
## Runtime config path: user://keybindings.json
## Bundled default:     res://data/keybindings_default.json
##
## A binding entry shape (JSON / GDScript dict):
##   { "keys": ["Up"], "description": "..." }
##
## Recognised key name strings (see KEY_NAME_MAP below):
##   Up Down Left Right PageUp PageDown Home End Tab Escape Enter Space
##   F1..F12

const RUNTIME_CONFIG_PATH := "user://keybindings.json"
const DEFAULT_CONFIG_PATH := "res://data/keybindings_default.json"
const CONFIG_VERSION := 1

# Canonical action names.  Every entry here must appear in keybindings_default.json.
const ACTIONS: PackedStringArray = [
	"mud_history_prev",
	"mud_history_next",
	"mud_scroll_up",
	"mud_scroll_down",
	"mud_focus_input",
]

# Mapping from human-readable key name → Godot Key enum value.
const KEY_NAME_MAP: Dictionary = {
	"Up": KEY_UP,
	"Down": KEY_DOWN,
	"Left": KEY_LEFT,
	"Right": KEY_RIGHT,
	"PageUp": KEY_PAGEUP,
	"PageDown": KEY_PAGEDOWN,
	"Home": KEY_HOME,
	"End": KEY_END,
	"Tab": KEY_TAB,
	"Escape": KEY_ESCAPE,
	"Enter": KEY_ENTER,
	"Space": KEY_SPACE,
	"F1": KEY_F1,  "F2": KEY_F2,  "F3": KEY_F3,  "F4": KEY_F4,
	"F5": KEY_F5,  "F6": KEY_F6,  "F7": KEY_F7,  "F8": KEY_F8,
	"F9": KEY_F9,  "F10": KEY_F10, "F11": KEY_F11, "F12": KEY_F12,
}

# Reverse map: Key enum value → key name string (for display).
var _key_name_reverse: Dictionary = {}

# Live bindings: action_name → { "keys": [...key_names], "description": "..." }
var _bindings: Dictionary = {}

# True once load() has been called.
var _loaded: bool = false


func _ready() -> void:
	# Build reverse map once.
	for name: Variant in KEY_NAME_MAP.keys():
		_key_name_reverse[KEY_NAME_MAP[name]] = str(name)


# ── Public API ────────────────────────────────────────────────────────────────

func load() -> void:
	"""Load from user://keybindings.json, fall back to bundled default, then to code defaults."""
	var raw: Dictionary = _load_json(RUNTIME_CONFIG_PATH)
	if raw.is_empty():
		raw = _load_json(DEFAULT_CONFIG_PATH)
	_apply_config(raw)
	_loaded = true


func save() -> void:
	"""Persist current bindings to user://keybindings.json."""
	var out: Dictionary = {"version": CONFIG_VERSION, "bindings": _bindings.duplicate(true)}
	var file := FileAccess.open(RUNTIME_CONFIG_PATH, FileAccess.WRITE)
	if file == null:
		push_warning("KeybindingsManager: cannot write %s (err %d)" % [
			RUNTIME_CONFIG_PATH, FileAccess.get_open_error()
		])
		return
	file.store_string(JSON.stringify(out, "\t"))
	file.close()


func reset() -> void:
	"""Reset all bindings to the bundled defaults and save."""
	_bindings.clear()
	var raw: Dictionary = _load_json(DEFAULT_CONFIG_PATH)
	_apply_config(raw)
	save()


func reset_action(action: String) -> bool:
	"""Reset a single action to its bundled default.  Returns false if action unknown."""
	if action not in ACTIONS:
		return false
	var raw: Dictionary = _load_json(DEFAULT_CONFIG_PATH)
	var defaults: Dictionary = raw.get("bindings", {}) as Dictionary
	if defaults.has(action):
		_bindings[action] = (defaults[action] as Dictionary).duplicate(true)
	save()
	return true


func get_all_actions() -> PackedStringArray:
	return ACTIONS.duplicate()


func get_keys_for_action(action: String) -> PackedStringArray:
	"""Return the list of key-name strings bound to this action."""
	if not _bindings.has(action):
		return PackedStringArray()
	var entry: Dictionary = _bindings[action] as Dictionary
	var keys_variant: Variant = entry.get("keys", [])
	if typeof(keys_variant) != TYPE_ARRAY:
		return PackedStringArray()
	var result: PackedStringArray = []
	for v: Variant in (keys_variant as Array):
		result.append(str(v))
	return result


func set_action_keys(action: String, key_names: PackedStringArray) -> bool:
	"""Remap an action.  Returns false if action or any key name is unrecognised."""
	if action not in ACTIONS:
		return false
	for kname: String in key_names:
		if not KEY_NAME_MAP.has(kname):
			return false
	if not _bindings.has(action):
		_bindings[action] = {"keys": [], "description": ""}
	(_bindings[action] as Dictionary)["keys"] = Array(key_names)
	return true


func get_description(action: String) -> String:
	if not _bindings.has(action):
		return ""
	return str((_bindings[action] as Dictionary).get("description", ""))


func is_key_for_action(action: String, keycode: Key) -> bool:
	"""Return true if keycode matches any key bound to action."""
	for kname: String in get_keys_for_action(action):
		if KEY_NAME_MAP.has(kname) and int(KEY_NAME_MAP[kname]) == int(keycode):
			return true
	return false


func get_summary_lines() -> PackedStringArray:
	"""Return human-readable lines suitable for the in-game keybind list command."""
	var lines: PackedStringArray = []
	for action: String in ACTIONS:
		var keys := get_keys_for_action(action)
		var desc := get_description(action)
		var key_str: String = ", ".join(keys) if not keys.is_empty() else "(unbound)"
		lines.append("  %s  →  %s   [%s]" % [action, key_str, desc])
	return lines


func keycode_to_name(keycode: Key) -> String:
	"""Convert a Key enum value to a display name, or the hex code if unmapped."""
	if _key_name_reverse.has(int(keycode)):
		return str(_key_name_reverse[int(keycode)])
	return "0x%X" % int(keycode)


# ── Internal ──────────────────────────────────────────────────────────────────

func _load_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return {}
	var raw := file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return {}
	return parsed as Dictionary


func _apply_config(raw: Dictionary) -> void:
	"""Merge a parsed config dict into _bindings, filling missing actions with code fallbacks."""
	var bindings_dict: Dictionary = raw.get("bindings", {}) as Dictionary

	# Process each known action from the file.
	for action: Variant in bindings_dict.keys():
		var action_str: String = str(action)
		if action_str not in ACTIONS:
			continue
		var entry_variant: Variant = bindings_dict[action]
		if typeof(entry_variant) != TYPE_DICTIONARY:
			continue
		var entry: Dictionary = entry_variant as Dictionary
		# Validate every key name; discard the entry if any is unrecognised.
		var keys_variant: Variant = entry.get("keys", [])
		if typeof(keys_variant) != TYPE_ARRAY:
			continue
		var valid := true
		for kname_variant: Variant in (keys_variant as Array):
			if not KEY_NAME_MAP.has(str(kname_variant)):
				valid = false
				break
		if valid:
			_bindings[action_str] = entry.duplicate(true)

	# Ensure every known action has a fallback entry so is_key_for_action() never crashes.
	for action: String in ACTIONS:
		if not _bindings.has(action):
			_bindings[action] = {"keys": [], "description": ""}
