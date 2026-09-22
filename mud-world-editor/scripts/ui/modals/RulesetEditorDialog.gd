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
var salvage_default: OptionButton
var salvage_rows: VBoxContainer
var salvage_baseline: Dictionary = {}
var skill_bonus_rows: VBoxContainer
var content_database: DatabaseManager
var form_dirty := false
var loading := false
var faction_baseline: Array = []
var skill_bonus_baseline: Dictionary = {}

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
	box.add_child(InspectorStyle.create_sub_header("Crafting salvage"))
	var salvage_hint := InspectorStyle.lbl("A family rule says what an item becomes when salvaged. An item can still declare its own output.", InspectorStyle.COLOR_TEXT_DIM); salvage_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(salvage_hint)
	var default_row := HBoxContainer.new(); default_row.add_child(InspectorStyle.lbl("Fallback output", InspectorStyle.COLOR_TEXT_DIM))
	salvage_default = OptionButton.new(); salvage_default.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_button_style(salvage_default); salvage_default.item_selected.connect(func(index): salvage_default.select(index); _mark_dirty()); default_row.add_child(salvage_default); box.add_child(default_row)
	var salvage_header := HBoxContainer.new(); salvage_header.add_child(InspectorStyle.create_sub_header("Family rules"))
	var salvage_spacer := Control.new(); salvage_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; salvage_header.add_child(salvage_spacer)
	var add_salvage := Button.new(); add_salvage.text = "+ Family Rule"; InspectorStyle.apply_button_style(add_salvage, InspectorStyle.COLOR_SUCCESS); add_salvage.pressed.connect(func(): _add_salvage_row("", {}); _mark_dirty()); salvage_header.add_child(add_salvage); box.add_child(salvage_header)
	salvage_rows = VBoxContainer.new(); salvage_rows.add_theme_constant_override("separation", 5); box.add_child(salvage_rows)
	box.add_child(InspectorStyle.create_sub_header("Custom Factions"))
	var faction_hint := InspectorStyle.lbl("Built-in factions remain engine-owned. Add only this set's custom factions.", InspectorStyle.COLOR_TEXT_DIM); box.add_child(faction_hint)
	faction_rows = VBoxContainer.new(); faction_rows.add_theme_constant_override("separation", 5); box.add_child(faction_rows)
	var add_faction := Button.new(); add_faction.text = "+ Add Custom Faction"; InspectorStyle.apply_button_style(add_faction, InspectorStyle.COLOR_SUCCESS); add_faction.pressed.connect(func(): _add_faction_row("", "neutral"); _mark_dirty()); box.add_child(add_faction)
	box.add_child(InspectorStyle.create_sub_header("Declared Stats"))
	stats = _field(box, "Stats (comma-separated)")
	stats.tooltip_text = "The active stat vocabulary for this ruleset. Existing unknown sections remain untouched."
	var skill_header := HBoxContainer.new(); skill_header.add_child(InspectorStyle.create_sub_header("Skill Stat Bonuses"))
	var skill_spacer := Control.new(); skill_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; skill_header.add_child(skill_spacer)
	var add_skill_bonus := Button.new(); add_skill_bonus.text = "+ Skill Bonus"; InspectorStyle.apply_button_style(add_skill_bonus, InspectorStyle.COLOR_SUCCESS)
	add_skill_bonus.pressed.connect(func(): _add_skill_bonus_row("", {}); _mark_dirty())
	skill_header.add_child(add_skill_bonus); box.add_child(skill_header)
	var skill_hint := InspectorStyle.lbl("Which stat backs a skill check, and how much each point above 10 adds (skill_system.py). Leaving the stat blank means no bonus.", InspectorStyle.COLOR_TEXT_DIM)
	skill_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(skill_hint)
	skill_bonus_rows = VBoxContainer.new(); skill_bonus_rows.add_theme_constant_override("separation", 5); box.add_child(skill_bonus_rows)
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
	content_database = DatabaseManager.new()
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
	_load_salvage_rules()
	_load_skill_bonuses()
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
	if _salvage_rules_changed(): draft.set_salvage_rules(_salvage_rules())
	if _skill_bonuses_changed(): draft.set_skill_stat_bonuses(_skill_bonuses())
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


