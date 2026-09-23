# scripts/ui/modals/ManifestEditorDialog.gd
#
# The content set's identity, start and capabilities, editable after creation.
#
# Before this, the manifest was written once by the scaffold and never again: an
# author who wanted a different start room, or to turn a system on, edited JSON by
# hand or copied the set. The fields it does *not* offer are as deliberate as the
# ones it does -- the id is the directory name and the identity saves are
# partitioned by, and paths are refused by `configuration_save.py` rather than
# half-supported here.
class_name ManifestEditorDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal manifest_saved
signal request_edit_opening
signal request_edit_presentation

const DraftScript = preload("res://scripts/data/ManifestDraft.gd")
const Scaffold = preload("res://scripts/data/ContentSetScaffold.gd")

var draft
var status_label: Label
var identity_label: Label
var paths_label: Label
var title_field: LineEdit
var scenario_field: LineEdit
var region_field: LineEdit
var room_field: LineEdit
var capability_checks: Dictionary = {}
var capability_plan_label: Label
var linked_ruleset_path := ""
var linked_ruleset_original: Dictionary = {}
var linked_ruleset_hash := ""
var form_dirty := false
var loading := false

func setup():
	_install_guard()
	title = "Content Set Manifest"
	min_size = Vector2i(780, 640)
	ok_button_text = "Save Manifest"
	confirmed.connect(_save)
	var scroll := ScrollContainer.new(); scroll.custom_minimum_size = Vector2(750, 520); add_child(scroll)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(720, 0); box.add_theme_constant_override("separation", 10); scroll.add_child(box)
	status_label = Label.new(); status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(status_label)
	box.add_child(InspectorStyle.create_sub_header("Identity (fixed)"))
	identity_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); identity_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(identity_label)
	paths_label = InspectorStyle.lbl("", InspectorStyle.COLOR_TEXT_DIM); paths_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(paths_label)
	var edit_opening := Button.new(); edit_opening.text = "Edit Opening & First Session..."; edit_opening.tooltip_text = "Edit the opening heading, introduction, and suggested first actions."; InspectorStyle.apply_button_style(edit_opening); edit_opening.pressed.connect(func(): request_edit_opening.emit()); box.add_child(edit_opening)
	var edit_presentation := Button.new(); edit_presentation.text = "Edit Presentation..."; edit_presentation.tooltip_text = "Choose the client theme pack players see when they connect."; InspectorStyle.apply_button_style(edit_presentation); edit_presentation.pressed.connect(func(): request_edit_presentation.emit()); box.add_child(edit_presentation)
	box.add_child(InspectorStyle.create_sub_header("Title"))
	title_field = _field(box, "Title")
	box.add_child(InspectorStyle.create_sub_header("Where a character starts"))
	var start_hint := InspectorStyle.lbl("The region and room must exist in this set. The engine refuses a start it cannot place.", InspectorStyle.COLOR_TEXT_DIM)
	start_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(start_hint)
	scenario_field = _field(box, "Scenario id (the opening file's scenario_id)")
	region_field = _field(box, "Region id")
	room_field = _field(box, "Room id")
	box.add_child(InspectorStyle.create_sub_header("Capabilities"))
	var capability_hint := InspectorStyle.lbl("A capability must agree with the ruleset's `systems` section: the engine refuses a contradiction, and the report says which one.", InspectorStyle.COLOR_TEXT_DIM)
	capability_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(capability_hint)
	capability_plan_label = InspectorStyle.lbl("Capability changes update matching explicit ruleset system declarations in the same validated save. Related content stays saved and inactive; it is never deleted.", InspectorStyle.COLOR_TEXT_DIM)
	capability_plan_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(capability_plan_label)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	for capability in Scaffold.CAPABILITIES:
		var toggle := CheckBox.new(); toggle.text = str(capability); toggle.toggled.connect(func(_value): _refresh_capability_plan(); _mark_dirty()); grid.add_child(toggle)
		capability_checks[str(capability)] = toggle
	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(280, 40)
	get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	draft = DraftScript.new()
	var result: Dictionary = draft.open(DataRoot.root().path_join(Scaffold.MANIFEST_FILENAME))
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not load the manifest.")); status_label.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	loading = true
	identity_label.text = "id: %s\nversion: %s   manifest schema: %s   engine API: %s - %s" % [
		str(draft.data.get("id", "")), str(draft.data.get("version", "")),
		str(draft.data.get("manifest_schema_version", "")),
		str(draft.data.get("engine_api_min", "")), str(draft.data.get("engine_api_max", "")),
	]
	var paths: Dictionary = draft.data.get("paths", {}) if draft.data.get("paths") is Dictionary else {}
	var lines: Array = []
	for key in paths:
		lines.append("%s: %s" % [key, str(paths[key])])
	paths_label.text = "Paths (not editable here): " + ("; ".join(lines) if not lines.is_empty() else "none declared")
	title_field.text = draft.title_value()
	scenario_field.text = draft.start_field("scenario_id")
	region_field.text = draft.start_field("region_id")
	room_field.text = draft.start_field("room_id")
	var declared: Array = draft.capabilities()
	for capability in capability_checks:
		capability_checks[capability].button_pressed = declared.has(capability)
	var linked := _load_linked_ruleset()
	if not linked.get("ok", false):
		status_label.text = str(linked.get("error", "Could not load the linked ruleset.")); status_label.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; loading = false; popup_centered(); return
	_reset_form_baseline()
	loading = false; form_dirty = false; get_ok_button().disabled = true
	status_label.text = "Editing %s. Changing a capability needs the game reloaded before it takes effect." % DataRoot.root().path_join(Scaffold.MANIFEST_FILENAME)
	status_label.modulate = InspectorStyle.COLOR_TEXT_DIM
	_refresh_capability_plan()
	popup_centered()

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	if _field_changed(title_field): draft.set_title(title_field.text)
	draft.set_start(scenario_field.text, region_field.text, room_field.text)
	var chosen: Array = []
	for capability in capability_checks:
		if capability_checks[capability].button_pressed: chosen.append(capability)
	draft.set_capabilities(chosen)
	var result: Dictionary
	var capabilities_changed := _capabilities_changed()
	var reconciled: Dictionary = {}
	if capabilities_changed:
		reconciled = _reconciled_ruleset(draft.capabilities())
		result = draft.save_with_ruleset(linked_ruleset_path, reconciled, linked_ruleset_hash)
	else:
		result = draft.save()
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not save the manifest.")); status_label.modulate = DialogStyle.COLOR_DANGER; return
	if capabilities_changed:
		linked_ruleset_original = reconciled
		linked_ruleset_hash = FileAccess.get_sha256(linked_ruleset_path)
	form_dirty = false; get_ok_button().disabled = true
	manifest_saved.emit()
	_finish_save()

