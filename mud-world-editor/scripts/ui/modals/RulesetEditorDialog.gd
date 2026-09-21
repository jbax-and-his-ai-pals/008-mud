class_name RulesetEditorDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal ruleset_saved

var draft: RulesetDraft
var status_label: Label
var ruleset_id: LineEdit
var world_mode: LineEdit
var progression_model: LineEdit
var stats: LineEdit
var biomes: LineEdit
var region_types: LineEdit
var require_classification: CheckBox
var require_level_bands: CheckBox
var require_hazard_coverage: CheckBox
var system_checks: Dictionary = {}
var faction_rows: VBoxContainer
var form_dirty := false
var loading := false
var faction_baseline: Array = []

const SYSTEM_LABELS := {
	"combat": "Combat", "abilities": "Abilities", "magic": "Magic", "crafting": "Crafting",
	"gathering": "Gathering", "economy": "Economy", "quests": "Quests", "social": "Social",
}

func setup():
	_install_guard()
	title = "Ruleset Editor"
	min_size = Vector2i(800, 620)
	ok_button_text = "Save Ruleset"
	confirmed.connect(_save)
	var scroll := ScrollContainer.new(); scroll.custom_minimum_size = Vector2(770, 530); add_child(scroll)
	var box := VBoxContainer.new(); box.custom_minimum_size = Vector2(740, 0); box.add_theme_constant_override("separation", 12); scroll.add_child(box)
	status_label = Label.new(); status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM; box.add_child(status_label)
	box.add_child(InspectorStyle.create_sub_header("General"))
	ruleset_id = _field(box, "Ruleset ID")
	world_mode = _field(box, "World Mode")
	progression_model = _field(box, "Progression Model")
	box.add_child(InspectorStyle.create_sub_header("Enabled Systems"))
	var systems_grid := GridContainer.new(); systems_grid.columns = 2; box.add_child(systems_grid)
	for system_id in SYSTEM_LABELS:
		var toggle := CheckBox.new(); toggle.text = str(SYSTEM_LABELS[system_id]); toggle.toggled.connect(func(_value): _mark_dirty()); systems_grid.add_child(toggle); system_checks[system_id] = toggle
	box.add_child(InspectorStyle.create_sub_header("Custom Factions"))
	var faction_hint := InspectorStyle.lbl("Built-in factions remain engine-owned. Add only this set's custom factions.", InspectorStyle.COLOR_TEXT_DIM); box.add_child(faction_hint)
	faction_rows = VBoxContainer.new(); faction_rows.add_theme_constant_override("separation", 5); box.add_child(faction_rows)
	var add_faction := Button.new(); add_faction.text = "+ Add Custom Faction"; InspectorStyle.apply_button_style(add_faction, InspectorStyle.COLOR_SUCCESS); add_faction.pressed.connect(func(): _add_faction_row("", "neutral"); _mark_dirty()); box.add_child(add_faction)
	box.add_child(InspectorStyle.create_sub_header("Declared Stats"))
	stats = _field(box, "Stats (comma-separated)")
	stats.tooltip_text = "The active stat vocabulary for this ruleset. Existing unknown sections remain untouched."
	box.add_child(InspectorStyle.create_sub_header("Region Policy"))
	require_classification = _check(box, "Require region classification")
	require_level_bands = _check(box, "Require level bands")
	require_hazard_coverage = _check(box, "Require hazard coverage")
	biomes = _field(box, "Biomes (comma-separated)")
	region_types = _field(box, "Region types (comma-separated)")
	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(300, 40)
	get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	var result := RulesetDraft.load(DataRoot.ruleset_path())
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not load ruleset.")); status_label.modulate = DialogStyle.COLOR_DANGER
		get_ok_button().disabled = true; popup_centered(); return
	draft = result["draft"]
	loading = true
	var world: Dictionary = draft.data.get("world", {})
	var regions: Dictionary = world.get("regions", {}) if world.get("regions", {}) is Dictionary else {}
	var status: Dictionary = draft.data.get("status", {})
	var systems: Dictionary = draft.data.get("systems", {})
	ruleset_id.text = str(draft.data.get("ruleset_id", "")); world_mode.text = str(draft.data.get("world_mode", "")); progression_model.text = str(draft.data.get("progression_model", ""))
	stats.text = _joined(status.get("stats", [])); biomes.text = _joined(regions.get("biomes", [])); region_types.text = _joined(regions.get("region_types", []))
	require_classification.button_pressed = bool(regions.get("require_classification", false)); require_level_bands.button_pressed = bool(regions.get("require_level_bands", false)); require_hazard_coverage.button_pressed = bool(regions.get("require_hazard_coverage", false))
	var manifest = JSON.parse_string(FileAccess.get_file_as_string(DataRoot.root().path_join("content_set.manifest.json")))
	var capabilities: Array = manifest.get("capabilities", []) if manifest is Dictionary else []
	for system_id in system_checks:
		var declaration = systems.get(system_id, {})
		var inherited: bool = capabilities.has(system_id) or system_id == "economy"
		system_checks[system_id].button_pressed = bool(declaration.get("enabled", inherited)) if declaration is Dictionary else inherited
		system_checks[system_id].tooltip_text = "Changing a capability must agree with the manifest. Conflicts are refused on save." if system_id != "economy" else "Enabled by default when no override is declared."
	for child in faction_rows.get_children(): _remove_row(child)
	var factions: Dictionary = draft.data.get("factions", {})
	var extras: Array = factions.get("extra", []) if factions.get("extra", []) is Array else []
	for entry in extras:
		if entry is Dictionary: _add_faction_row(str(entry.get("id", "")), str(entry.get("disposition", "neutral")), entry)
	faction_baseline = _faction_entries().duplicate(true)
	_reset_form_baseline()
	loading = false; form_dirty = false; get_ok_button().disabled = true
	status_label.text = "Editing %s. Untouched ruleset sections are preserved exactly." % DataRoot.ruleset_path(); status_label.modulate = InspectorStyle.COLOR_TEXT_DIM
	popup_centered()

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	draft.data = draft.original.duplicate(true)
	for pair in [[ruleset_id, "ruleset_id"], [world_mode, "world_mode"], [progression_model, "progression_model"]]:
		if _field_changed(pair[0]): _put_path(draft.data, pair[1], pair[0].text.strip_edges())
	for system_id in system_checks:
		if _field_changed(system_checks[system_id]): draft.set_system_enabled(system_id, system_checks[system_id].button_pressed)
	var factions := _faction_entries()
	if factions != faction_baseline: draft.set_faction_extras(factions)
	if _field_changed(stats): draft.set_status_stats(_split(stats.text))
	for pair in [[require_classification, "require_classification"], [require_level_bands, "require_level_bands"], [require_hazard_coverage, "require_hazard_coverage"]]:
		if _field_changed(pair[0]): _put_path(draft.data, "world.regions." + pair[1], pair[0].button_pressed)
	for pair in [[biomes, "biomes"], [region_types, "region_types"]]:
		if _field_changed(pair[0]): _put_path(draft.data, "world.regions." + pair[1], _split(pair[0].text))
	var result := draft.save()
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not save ruleset.")); status_label.modulate = DialogStyle.COLOR_DANGER; return
	form_dirty = false; get_ok_button().disabled = true
	ruleset_saved.emit()
	_finish_save()