func _load_salvage_rules():
	for child in salvage_rows.get_children(): _remove_row(child)
	var crafting: Dictionary = draft.data.get("crafting", {}) if draft.data.get("crafting", {}) is Dictionary else {}
	var rules: Dictionary = crafting.get("salvage_rules", {}) if crafting.get("salvage_rules", {}) is Dictionary else {}
	salvage_baseline = rules.duplicate(true)
	_populate_item_picker(salvage_default, str(rules.get("default_item_id", "")), "No fallback output")
	var families: Dictionary = rules.get("by_family", {}) if rules.get("by_family", {}) is Dictionary else {}
	for family_id in families:
		if families[family_id] is Dictionary: _add_salvage_row(str(family_id), families[family_id].duplicate(true))
	if salvage_rows.get_child_count() == 0:
		salvage_rows.add_child(InspectorStyle.lbl("No family rules. The fallback is used unless an item declares its own output.", InspectorStyle.COLOR_TEXT_DIM))


func _add_salvage_row(family_id: String, rule: Dictionary):
	for child in salvage_rows.get_children():
		if child is Label and child.text.begins_with("No family rules"): _remove_row(child)
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("rule", rule)
	var family := OptionButton.new(); family.custom_minimum_size.x = 150; family.name = "SalvageFamily"
	var ids: Array = ["Choose family"]
	if content_database != null: ids.append_array(content_database.catalog.family_ids())
	for id in ids:
		family.add_item(str(id)); family.set_item_metadata(family.item_count - 1, "" if str(id) == "Choose family" else str(id))
		if str(id) == family_id: family.select(family.item_count - 1)
	if family_id != "" and family.selected == 0:
		family.add_item("Missing: " + family_id); family.set_item_metadata(family.item_count - 1, family_id); family.select(family.item_count - 1)
	InspectorStyle.apply_button_style(family); family.item_selected.connect(func(index): family.select(index); _mark_dirty()); row.add_child(family)
	var reference := ReferenceEditor.new(); reference.changed.connect(func(): _mark_dirty()); reference.build(row, rule, Callable(self, "_salvage_suggestions"))
	var rate := SpinBox.new(); rate.min_value = 0; rate.max_value = 20; rate.step = 0.1; rate.value = float(rule.get("quantity_per_weight", 1.0)); rate.tooltip_text = "output per unit of weight"; rate.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(rate)
	rate.value_changed.connect(func(value): rule["quantity_per_weight"] = float(value); _mark_dirty()); row.add_child(rate)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(row); _mark_dirty()); row.add_child(remove)
	salvage_rows.add_child(row)


func _populate_item_picker(picker: OptionButton, selected_id: String, empty_label: String):
	picker.clear(); picker.add_item(empty_label); picker.set_item_metadata(0, "")
	var ids: Array = content_database.get_item_ids() if content_database != null else []
	for item_id in ids:
		var label := str(item_id)
		if content_database.items.get(item_id) is Dictionary: label = "%s — %s" % [str(content_database.items[item_id].get("name", item_id)), item_id]
		picker.add_item(label); picker.set_item_metadata(picker.item_count - 1, item_id)
		if str(item_id) == selected_id: picker.select(picker.item_count - 1)
	if selected_id != "" and picker.selected == 0:
		picker.add_item("Missing: " + selected_id); picker.set_item_metadata(picker.item_count - 1, selected_id); picker.select(picker.item_count - 1)


func _salvage_suggestions(kind: String) -> Array:
	if content_database == null: return []
	match kind:
		"item_family": return content_database.catalog.family_ids()
		"capability": return content_database.catalog.capability_ids()
		_: return content_database.get_item_ids()


func _salvage_rules() -> Dictionary:
	# Preserve comments and legacy class rules while replacing only the family
	# section this dialog owns.
	var rules := salvage_baseline.duplicate(true)
	var by_family := {}
	for row in salvage_rows.get_children():
		if not (row is HBoxContainer) or row.get_child_count() < 2: continue
		var family: OptionButton = row.get_child(0)
		var family_id := str(family.get_item_metadata(family.selected))
		var rule: Dictionary = row.get_meta("rule", {})
		if family_id != "": by_family[family_id] = rule.duplicate(true)
	if by_family.is_empty(): rules.erase("by_family")
	else: rules["by_family"] = by_family
	var default_id := str(salvage_default.get_item_metadata(salvage_default.selected))
	if default_id == "": rules.erase("default_item_id")
	else: rules["default_item_id"] = default_id
	return rules


func _salvage_rules_changed() -> bool:
	return JSON.stringify(_salvage_rules()) != JSON.stringify(salvage_baseline)