func _field(parent: VBoxContainer, label_text: String) -> LineEdit:
	var row := VBoxContainer.new(); row.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(field)
	parent.add_child(row); return field

func _mark_dirty():
	if loading or draft == null: return
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved manifest changes." if form_dirty else "No unsaved changes."
	status_label.modulate = Color("f2cf74") if form_dirty else InspectorStyle.COLOR_TEXT_DIM


func _load_linked_ruleset() -> Dictionary:
	linked_ruleset_path = DataRoot.ruleset_path()
	if not FileAccess.file_exists(linked_ruleset_path):
		return {"ok": false, "error": "The manifest names a content set without a ruleset at %s." % linked_ruleset_path}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(linked_ruleset_path))
	if not parsed is Dictionary:
		return {"ok": false, "error": "The linked ruleset is not a JSON object; capability changes cannot safely reconcile it."}
	linked_ruleset_original = parsed.duplicate(true)
	linked_ruleset_hash = FileAccess.get_sha256(linked_ruleset_path)
	return {"ok": true}


func _capabilities_changed() -> bool:
	if draft == null: return false
	var baseline := {}
	for entry in draft.original.get("capabilities", []): baseline[str(entry)] = true
	for capability in capability_checks:
		if bool(capability_checks[capability].button_pressed) != baseline.has(capability): return true
	return false


func _reconciled_ruleset(chosen_capabilities: Array) -> Dictionary:
	var reconciled := linked_ruleset_original.duplicate(true)
	var systems: Dictionary = reconciled.get("systems", {}) if reconciled.get("systems") is Dictionary else {}
	reconciled["systems"] = systems
	var before := {}
	for entry in draft.original.get("capabilities", []): before[str(entry)] = true
	var after := {}
	for entry in chosen_capabilities: after[str(entry)] = true
	for capability in Scaffold.CAPABILITIES:
		if before.has(capability) == after.has(capability): continue
		var system: Dictionary = systems.get(capability, {}) if systems.get(capability) is Dictionary else {}
		system["enabled"] = after.has(capability)
		systems[capability] = system
	return reconciled


func _refresh_capability_plan():
	if capability_plan_label == null or draft == null: return
	var baseline := {}
	for entry in draft.original.get("capabilities", []): baseline[str(entry)] = true
	var changes: Array = []
	for capability in Scaffold.CAPABILITIES:
		if not capability_checks.has(capability): continue
		var enabled := bool(capability_checks[capability].button_pressed)
		if enabled == baseline.has(capability): continue
		changes.append(("Enable " if enabled else "Disable ") + str(capability))
	if changes.is_empty():
		capability_plan_label.text = "No capability changes planned. Matching explicit ruleset system declarations stay untouched."
		capability_plan_label.modulate = InspectorStyle.COLOR_TEXT_DIM
	else:
		capability_plan_label.text = "%s. This saves the manifest and matching ruleset system declaration together; existing related content remains inactive, never deleted." % "; ".join(changes)
		capability_plan_label.modulate = Color("f2cf74")