func _field(parent: Control, label: String) -> LineEdit:
	var row := VBoxContainer.new(); row.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(field); parent.add_child(row); return field

func _check(parent: Control, label: String) -> CheckBox:
	var check := CheckBox.new(); check.text = label; check.toggled.connect(func(_value): _mark_dirty()); parent.add_child(check); return check

func _split(text: String) -> Array: return [] if text.strip_edges() == "" else Array(text.split(",", true)).map(func(value): return str(value).strip_edges())
func _joined(value) -> String: return ", ".join(value) if value is Array else ""

func _add_faction_row(faction_id: String, disposition: String, source: Dictionary = {}):
	var row := HBoxContainer.new(); row.set_meta("source", source.duplicate(true)); row.set_meta("initial_id", faction_id); row.set_meta("initial_disposition", disposition); faction_rows.add_child(row)
	var id_field := LineEdit.new(); id_field.placeholder_text = "faction id"; id_field.text = faction_id; id_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(id_field)
	var kind := OptionButton.new(); var options := ["hostile", "friendly", "neutral", "player"]
	if not options.has(disposition): options.append(disposition)
	for option in options: kind.add_item(option)
	kind.select(maxi(0, options.find(disposition))); InspectorStyle.apply_button_style(kind); kind.item_selected.connect(func(_index): _mark_dirty()); row.add_child(kind)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove custom faction"; remove.pressed.connect(func(): _remove_row(row); _mark_dirty()); row.add_child(remove)

func _faction_entries() -> Array:
	var out: Array = []
	for row in faction_rows.get_children():
		var id_field: LineEdit = row.get_child(0)
		var disposition: OptionButton = row.get_child(1)
		var entry: Dictionary = row.get_meta("source").duplicate(true)
		if entry.has("id") or id_field.text != row.get_meta("initial_id") or entry.is_empty(): entry["id"] = id_field.text.strip_edges()
		if entry.has("disposition") or disposition.get_item_text(disposition.selected) != row.get_meta("initial_disposition") or row.get_meta("source").is_empty(): entry["disposition"] = disposition.get_item_text(disposition.selected)
		out.append(entry)
	return out

func _mark_dirty():
	if loading or draft == null: return
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved ruleset changes." if form_dirty else "No unsaved changes."; status_label.modulate = Color("f2cf74")
