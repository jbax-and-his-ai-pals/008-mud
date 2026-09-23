# scripts/ui/modals/PresentationDialog.gd
#
# The content set's presentation file (the manifest's `paths.presentation`).
# Its `theme_pack` is live: the server sends it to the client in `hello`, and
# the client applies the pack of that id if it ships one. The picker therefore
# offers this repository's client packs (`client/themes/*.json` by theme_id).
# `display_name`, `presentation_id` and the accessibility flags are validated
# (`content_set.py::_validate_presentation`) but no runtime reads them yet.
# Saves go through ConfigurationSave, so the engine refuses a bad file first;
# only changed fields are written.

class_name PresentationDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

const ConfigurationSave = preload("res://scripts/data/ConfigurationSave.gd")
const FLAGS := [
	["alt_text_required", "Alt text required"],
	["high_contrast_supported", "High contrast supported"],
	["reduced_motion_supported", "Reduced motion supported"],
]

var draft = null
var path := ""
var disk_hash := ""
var original: Dictionary = {}
var status: Label
var display_name: LineEdit
var presentation_id: LineEdit
var theme_pack: OptionButton
var flag_checks: Dictionary = {}
var loading := false


func setup():
	_install_guard()
	title = "Presentation"
	min_size = Vector2i(560, 380)
	ok_button_text = "Save Presentation"
	confirmed.connect(_save)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(520, 0); box.add_theme_constant_override("separation", 8); add_child(box)
	status = Label.new(); status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(status)
	var pack_row := HBoxContainer.new(); box.add_child(pack_row)
	pack_row.add_child(InspectorStyle.lbl("Client theme pack", InspectorStyle.COLOR_TEXT_DIM))
	theme_pack = OptionButton.new(); theme_pack.name = "ThemePack"; theme_pack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_button_style(theme_pack); theme_pack.item_selected.connect(func(index): theme_pack.select(index); _mark_dirty())
	pack_row.add_child(theme_pack)
	var hint := InspectorStyle.lbl("Sent to the client when a player connects; a client without that pack keeps its current theme. A player's own 'theme use' choice is never overridden.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	display_name = _field(box, "Display name (not yet read by the client)")
	presentation_id = _field(box, "Presentation id (not yet read)")
	box.add_child(InspectorStyle.lbl("Accessibility declarations (not yet read)", InspectorStyle.COLOR_TEXT_DIM))
	for spec in FLAGS:
		var check := CheckBox.new(); check.name = str(spec[0]).to_pascal_case(); check.text = spec[1]
		check.toggled.connect(func(_v): _mark_dirty()); box.add_child(check)
		flag_checks[spec[0]] = check
	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(260, 40)
	get_ok_button().disabled = true


static func presentation_path() -> String:
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(DataRoot.root().path_join("content_set.manifest.json")))
	var relative := "presentation/default.json"
	if manifest is Dictionary and manifest.get("paths") is Dictionary and manifest["paths"].get("presentation") is String:
		relative = manifest["paths"]["presentation"]
	return DataRoot.root().path_join(relative).simplify_path()


## `theme_id`s of the client packs this repository ships.
static func client_theme_ids() -> Array:
	var dir := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir().path_join("client/themes")
	var ids: Array = []
	for file_name in DirAccess.get_files_at(dir):
		if not file_name.ends_with(".json"): continue
		var pack = JSON.parse_string(FileAccess.get_file_as_string(dir.path_join(file_name)))
		if pack is Dictionary and str(pack.get("theme_id", "")) != "": ids.append(str(pack["theme_id"]))
	ids.sort()
	return ids


func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	path = presentation_path()
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path)) if FileAccess.file_exists(path) else null
	if not (parsed is Dictionary):
		status.text = "No readable presentation file at %s." % path; status.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	original = parsed
	draft = parsed.duplicate(true)
	disk_hash = FileAccess.get_sha256(path)
	loading = true
	QuestGenerationSection._fill_picker(theme_pack, client_theme_ids(), {}, str(original.get("theme_pack", "")), "Client default")
	display_name.text = str(original.get("display_name", ""))
	presentation_id.text = str(original.get("presentation_id", ""))
	var accessibility: Dictionary = original.get("accessibility", {}) if original.get("accessibility") is Dictionary else {}
	for key in flag_checks: flag_checks[key].button_pressed = accessibility.get(key) == true
	_reset_form_baseline()
	loading = false
	get_ok_button().disabled = true
	status.text = "Editing %s." % path; status.modulate = InspectorStyle.COLOR_TEXT_DIM
	popup_centered()


func compose() -> Dictionary:
	var out: Dictionary = original.duplicate(true)
	if _field_changed(theme_pack):
		var pack := QuestGenerationSection._picked(theme_pack)
		if pack == "": out.erase("theme_pack")
		else: out["theme_pack"] = pack
	for pair in [[display_name, "display_name"], [presentation_id, "presentation_id"]]:
		if _field_changed(pair[0]):
			var text: String = pair[0].text.strip_edges()
			if text == "": out.erase(pair[1])
			else: out[pair[1]] = text
	for key in flag_checks:
		if _field_changed(flag_checks[key]):
			var accessibility: Dictionary = out.get("accessibility", {}) if out.get("accessibility") is Dictionary else {}
			accessibility[key] = flag_checks[key].button_pressed
			out["accessibility"] = accessibility
	return out


func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	var result := ConfigurationSave.write(path, compose(), disk_hash)
	if not result.get("ok", false):
		status.text = str(result.get("error", "Could not save the presentation file.")); status.modulate = DialogStyle.COLOR_DANGER; return
	get_ok_button().disabled = true
	_finish_save()


func _field(parent: VBoxContainer, label: String) -> LineEdit:
	var row := VBoxContainer.new(); parent.add_child(row)
	row.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_t): _mark_dirty()); row.add_child(field)
	return field


func _mark_dirty():
	if loading or draft == null: return
	var dirty := _form_changed()
	get_ok_button().disabled = not dirty
	status.text = "Unsaved presentation changes." if dirty else "No unsaved changes."; status.modulate = Color("f2cf74")
