# scripts/ui/modals/FeatureProfileDialog.gd
#
# The feature profile the set's manifest selects (`paths.feature_profile`):
# which systems a server runs (feature_profile.py's modes, and a plugin
# provider for a "custom" one) and the party, shard and finite-adventure
# policies (headless/party.py, shard.py, finite_adventure.py). Saved through
# the staged engine check (content_set.py::_validate_feature_profile).
#
# "(default)" means the key is absent and the server's own default applies.
# Only what the author changed is written; keys this dialog does not show are
# carried through, so the engine check names them rather than the editor
# dropping them unseen.

class_name FeatureProfileDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")
const DEFAULT := "__default__"

# feature_profile.py allowed_modes(), PROVIDER_CATEGORIES and PROFILE_POLICIES;
# schema_parity_smoke.gd checks all three against the engine. Modes list the
# default first.
const MODES := {
	"world": ["", "co_op_party", "finite_adventure", "persistent_shard", "readonly_archive", "single_player_story"],
	"combat": ["enabled", "disabled"],
	"weather": ["builtin", "custom", "disabled"],
	"world_effects": ["enabled", "custom", "disabled"],
	"authoring": ["all", "disabled", "gm_only"],
	"world_mutation": ["mutable", "readonly"],
	"mods": ["enabled", "disabled"],
	"permadeath": ["disabled", "enabled"],
}
const PROVIDER_CATEGORIES := ["weather", "world_effects"]
const POLICIES := {
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
# The readers' own defaults for the typed keys (the lists' defaults are first).
const TYPED_DEFAULTS := {"offline_invites_supported": "yes", "replay_supported": "yes", "disconnect_timeout_seconds": "300"}
const SECTION_TITLES := {"party": "Parties", "persistent_shard": "Persistent Shard", "finite_adventure": "Finite Adventure"}

signal feature_profile_saved
var path := ""
var disk_hash := ""
var original: Dictionary = {}
var mode_pickers: Dictionary = {}
var provider_fields: Dictionary = {}
var policy_controls: Dictionary = {}
var status: Label
var body: VBoxContainer
var loading := false
# The loaded profile, or null (EditorUIManager asks every dialog for its draft).
var draft = null


func setup():
	_install_guard()
	title = "Feature Profile"
	min_size = Vector2i(760, 640)
	ok_button_text = "Save Feature Profile"
	confirmed.connect(_save)
	var root := VBoxContainer.new(); root.custom_minimum_size = Vector2(720, 560); root.add_theme_constant_override("separation", 8); add_child(root)
	status = Label.new(); status.name = "Status"; status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status.modulate = InspectorStyle.COLOR_TEXT_DIM; root.add_child(status)
	var scroll := ScrollContainer.new(); scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL; root.add_child(scroll)
	body = VBoxContainer.new(); body.size_flags_horizontal = Control.SIZE_EXPAND_FILL; body.add_theme_constant_override("separation", 6); scroll.add_child(body)

	body.add_child(InspectorStyle.create_sub_header("Systems"))
	var hint := InspectorStyle.lbl("Which systems a server running this set turns on. \"(default)\" leaves the key out, and the server's default applies.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; body.add_child(hint)
	var grid := GridContainer.new(); grid.columns = 2; grid.add_theme_constant_override("h_separation", 12); body.add_child(grid)
	for category in MODES:
		grid.add_child(InspectorStyle.lbl(category.replace("_", " ").capitalize(), InspectorStyle.COLOR_TEXT_DIM))
		var picker := OptionButton.new(); picker.name = "Mode_" + category; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		InspectorStyle.apply_button_style(picker); grid.add_child(picker); mode_pickers[category] = picker
		picker.item_selected.connect(func(_i): _refresh_providers(); _mark_dirty())
		if category in PROVIDER_CATEGORIES:
			grid.add_child(InspectorStyle.lbl("   provider id", InspectorStyle.COLOR_TEXT_DIM))
			var field := LineEdit.new(); field.name = "Provider_" + category; field.placeholder_text = "plugin provider id (custom mode only)"
			InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _mark_dirty()); grid.add_child(field); provider_fields[category] = field

	for section in POLICIES:
		body.add_child(InspectorStyle.create_sub_header(SECTION_TITLES[section]))
		var section_grid := GridContainer.new(); section_grid.columns = 2; section_grid.add_theme_constant_override("h_separation", 12); body.add_child(section_grid)
		for key in POLICIES[section]:
			section_grid.add_child(InspectorStyle.lbl(key.replace("_", " ").capitalize(), InspectorStyle.COLOR_TEXT_DIM))
			var kind = POLICIES[section][key]
			var control: Control
			if kind is Array or kind == "bool" or kind == "campaign":
				var picker := OptionButton.new(); picker.item_selected.connect(func(_i): _mark_dirty()); InspectorStyle.apply_button_style(picker); control = picker
			else:
				var field := LineEdit.new(); field.text_changed.connect(func(_t): _mark_dirty()); InspectorStyle.apply_input_style(field); control = field
				field.placeholder_text = "(default: %s)" % TYPED_DEFAULTS.get(key, "none")
			control.name = "Policy_%s_%s" % [section, key]; control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			section_grid.add_child(control); policy_controls["%s.%s" % [section, key]] = control
	DialogStyle.style_window(self); get_ok_button().custom_minimum_size = Vector2(300, 40); get_ok_button().disabled = true


func open_active():
	if visible: return
	_form_baseline.clear()
	draft = null
	path = _profile_path()
	if path == "" or not FileAccess.file_exists(path):
		original = {}; disk_hash = ""
		body.visible = false
		status.text = "This set's manifest selects no feature profile, so a server runs it with every default." if path == "" else "The manifest names %s, which does not exist." % path
		status.modulate = DialogStyle.COLOR_DANGER if path != "" else InspectorStyle.COLOR_TEXT_DIM
		get_ok_button().disabled = true; popup_centered(); return
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not parsed is Dictionary:
		body.visible = false; status.text = "%s is not a JSON object; fix it by hand first." % path.get_file(); status.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	original = parsed.duplicate(true); draft = original; disk_hash = FileAccess.get_sha256(path); body.visible = true; loading = true
	for category in MODES:
		var node = original.get(category, {})
		_fill_choice(mode_pickers[category], MODES[category], node.get("mode", null) if node is Dictionary else null, _mode_label(category, MODES[category][0]))
		if provider_fields.has(category): provider_fields[category].text = str(node.get("provider_id", "")) if node is Dictionary else ""
	var campaigns := _campaign_ids()
	for control_key in policy_controls:
		var section := str(control_key).get_slice(".", 0); var key := str(control_key).get_slice(".", 1)
		var node = original.get(_node_name(section), {})
		var value = node.get(key, null) if node is Dictionary else null
		var kind = POLICIES[section][key]; var control: Control = policy_controls[control_key]
		if kind is Array: _fill_choice(control, kind, value, "(default: %s)" % kind[0])
		elif kind == "bool": _fill_choice(control, [true, false], value, "(default: %s)" % TYPED_DEFAULTS[key])
		elif kind == "campaign": _fill_choice(control, campaigns, value, "(default: the set's only campaign, if it has one)")
		else: (control as LineEdit).text = "" if value == null else str(value)
	_refresh_providers()
	_reset_form_baseline()
	loading = false; get_ok_button().disabled = true
	status.text = "Editing %s, the profile this set's manifest selects." % path.get_file(); status.modulate = InspectorStyle.COLOR_TEXT_DIM
	popup_centered()


# The profile as it should be written: the file's own content, with each
# control's key set, or removed for "(default)"; sections left empty that the
# file did not have are not added.
func compose() -> Dictionary:
	var data: Dictionary = original.duplicate(true)
	for category in MODES:
		var picked = _picked(mode_pickers[category])
		_set_key(data, category, "mode", picked)
		if provider_fields.has(category):
			var provider := (provider_fields[category] as LineEdit).text.strip_edges()
			_set_key(data, category, "provider_id", provider if picked is String and picked == "custom" and provider != "" else DEFAULT)
	for control_key in policy_controls:
		var section := str(control_key).get_slice(".", 0); var key := str(control_key).get_slice(".", 1)
		var kind = POLICIES[section][key]; var control: Control = policy_controls[control_key]
		var value = DEFAULT
		if control is OptionButton: value = _picked(control)
		else:
			var text := (control as LineEdit).text.strip_edges()
			if text != "": value = float(text) if kind == "seconds" and text.is_valid_float() else text
			if kind == "seconds" and value is float and value == floor(value): value = int(value)
		_set_key(data, _node_name(section), key, value)
	return data


func _save():
	if path == "" or not body.visible: return
	if not _form_changed(): _finish_save(); return
	var errors: Array = []
	for control_key in policy_controls:
		var control = policy_controls[control_key]
		if control is LineEdit and POLICIES[str(control_key).get_slice(".", 0)][str(control_key).get_slice(".", 1)] == "seconds":
			var text: String = control.text.strip_edges()
			if text != "" and (not text.is_valid_float() or float(text) < 0): errors.append("%s must be a number of seconds, 0 or more." % control_key)
	if not errors.is_empty(): status.text = "\n".join(errors); status.modulate = DialogStyle.COLOR_DANGER; return
	var data := compose()
	var result: Dictionary = ConfigurationSave.write(path, data, disk_hash)
	if not result.get("ok", false): status.text = str(result.get("error", "Could not save the feature profile.")); status.modulate = DialogStyle.COLOR_DANGER; return
	original = data.duplicate(true); draft = original; disk_hash = FileAccess.get_sha256(path)
	get_ok_button().disabled = true; feature_profile_saved.emit()
	_finish_save()


func _set_key(data: Dictionary, category: String, key: String, value) -> void:
	var had_section: bool = original.has(category)
	var node = data.get(category, {})
	if not node is Dictionary: return  # malformed in the file: left for the engine check to name
	if value is String and value == DEFAULT: node.erase(key)
	else: node[key] = value
	if node.is_empty() and not had_section: data.erase(category)
	else: data[category] = node


# `shard` is read as another name for `persistent_shard`; a file that uses it
# keeps it.
func _node_name(section: String) -> String:
	if section == "persistent_shard" and original.has("shard") and not original.has("persistent_shard"): return "shard"
	return section


func _fill_choice(picker: OptionButton, values: Array, current, default_label: String) -> void:
	picker.clear()
	picker.add_item(default_label); picker.set_item_metadata(0, DEFAULT)
	var selected := 0
	for value in values:
		var label := str(value).capitalize().replace("_", " ") if value is String else ("Yes" if value else "No")
		if value is String and value == "": continue
		picker.add_item(label); picker.set_item_metadata(picker.item_count - 1, value)
		if current != null and typeof(current) == typeof(value) and (str(current).strip_edges().to_lower() == str(value) if value is String else current == value): selected = picker.item_count - 1
	# A value the list does not know (a synonym, or a mistake) stays visible and
	# is written back unchanged unless the author picks something else.
	# An authored "" is the world mode's own default.
	if current is String and current.strip_edges() == "" and values.has(""): current = null
	if current != null and selected == 0:
		picker.add_item("Current: %s" % str(current)); picker.set_item_metadata(picker.item_count - 1, current); selected = picker.item_count - 1
	picker.select(selected)


func _picked(picker: OptionButton):
	return picker.get_item_metadata(picker.selected) if picker.selected >= 0 else DEFAULT


func _mode_label(category: String, default_mode: String) -> String:
	if category == "world": return "(default: decided by the other modes)"
	return "(default: %s)" % default_mode


func _refresh_providers() -> void:
	for category in provider_fields:
		var picked = _picked(mode_pickers[category])
		(provider_fields[category] as LineEdit).editable = picked is String and picked == "custom"


func _profile_path() -> String:
	var manifest_path := DataRoot.root().path_join("content_set.manifest.json")
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(manifest_path)) if FileAccess.file_exists(manifest_path) else null
	var declared = manifest.get("paths", {}).get("feature_profile", "") if manifest is Dictionary and manifest.get("paths") is Dictionary else ""
	return DataRoot.root().path_join(str(declared)).simplify_path() if str(declared).strip_edges() != "" else ""


func _campaign_ids() -> Array:
	var out: Array = []
	var directory := DataRoot.root().path_join("data/campaigns")
	if not DirAccess.dir_exists_absolute(directory): return out
	for file_name in DirAccess.get_files_at(directory):
		if not file_name.ends_with(".json"): continue
		var parsed = JSON.parse_string(FileAccess.get_file_as_string(directory.path_join(file_name)))
		if parsed is Dictionary: out.append(str(parsed.get("campaign_id", file_name.get_basename())))
	out.sort()
	return out


func _mark_dirty():
	if loading: return
	var dirty := _form_changed(); get_ok_button().disabled = not dirty
	status.text = "Unsaved feature profile changes." if dirty else "No unsaved changes."; status.modulate = Color("f2cf74")