# `skills.stat_bonuses` (`skill_system.py:43-49`; `content_set.py::
# _validate_skills_rules`): which stat backs a skill check, and how much each
# point above 10 adds. Only the shape is engine-checked -- a stat name is
# whatever this ruleset says it is, since the ruleset is where stats are
# declared in the first place -- so the stat field is free text, the same as
# the "Declared Stats" field above it, rather than a picker over a vocabulary
# that would be circular.
func _load_skill_bonuses():
	for child in skill_bonus_rows.get_children(): _remove_row(child)
	var skills: Dictionary = draft.data.get("skills", {}) if draft.data.get("skills", {}) is Dictionary else {}
	var bonuses: Dictionary = skills.get("stat_bonuses", {}) if skills.get("stat_bonuses", {}) is Dictionary else {}
	# `JSON.parse_string` always returns a float for `per_point`, no matter what
	# the file spells -- normalized the same way `_skill_bonuses()` reads its
	# rows so an unedited bonus does not report itself dirty merely for having
	# been read off disk (the SpinBox int-coercion, applied consistently).
	skill_bonus_baseline = _normalized_bonuses(bonuses)
	for skill_id in bonuses:
		if bonuses[skill_id] is Dictionary: _add_skill_bonus_row(str(skill_id), bonuses[skill_id].duplicate(true))
	if skill_bonus_rows.get_child_count() == 0:
		skill_bonus_rows.add_child(InspectorStyle.lbl("No skill bonuses declared.", InspectorStyle.COLOR_TEXT_DIM))


func _normalized_bonuses(bonuses: Dictionary) -> Dictionary:
	var out := {}
	for skill_id in bonuses:
		var rule = bonuses[skill_id]
		if not (rule is Dictionary): continue
		var entry := {}
		var stat := str(rule.get("stat", "")).strip_edges()
		if stat != "": entry["stat"] = stat
		entry["per_point"] = int(rule.get("per_point", 1))
		out[str(skill_id)] = entry
	return out


func _add_skill_bonus_row(skill_id: String, rule: Dictionary):
	for child in skill_bonus_rows.get_children():
		if child is Label and child.text.begins_with("No skill bonuses"): _remove_row(child)
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	row.set_meta("source", rule.duplicate(true)); row.set_meta("initial_id", skill_id)
	var id_field := LineEdit.new(); id_field.placeholder_text = "skill id"; id_field.text = skill_id
	id_field.custom_minimum_size.x = 130; InspectorStyle.apply_input_style(id_field)
	id_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(id_field)
	var stat_field := LineEdit.new(); stat_field.placeholder_text = "stat this skill uses"; stat_field.text = str(rule.get("stat", ""))
	stat_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(stat_field)
	stat_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(stat_field)
	row.add_child(InspectorStyle.lbl("per point above 10:", InspectorStyle.COLOR_TEXT_DIM))
	var per_point := SpinBox.new(); per_point.min_value = 0; per_point.max_value = 20; per_point.step = 1
	per_point.value = int(rule.get("per_point", 1)); per_point.custom_minimum_size.x = 60
	InspectorStyle.apply_input_style(per_point); per_point.value_changed.connect(func(_value): _mark_dirty())
	row.add_child(per_point)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove skill bonus"
	remove.pressed.connect(func(): _remove_row(row); _mark_dirty())
	row.add_child(remove)
	skill_bonus_rows.add_child(row)


func _skill_bonuses() -> Dictionary:
	var out := {}
	for row in skill_bonus_rows.get_children():
		if not (row is HBoxContainer) or row.get_child_count() < 4: continue
		var id_field: LineEdit = row.get_child(0)
		var stat_field: LineEdit = row.get_child(1)
		var per_point: SpinBox = row.get_child(3)
		var skill_id := id_field.text.strip_edges()
		if skill_id == "": continue
		var entry: Dictionary = row.get_meta("source").duplicate(true)
		var stat := stat_field.text.strip_edges()
		if stat == "": entry.erase("stat")
		else: entry["stat"] = stat
		entry["per_point"] = int(per_point.value)
		out[skill_id] = entry
	return out


func _skill_bonuses_changed() -> bool:
	return JSON.stringify(_skill_bonuses()) != JSON.stringify(skill_bonus_baseline)

func _mark_dirty():
	if loading or draft == null: return
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved ruleset changes." if form_dirty else "No unsaved changes."; status_label.modulate = Color("f2cf74")
