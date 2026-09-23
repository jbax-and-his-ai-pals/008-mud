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
var retreat_skill: LineEdit
var retreat_base: SpinBox
var retreat_per_level: SpinBox
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
var npc_schedule_categories: VBoxContainer
var npc_schedule_roles: VBoxContainer
var npc_schedule_excluded: LineEdit
var npc_schedule_baseline: Dictionary = {}
var advancement_base: SpinBox
var advancement_multiplier: SpinBox
var advancement_grant_rows: VBoxContainer
var advancement_baseline: Dictionary = {}
var weather_description_rows: VBoxContainer
var weather_profile_rows: VBoxContainer
var weather_description_baseline: Dictionary = {}
var weather_profile_baseline: Dictionary = {}
var quest_generation_section: QuestGenerationSection
var world_rules_section: WorldRulesSection
var crime_section: CrimeSection

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
	box.add_child(InspectorStyle.create_sub_header("Combat Retreat"))
	var retreat_hint := InspectorStyle.lbl("An empty skill permits retreat freely. Otherwise the skill check starts at the base difficulty and rises per toughest hostile level.", InspectorStyle.COLOR_TEXT_DIM); retreat_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(retreat_hint)
	retreat_skill = _field(box, "Retreat skill (optional)")
	var retreat_row := HBoxContainer.new(); retreat_row.add_child(InspectorStyle.lbl("Base difficulty", InspectorStyle.COLOR_TEXT_DIM))
	retreat_base = SpinBox.new(); retreat_base.min_value = 0; retreat_base.max_value = 1000; retreat_base.step = 1; retreat_base.custom_minimum_size.x = 90; InspectorStyle.apply_input_style(retreat_base); retreat_base.value_changed.connect(func(_value): _mark_dirty()); retreat_row.add_child(retreat_base)
	retreat_row.add_child(InspectorStyle.lbl("Per hostile level", InspectorStyle.COLOR_TEXT_DIM))
	retreat_per_level = SpinBox.new(); retreat_per_level.min_value = 0; retreat_per_level.max_value = 1000; retreat_per_level.step = 1; retreat_per_level.custom_minimum_size.x = 90; InspectorStyle.apply_input_style(retreat_per_level); retreat_per_level.value_changed.connect(func(_value): _mark_dirty()); retreat_row.add_child(retreat_per_level); box.add_child(retreat_row)
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
	box.add_child(InspectorStyle.create_sub_header("NPC Schedules"))
	var schedule_hint := InspectorStyle.lbl("Optional setting-wide routines. Roles match NPC template IDs; location slots resolve top-to-bottom, so fallback and exclude can only refer to an earlier slot.", InspectorStyle.COLOR_TEXT_DIM)
	schedule_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(schedule_hint)
	npc_schedule_excluded = _field(box, "Exclude NPC names containing (comma-separated)")
	var category_header := HBoxContainer.new(); category_header.add_child(InspectorStyle.lbl("Room Categories", InspectorStyle.COLOR_TEXT_DIM))
	var category_spacer := Control.new(); category_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; category_header.add_child(category_spacer)
	var add_category := Button.new(); add_category.text = "+ Category"; InspectorStyle.apply_button_style(add_category, InspectorStyle.COLOR_SUCCESS)
	add_category.pressed.connect(func(): _add_schedule_category_row("", [], {}); _mark_dirty()); category_header.add_child(add_category); box.add_child(category_header)
	npc_schedule_categories = VBoxContainer.new(); npc_schedule_categories.add_theme_constant_override("separation", 5); box.add_child(npc_schedule_categories)
	var role_header := HBoxContainer.new(); role_header.add_child(InspectorStyle.lbl("Schedule Roles", InspectorStyle.COLOR_TEXT_DIM))
	var role_spacer := Control.new(); role_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; role_header.add_child(role_spacer)
	var add_role := Button.new(); add_role.text = "+ Schedule Role"; InspectorStyle.apply_button_style(add_role, InspectorStyle.COLOR_SUCCESS)
	add_role.pressed.connect(func(): _add_schedule_role({}, "", []); _mark_dirty()); role_header.add_child(add_role); box.add_child(role_header)
	npc_schedule_roles = VBoxContainer.new(); npc_schedule_roles.add_theme_constant_override("separation", 9); box.add_child(npc_schedule_roles)
	box.add_child(InspectorStyle.create_sub_header("Advancement"))
	var advancement_hint := InspectorStyle.lbl("First-time activity rewards. A grant's kinds must be engine-recognized ledger events; use item family before an engine item class whenever possible.", InspectorStyle.COLOR_TEXT_DIM)
	advancement_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(advancement_hint)
	var curve_row := HBoxContainer.new(); curve_row.add_theme_constant_override("separation", 8); curve_row.add_child(InspectorStyle.lbl("XP at level 2", InspectorStyle.COLOR_TEXT_DIM))
	advancement_base = SpinBox.new(); advancement_base.min_value = 1; advancement_base.max_value = 100000; advancement_base.step = 1; advancement_base.custom_minimum_size.x = 100; InspectorStyle.apply_input_style(advancement_base); advancement_base.value_changed.connect(func(_value): _mark_dirty()); curve_row.add_child(advancement_base)
	curve_row.add_child(InspectorStyle.lbl("Growth multiplier", InspectorStyle.COLOR_TEXT_DIM))
	advancement_multiplier = SpinBox.new(); advancement_multiplier.min_value = 1.01; advancement_multiplier.max_value = 10; advancement_multiplier.step = 0.01; advancement_multiplier.custom_minimum_size.x = 100; InspectorStyle.apply_input_style(advancement_multiplier); advancement_multiplier.value_changed.connect(func(_value): _mark_dirty()); curve_row.add_child(advancement_multiplier); box.add_child(curve_row)
	var grants_header := HBoxContainer.new(); grants_header.add_child(InspectorStyle.lbl("Activity grants", InspectorStyle.COLOR_TEXT_DIM))
	var grants_spacer := Control.new(); grants_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; grants_header.add_child(grants_spacer)
	var add_grant := Button.new(); add_grant.text = "+ Activity Grant"; InspectorStyle.apply_button_style(add_grant, InspectorStyle.COLOR_SUCCESS)
	add_grant.pressed.connect(func(): _add_advancement_grant({}, ""); _mark_dirty()); grants_header.add_child(add_grant); box.add_child(grants_header)
	advancement_grant_rows = VBoxContainer.new(); advancement_grant_rows.add_theme_constant_override("separation", 7); box.add_child(advancement_grant_rows)
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
	box.add_child(InspectorStyle.create_sub_header("Weather"))
	var weather_hint := InspectorStyle.lbl("Weather types are this ruleset's own vocabulary -- whatever weather.chances or a profile's own mapping names.", InspectorStyle.COLOR_TEXT_DIM)
	weather_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(weather_hint)
	var desc_header := HBoxContainer.new(); desc_header.add_child(InspectorStyle.lbl("Descriptions", InspectorStyle.COLOR_TEXT_DIM))
	var desc_spacer := Control.new(); desc_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; desc_header.add_child(desc_spacer)
	var add_desc := Button.new(); add_desc.text = "+ Description"; InspectorStyle.apply_button_style(add_desc, InspectorStyle.COLOR_SUCCESS)
	add_desc.pressed.connect(func(): _add_string_map_row(weather_description_rows, "", "", "weather type", "flavor text"); _mark_dirty())
	desc_header.add_child(add_desc); box.add_child(desc_header)
	weather_description_rows = VBoxContainer.new(); weather_description_rows.add_theme_constant_override("separation", 5); box.add_child(weather_description_rows)
	var profile_header := HBoxContainer.new(); profile_header.add_child(InspectorStyle.lbl("Profiles", InspectorStyle.COLOR_TEXT_DIM))
	var profile_spacer := Control.new(); profile_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; profile_header.add_child(profile_spacer)
	var add_profile := Button.new(); add_profile.text = "+ Profile"; InspectorStyle.apply_button_style(add_profile, InspectorStyle.COLOR_SUCCESS)
	add_profile.pressed.connect(func(): _add_weather_profile_row("", {}); _mark_dirty())
	profile_header.add_child(add_profile); box.add_child(profile_header)
	var profile_hint := InspectorStyle.lbl("A profile translates global weather into a region's local expression (an alpine pass turning rain into snow) and adds a travel advisory per local type.", InspectorStyle.COLOR_TEXT_DIM)
	profile_hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(profile_hint)
	weather_profile_rows = VBoxContainer.new(); weather_profile_rows.add_theme_constant_override("separation", 7); box.add_child(weather_profile_rows)
	quest_generation_section = QuestGenerationSection.new()
	quest_generation_section.build(box, func(): _mark_dirty())
	world_rules_section = WorldRulesSection.new()
	world_rules_section.build(box, func(): _mark_dirty())
	crime_section = CrimeSection.new()
	crime_section.build(box, func(): _mark_dirty())
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
	var retreat: Dictionary = draft.data.get("combat", {}).get("retreat", {}) if draft.data.get("combat", {}) is Dictionary and draft.data.get("combat", {}).get("retreat", {}) is Dictionary else {}
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
	retreat_skill.text = str(retreat.get("skill", "")); retreat_base.value = float(retreat.get("base_difficulty", 10)); retreat_per_level.value = float(retreat.get("difficulty_per_hostile_level", 2))
	for child in faction_rows.get_children(): _remove_row(child)
	var factions: Dictionary = draft.data.get("factions", {})
	var extras: Array = factions.get("extra", []) if factions.get("extra", []) is Array else []
	for entry in extras:
		if entry is Dictionary: _add_faction_row(str(entry.get("id", "")), str(entry.get("disposition", "neutral")), entry)
	faction_baseline = _faction_entries().duplicate(true)
	_load_salvage_rules()
	_load_skill_bonuses()
	_load_npc_schedules()
	_load_advancement()
	_load_weather_section()
	var quest_generation = draft.data.get("quest_generation", {})
	quest_generation_section.load(quest_generation if quest_generation is Dictionary else {}, content_database)
	world_rules_section.load(draft.data, content_database)
	crime_section.load(draft.data, content_database)
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
	if _field_changed(retreat_skill) or _field_changed(retreat_base) or _field_changed(retreat_per_level):
		_put_path(draft.data, "combat.retreat.skill", retreat_skill.text.strip_edges())
		_put_path(draft.data, "combat.retreat.base_difficulty", int(retreat_base.value))
		_put_path(draft.data, "combat.retreat.difficulty_per_hostile_level", int(retreat_per_level.value))
	var factions := _faction_entries()
	if factions != faction_baseline: draft.set_faction_extras(factions)
	if _salvage_rules_changed(): draft.set_salvage_rules(_salvage_rules())
	if _skill_bonuses_changed(): draft.set_skill_stat_bonuses(_skill_bonuses())
	if _npc_schedules_changed(): draft.set_npc_schedules(_npc_schedules())
	if _advancement_changed(): draft.set_advancement(_advancement())
	if _weather_descriptions_changed(): draft.set_weather_descriptions(_weather_descriptions())
	if _weather_profiles_changed(): draft.set_weather_profiles(_weather_profiles())
	if quest_generation_section.changed(): draft.set_quest_generation(quest_generation_section.compose())
	if world_rules_section.changed(): draft.set_world_rules(world_rules_section.compose())
	if crime_section.changed(): draft.set_crime(crime_section.compose())
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


# `AdvancementManager` reads a small ruleset-owned curve and an array of
# first-time ledger grants.  This form owns exactly those runtime fields and
# leaves any future presentation metadata on each source row intact.
func _load_advancement():
	for child in advancement_grant_rows.get_children(): _remove_row(child)
	var advancement: Dictionary = draft.data.get("advancement", {}) if draft.data.get("advancement", {}) is Dictionary else {}
	advancement_baseline = advancement.duplicate(true)
	var curve: Dictionary = advancement.get("curve", {}) if advancement.get("curve", {}) is Dictionary else {}
	advancement_base.value = float(curve.get("base", 100))
	advancement_multiplier.value = float(curve.get("multiplier", 1.25))
	var grants: Array = advancement.get("grants", []) if advancement.get("grants", []) is Array else []
	for source in grants:
		if source is Dictionary: _add_advancement_grant(source.duplicate(true), str(source.get("id", "")))
	if advancement_grant_rows.get_child_count() == 0:
		advancement_grant_rows.add_child(InspectorStyle.lbl("No activity grants. The engine will record first-time events but award no XP.", InspectorStyle.COLOR_TEXT_DIM))


func _add_advancement_grant(source: Dictionary, grant_id: String):
	for child in advancement_grant_rows.get_children():
		if child is Label: _remove_row(child)
	var card := VBoxContainer.new(); card.name = "AdvancementGrant"; card.add_theme_constant_override("separation", 4); card.set_meta("source", source.duplicate(true))
	var criteria: Dictionary = source.get("match", {}) if source.get("match", {}) is Dictionary else {}
	var header := HBoxContainer.new(); header.name = "Header"; header.add_theme_constant_override("separation", 6); card.add_child(header)
	var id_field := LineEdit.new(); id_field.name = "GrantId"; id_field.placeholder_text = "grant id"; id_field.text = grant_id; id_field.custom_minimum_size.x = 150
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_text): _mark_dirty()); header.add_child(id_field)
	var kinds := LineEdit.new(); kinds.name = "Kinds"; kinds.placeholder_text = "kind(s), comma-separated"; kinds.text = _joined(criteria.get("kind", [])) if criteria.get("kind", []) is Array else str(criteria.get("kind", "")); kinds.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	kinds.set_meta("was_array", criteria.get("kind", null) is Array); kinds.tooltip_text = "Known: region, landmark, creature, item, recipe, spell, npc, relationship, quest, collection, discovery."
	InspectorStyle.apply_input_style(kinds); kinds.text_changed.connect(func(_text): _mark_dirty()); header.add_child(kinds)
	var xp := SpinBox.new(); xp.name = "XP"; xp.min_value = -100000; xp.max_value = 100000; xp.step = 1; xp.value = float(source.get("xp", 0)); xp.custom_minimum_size.x = 80
	InspectorStyle.apply_input_style(xp); xp.value_changed.connect(func(_value): _mark_dirty()); header.add_child(xp)
	var remove := Button.new(); remove.text = "Remove Grant"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_row(card); _ensure_advancement_empty_hint(); _mark_dirty()); header.add_child(remove)
	var message := LineEdit.new(); message.name = "Message"; message.placeholder_text = "optional player-facing first-time message"; message.text = str(source.get("message", "")); message.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(message); message.text_changed.connect(func(_text): _mark_dirty()); card.add_child(message)
	var filters := HBoxContainer.new(); filters.name = "Filters"; filters.add_theme_constant_override("separation", 6); card.add_child(filters)
	for spec in [["Region", "region_id", "region id", 120], ["NPC tags", "npc_tags", "npc tags", 140], ["Item family", "item_family", "item family", 130], ["Item type", "item_type", "engine item class", 130], ["Item tags", "item_tags", "item tags", 130], ["Entry IDs", "entry_ids", "entry ids", 140]]:
		var field := LineEdit.new(); field.name = spec[0]; field.placeholder_text = spec[2]; field.custom_minimum_size.x = spec[3]
		field.text = _joined(criteria.get(spec[1], [])) if criteria.get(spec[1], []) is Array else str(criteria.get(spec[1], ""))
		field.set_meta("key", spec[1]); field.set_meta("was_array", criteria.get(spec[1], null) is Array)
		InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); filters.add_child(field)
	var once := CheckBox.new(); once.name = "OncePerKind"; once.text = "Once per kind"; once.button_pressed = bool(criteria.get("once_per_kind", false)); once.toggled.connect(func(_value): _mark_dirty()); filters.add_child(once)
	advancement_grant_rows.add_child(card)


func _advancement() -> Dictionary:
	var out := advancement_baseline.duplicate(true)
	# Do not manufacture an advancement section/curve just because another
	# ruleset field was saved. Defaults are displayed for discoverability, but
	# remain engine defaults until an author changes them.
	var curve: Dictionary = out.get("curve", {}) if out.get("curve", {}) is Dictionary else {}
	var curve_was_authored := out.get("curve", null) is Dictionary
	if curve_was_authored or int(advancement_base.value) != 100 or not is_equal_approx(advancement_multiplier.value, 1.25):
		curve["base"] = advancement_base.value; curve["multiplier"] = advancement_multiplier.value; out["curve"] = curve
	var grants: Array = []
	for card in advancement_grant_rows.get_children():
		if not (card is VBoxContainer) or card.name != "AdvancementGrant": continue
		var grant_id := (card.get_node("Header/GrantId") as LineEdit).text.strip_edges()
		if grant_id == "": continue
		var grant: Dictionary = card.get_meta("source").duplicate(true); grant["id"] = grant_id; grant["xp"] = (card.get_node("Header/XP") as SpinBox).value
		var message := (card.get_node("Message") as LineEdit).text.strip_edges()
		if message == "": grant.erase("message")
		else: grant["message"] = message
		var criteria: Dictionary = grant.get("match", {}) if grant.get("match", {}) is Dictionary else {}
		var kinds_field: LineEdit = card.get_node("Header/Kinds"); var kinds := _split(kinds_field.text)
		criteria["kind"] = kinds if kinds_field.get_meta("was_array", false) or kinds.size() != 1 else (kinds[0] if not kinds.is_empty() else "")
		for field in (card.get_node("Filters") as HBoxContainer).get_children():
			if not field is LineEdit: continue
			var key := str(field.get_meta("key", "")); var value := (field as LineEdit).text.strip_edges()
			if value == "": criteria.erase(key)
			elif field.get_meta("was_array", false) or key in ["npc_tags", "item_tags", "entry_ids"]: criteria[key] = _split(value)
			else: criteria[key] = value
		var once_per_kind := (card.get_node("Filters/OncePerKind") as CheckBox).button_pressed
		if once_per_kind or criteria.has("once_per_kind"): criteria["once_per_kind"] = once_per_kind
		else: criteria.erase("once_per_kind")
		grant["match"] = criteria; grants.append(grant)
	if grants.is_empty(): out.erase("grants")
	else: out["grants"] = grants
	return out


func _advancement_changed() -> bool:
	return JSON.stringify(_advancement()) != JSON.stringify(advancement_baseline)


func _ensure_advancement_empty_hint():
	if advancement_grant_rows.get_child_count() == 0:
		advancement_grant_rows.add_child(InspectorStyle.lbl("No activity grants. The engine will record first-time events but award no XP.", InspectorStyle.COLOR_TEXT_DIM))


# NPC schedules deliberately have their own editor rather than falling back to
# a generic JSON property.  The scheduler's grammar is useful authoring
# context: category names are chosen by this content set, slots are resolved in
# their listed order, and every daily activity references one of those slots.
# Rows carry a copy of their source object so future/setting-specific metadata
# survives edits to the fields this dialog owns.
func _load_npc_schedules():
	for child in npc_schedule_categories.get_children(): _remove_row(child)
	for child in npc_schedule_roles.get_children(): _remove_row(child)
	var schedules: Dictionary = draft.data.get("npc_schedules", {}) if draft.data.get("npc_schedules", {}) is Dictionary else {}
	npc_schedule_baseline = schedules.duplicate(true)
	npc_schedule_excluded.text = _joined(schedules.get("excluded_name_keywords", []))
	var categories: Dictionary = schedules.get("room_categories", {}) if schedules.get("room_categories", {}) is Dictionary else {}
	for category_id in categories:
		_add_schedule_category_row(str(category_id), categories[category_id] if categories[category_id] is Array else [], {})
	var roles: Array = schedules.get("roles", []) if schedules.get("roles", []) is Array else []
	for source in roles:
		if source is Dictionary:
			_add_schedule_role(source.duplicate(true), str(source.get("id", "")), source.get("template_keywords", []) if source.get("template_keywords", []) is Array else [])
	if npc_schedule_categories.get_child_count() == 0:
		npc_schedule_categories.add_child(InspectorStyle.lbl("No categories. Add a category to match room-name keywords.", InspectorStyle.COLOR_TEXT_DIM))
	if npc_schedule_roles.get_child_count() == 0:
		npc_schedule_roles.add_child(InspectorStyle.lbl("No scheduled roles. NPCs can still use explicit schedules on their templates.", InspectorStyle.COLOR_TEXT_DIM))


func _add_schedule_category_row(category_id: String, keywords: Array, source: Dictionary):
	for child in npc_schedule_categories.get_children():
		if child is Label: _remove_row(child)
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("source", source.duplicate(true))
	var id_field := LineEdit.new(); id_field.name = "CategoryId"; id_field.placeholder_text = "category id"; id_field.text = category_id; id_field.custom_minimum_size.x = 145
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(id_field)
	var keywords_field := LineEdit.new(); keywords_field.name = "Keywords"; keywords_field.placeholder_text = "room-name keywords, comma-separated"; keywords_field.text = _joined(keywords); keywords_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(keywords_field); keywords_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(keywords_field)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove room category"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_row(row); _ensure_schedule_empty_hints(); _mark_dirty()); row.add_child(remove)
	npc_schedule_categories.add_child(row)


func _add_schedule_role(source: Dictionary, role_id: String, keywords: Array):
	for child in npc_schedule_roles.get_children():
		if child is Label: _remove_row(child)
	var card := VBoxContainer.new(); card.add_theme_constant_override("separation", 5); card.set_meta("source", source.duplicate(true)); card.name = "ScheduleRole"
	var identity := HBoxContainer.new(); identity.name = "Identity"; identity.add_theme_constant_override("separation", 6); card.add_child(identity)
	var id_field := LineEdit.new(); id_field.name = "RoleId"; id_field.placeholder_text = "role id"; id_field.text = role_id; id_field.custom_minimum_size.x = 145
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_text): _mark_dirty()); identity.add_child(id_field)
	var keyword_field := LineEdit.new(); keyword_field.name = "TemplateKeywords"; keyword_field.placeholder_text = "template ID keywords, comma-separated"; keyword_field.text = _joined(keywords); keyword_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(keyword_field); keyword_field.text_changed.connect(func(_text): _mark_dirty()); identity.add_child(keyword_field)
	var remove_role := Button.new(); remove_role.text = "Remove Role"; remove_role.tooltip_text = "Remove this schedule role"; InspectorStyle.apply_button_style(remove_role, DialogStyle.COLOR_DANGER)
	remove_role.pressed.connect(func(): _remove_row(card); _ensure_schedule_empty_hints(); _mark_dirty()); identity.add_child(remove_role)
	var slots_header := HBoxContainer.new(); slots_header.add_child(InspectorStyle.lbl("Location slots (resolved in order)", InspectorStyle.COLOR_TEXT_DIM))
	var slots_spacer := Control.new(); slots_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; slots_header.add_child(slots_spacer)
	var add_slot := Button.new(); add_slot.text = "+ Slot"; InspectorStyle.apply_button_style(add_slot, InspectorStyle.COLOR_SUCCESS)
	add_slot.pressed.connect(func(): _add_schedule_slot(card.get_node("Slots") as VBoxContainer, "", {}); _mark_dirty()); slots_header.add_child(add_slot); card.add_child(slots_header)
	var slots := VBoxContainer.new(); slots.name = "Slots"; slots.add_theme_constant_override("separation", 4); card.add_child(slots)
	var source_slots: Dictionary = source.get("location_slots", {}) if source.get("location_slots", {}) is Dictionary else {}
	for slot_id in source_slots:
		if source_slots[slot_id] is Dictionary: _add_schedule_slot(slots, str(slot_id), source_slots[slot_id].duplicate(true))
	var schedule_header := HBoxContainer.new(); schedule_header.add_child(InspectorStyle.lbl("Daily activities", InspectorStyle.COLOR_TEXT_DIM))
	var schedule_spacer := Control.new(); schedule_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; schedule_header.add_child(schedule_spacer)
	var add_activity := Button.new(); add_activity.text = "+ Activity"; InspectorStyle.apply_button_style(add_activity, InspectorStyle.COLOR_SUCCESS)
	add_activity.pressed.connect(func(): _add_schedule_activity(card.get_node("Activities") as VBoxContainer, -1, {}); _mark_dirty()); schedule_header.add_child(add_activity); card.add_child(schedule_header)
	var activities := VBoxContainer.new(); activities.name = "Activities"; activities.add_theme_constant_override("separation", 4); card.add_child(activities)
	var source_schedule: Dictionary = source.get("schedule", {}) if source.get("schedule", {}) is Dictionary else {}
	for hour in source_schedule:
		if source_schedule[hour] is Dictionary: _add_schedule_activity(activities, int(str(hour)), source_schedule[hour].duplicate(true))
	npc_schedule_roles.add_child(card)


func _add_schedule_slot(parent: VBoxContainer, slot_id: String, source: Dictionary):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("source", source.duplicate(true)); parent.add_child(row)
	var id_field := LineEdit.new(); id_field.name = "SlotId"; id_field.placeholder_text = "slot"; id_field.text = slot_id; id_field.custom_minimum_size.x = 115
	InspectorStyle.apply_input_style(id_field); id_field.text_changed.connect(func(_text): _mark_dirty()); row.add_child(id_field)
	var picker := OptionButton.new(); picker.name = "SlotType"; picker.custom_minimum_size.x = 140
	for slot_type in ["self", "property_or_self", "category"]: picker.add_item(slot_type)
	var selected_type := str(source.get("type", "self")); var type_index := ["self", "property_or_self", "category"].find(selected_type)
	if type_index < 0: picker.add_item(selected_type); type_index = picker.item_count - 1
	picker.select(type_index); InspectorStyle.apply_button_style(picker); row.add_child(picker)
	var subject := LineEdit.new(); subject.name = "Subject"; subject.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	subject.text = str(source.get("property", "")) if selected_type == "property_or_self" else _joined(source.get("categories", []))
	InspectorStyle.apply_input_style(subject); subject.text_changed.connect(func(_text): _mark_dirty()); row.add_child(subject)
	var exclude := LineEdit.new(); exclude.name = "Exclude"; exclude.placeholder_text = "exclude slot"; exclude.text = str(source.get("exclude", "")); exclude.custom_minimum_size.x = 105
	InspectorStyle.apply_input_style(exclude); exclude.text_changed.connect(func(_text): _mark_dirty()); row.add_child(exclude)
	var fallback := LineEdit.new(); fallback.name = "Fallback"; fallback.placeholder_text = "fallback slot"; fallback.text = str(source.get("fallback", "")); fallback.custom_minimum_size.x = 110
	InspectorStyle.apply_input_style(fallback); fallback.text_changed.connect(func(_text): _mark_dirty()); row.add_child(fallback)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove location slot"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_row(row); _mark_dirty()); row.add_child(remove)
	picker.item_selected.connect(func(_index): _refresh_schedule_slot(row); _mark_dirty())
	_refresh_schedule_slot(row)


func _refresh_schedule_slot(row: HBoxContainer):
	var picker: OptionButton = row.get_node("SlotType")
	var subject: LineEdit = row.get_node("Subject")
	var exclude: LineEdit = row.get_node("Exclude")
	var fallback: LineEdit = row.get_node("Fallback")
	var slot_type := picker.get_item_text(picker.selected)
	subject.editable = slot_type != "self"; exclude.editable = slot_type == "category"; fallback.editable = slot_type == "category"
	if slot_type == "self": subject.placeholder_text = "uses NPC home"; subject.tooltip_text = "The NPC's own home room."
	elif slot_type == "property_or_self": subject.placeholder_text = "NPC property, e.g. work_location"; subject.tooltip_text = "Reads a region:room value from this NPC property, then falls back to its home."
	else: subject.placeholder_text = "category IDs, comma-separated"; subject.tooltip_text = "Choose from room categories defined above."


func _add_schedule_activity(parent: VBoxContainer, hour: int, source: Dictionary):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("source", source.duplicate(true)); parent.add_child(row)
	row.add_child(InspectorStyle.lbl("Hour", InspectorStyle.COLOR_TEXT_DIM))
	var hour_box := SpinBox.new(); hour_box.name = "Hour"; hour_box.min_value = 0; hour_box.max_value = 23; hour_box.step = 1; hour_box.value = 0 if hour < 0 else hour; hour_box.custom_minimum_size.x = 62
	InspectorStyle.apply_input_style(hour_box); hour_box.value_changed.connect(func(_value): _mark_dirty()); row.add_child(hour_box)
	var activity := LineEdit.new(); activity.name = "Activity"; activity.placeholder_text = "activity"; activity.text = str(source.get("activity", "")); activity.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(activity); activity.text_changed.connect(func(_text): _mark_dirty()); row.add_child(activity)
	var slot := LineEdit.new(); slot.name = "Slot"; slot.placeholder_text = "location slot"; slot.text = str(source.get("slot", "")); slot.custom_minimum_size.x = 130
	InspectorStyle.apply_input_style(slot); slot.text_changed.connect(func(_text): _mark_dirty()); row.add_child(slot)
	var aggressive := CheckBox.new(); aggressive.name = "Aggressive"; aggressive.text = "Aggressive"; aggressive.tooltip_text = "Temporarily use the engine-supported aggressive behavior override."
	aggressive.button_pressed = str(source.get("behavior_override", "")) == "aggressive"; aggressive.toggled.connect(func(_value): _mark_dirty()); row.add_child(aggressive)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove activity"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): _remove_row(row); _mark_dirty()); row.add_child(remove)


func _npc_schedules() -> Dictionary:
	var out := npc_schedule_baseline.duplicate(true)
	var excluded := _split(npc_schedule_excluded.text)
	if excluded.is_empty(): out.erase("excluded_name_keywords")
	else: out["excluded_name_keywords"] = excluded
	var categories := {}
	for row in npc_schedule_categories.get_children():
		if not (row is HBoxContainer): continue
		var category_id := (row.get_node("CategoryId") as LineEdit).text.strip_edges()
		if category_id != "": categories[category_id] = _split((row.get_node("Keywords") as LineEdit).text)
	if categories.is_empty(): out.erase("room_categories")
	else: out["room_categories"] = categories
	var roles: Array = []
	for card in npc_schedule_roles.get_children():
		if not (card is VBoxContainer) or card.name != "ScheduleRole": continue
		var role_id := (card.get_node("Identity/RoleId") as LineEdit).text.strip_edges()
		if role_id == "": continue
		var role: Dictionary = card.get_meta("source").duplicate(true)
		role["id"] = role_id
		role["template_keywords"] = _split((card.get_node("Identity/TemplateKeywords") as LineEdit).text)
		var slots := {}
		for row in (card.get_node("Slots") as VBoxContainer).get_children():
			if not (row is HBoxContainer): continue
			var slot_id := (row.get_node("SlotId") as LineEdit).text.strip_edges()
			if slot_id == "": continue
			var slot: Dictionary = row.get_meta("source").duplicate(true)
			var slot_type := (row.get_node("SlotType") as OptionButton).get_item_text((row.get_node("SlotType") as OptionButton).selected)
			slot["type"] = slot_type
			var subject := (row.get_node("Subject") as LineEdit).text.strip_edges()
			if slot_type == "property_or_self":
				slot["property"] = subject; slot.erase("categories"); slot.erase("exclude"); slot.erase("fallback")
			elif slot_type == "category":
				slot["categories"] = _split(subject); slot.erase("property")
				for pair in [["Exclude", "exclude"], ["Fallback", "fallback"]]:
					var value := (row.get_node(pair[0]) as LineEdit).text.strip_edges()
					if value == "": slot.erase(pair[1])
					else: slot[pair[1]] = value
			else:
				slot.erase("property"); slot.erase("categories"); slot.erase("exclude"); slot.erase("fallback")
			slots[slot_id] = slot
		role["location_slots"] = slots
		var activities := {}
		for row in (card.get_node("Activities") as VBoxContainer).get_children():
			if not (row is HBoxContainer): continue
			var entry: Dictionary = row.get_meta("source").duplicate(true)
			entry["activity"] = (row.get_node("Activity") as LineEdit).text.strip_edges()
			entry["slot"] = (row.get_node("Slot") as LineEdit).text.strip_edges()
			if (row.get_node("Aggressive") as CheckBox).button_pressed: entry["behavior_override"] = "aggressive"
			else: entry.erase("behavior_override")
			activities[str(int((row.get_node("Hour") as SpinBox).value))] = entry
		role["schedule"] = activities
		roles.append(role)
	if roles.is_empty(): out.erase("roles")
	else: out["roles"] = roles
	return out


func _npc_schedules_changed() -> bool:
	return JSON.stringify(_npc_schedules()) != JSON.stringify(npc_schedule_baseline)


func _ensure_schedule_empty_hints():
	if npc_schedule_categories.get_child_count() == 0:
		npc_schedule_categories.add_child(InspectorStyle.lbl("No categories. Add a category to match room-name keywords.", InspectorStyle.COLOR_TEXT_DIM))
	if npc_schedule_roles.get_child_count() == 0:
		npc_schedule_roles.add_child(InspectorStyle.lbl("No scheduled roles. NPCs can still use explicit schedules on their templates.", InspectorStyle.COLOR_TEXT_DIM))

# `weather.descriptions` (flat topic-like map) and `weather.profiles.<id>.map`/
# `.travel_notes` (`weather_manager.py::effective_weather`/`travel_note`;
# `information.py`'s `weather` command). Weather-type keys are this ruleset's
# own vocabulary, so both are string maps rather than pickers over a closed
# list -- the same generic row shared by every string-map field here.
func _add_string_map_row(rows: VBoxContainer, key: String, value: String, key_placeholder: String, value_placeholder: String):
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var key_field := LineEdit.new(); key_field.text = key; key_field.placeholder_text = key_placeholder
	key_field.custom_minimum_size.x = 130; InspectorStyle.apply_input_style(key_field)
	key_field.text_changed.connect(func(_t): _mark_dirty())
	row.add_child(key_field)
	var value_field := LineEdit.new(); value_field.text = value; value_field.placeholder_text = value_placeholder
	value_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(value_field)
	value_field.text_changed.connect(func(_t): _mark_dirty())
	row.add_child(value_field)
	var remove := Button.new(); remove.text = "×"; remove.pressed.connect(func(): _remove_row(row); _mark_dirty())
	row.add_child(remove)
	rows.add_child(row)


func _load_string_map_rows(rows: VBoxContainer, source: Dictionary, key_placeholder: String, value_placeholder: String):
	for child in rows.get_children(): _remove_row(child)
	var keys: Array = source.keys(); keys.sort()
	for key in keys: _add_string_map_row(rows, str(key), str(source[key]), key_placeholder, value_placeholder)


func _read_string_map_rows(rows: VBoxContainer) -> Dictionary:
	var out := {}
	for row in rows.get_children():
		if not (row is HBoxContainer) or row.get_child_count() < 3: continue
		var key := str(row.get_child(0).text).strip_edges()
		if key == "": continue
		out[key] = str(row.get_child(1).text)
	return out


func _load_weather_section():
	var weather: Dictionary = draft.data.get("weather", {}) if draft.data.get("weather", {}) is Dictionary else {}
	var descriptions: Dictionary = weather.get("descriptions", {}) if weather.get("descriptions", {}) is Dictionary else {}
	weather_description_baseline = descriptions.duplicate(true)
	_load_string_map_rows(weather_description_rows, descriptions, "weather type", "flavor text")
	for child in weather_profile_rows.get_children(): _remove_row(child)
	var profiles: Dictionary = weather.get("profiles", {}) if weather.get("profiles", {}) is Dictionary else {}
	weather_profile_baseline = profiles.duplicate(true)
	for profile_id in profiles:
		if profiles[profile_id] is Dictionary: _add_weather_profile_row(str(profile_id), profiles[profile_id].duplicate(true))


func _weather_descriptions() -> Dictionary:
	return _read_string_map_rows(weather_description_rows)


func _weather_descriptions_changed() -> bool:
	return JSON.stringify(_weather_descriptions()) != JSON.stringify(weather_description_baseline)


## One card per profile: its id, a `map` string-map and a `travel_notes`
## string-map. The two sub-lists are found by name rather than child index, so
## a card built at load time and one built fresh by "+ Profile" are read back
## identically.
func _add_weather_profile_row(profile_id: String, profile: Dictionary):
	var card := InspectorStyle.create_card(); var vbox: VBoxContainer = card.get_child(0).get_child(0)
	# A profile that authored an explicit empty `map`/`travel_notes` (fantasy_
	# frontier's "underground" does exactly this) must keep that key on an
	# untouched save; a card built fresh by "+ Profile" should not gain one it
	# was never given. The read alone cannot tell those apart once both are ""
	# empty, so the fact of having started with the key is remembered here.
	card.set_meta("had_map", profile.has("map"))
	card.set_meta("had_travel_notes", profile.has("travel_notes"))
	weather_profile_rows.add_child(card)

	var id_row := HBoxContainer.new(); id_row.add_theme_constant_override("separation", 6)
	id_row.add_child(InspectorStyle.lbl("Profile ID", InspectorStyle.COLOR_TEXT_DIM))
	var id_field := LineEdit.new(); id_field.name = "ProfileId"; id_field.text = profile_id
	id_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(id_field)
	id_field.text_changed.connect(func(_t): _mark_dirty())
	id_row.add_child(id_field)
	var remove_profile := Button.new(); remove_profile.text = "Remove Profile"
	remove_profile.pressed.connect(func(): _remove_row(card); _mark_dirty())
	id_row.add_child(remove_profile)
	vbox.add_child(id_row)

	vbox.add_child(InspectorStyle.lbl("Map (global weather -> local expression)", InspectorStyle.COLOR_TEXT_DIM))
	var map_rows := VBoxContainer.new(); map_rows.name = "MapRows"; map_rows.add_theme_constant_override("separation", 4); vbox.add_child(map_rows)
	var add_map := Button.new(); add_map.text = "+ Mapping"; InspectorStyle.apply_button_style(add_map, InspectorStyle.COLOR_SUCCESS)
	add_map.pressed.connect(func(): _add_string_map_row(map_rows, "", "", "global type", "local type"); _mark_dirty())
	vbox.add_child(add_map)
	_load_string_map_rows(map_rows, profile.get("map", {}) if profile.get("map", {}) is Dictionary else {}, "global type", "local type")

	vbox.add_child(InspectorStyle.lbl("Travel notes", InspectorStyle.COLOR_TEXT_DIM))
	var note_rows := VBoxContainer.new(); note_rows.name = "TravelNoteRows"; note_rows.add_theme_constant_override("separation", 4); vbox.add_child(note_rows)
	var add_note := Button.new(); add_note.text = "+ Travel Note"; InspectorStyle.apply_button_style(add_note, InspectorStyle.COLOR_SUCCESS)
	add_note.pressed.connect(func(): _add_string_map_row(note_rows, "", "", "weather type", "advisory text"); _mark_dirty())
	vbox.add_child(add_note)
	_load_string_map_rows(note_rows, profile.get("travel_notes", {}) if profile.get("travel_notes", {}) is Dictionary else {}, "weather type", "advisory text")


func _weather_profiles() -> Dictionary:
	var out := {}
	for card in weather_profile_rows.get_children():
		var id_field: LineEdit = card.find_child("ProfileId", true, false)
		if id_field == null: continue
		var profile_id := id_field.text.strip_edges()
		if profile_id == "": continue
		var map_rows: VBoxContainer = card.find_child("MapRows", true, false)
		var note_rows: VBoxContainer = card.find_child("TravelNoteRows", true, false)
		var profile := {}
		var map := _read_string_map_rows(map_rows)
		var notes := _read_string_map_rows(note_rows)
		if not map.is_empty() or bool(card.get_meta("had_map", false)): profile["map"] = map
		if not notes.is_empty() or bool(card.get_meta("had_travel_notes", false)): profile["travel_notes"] = notes
		out[profile_id] = profile
	return out


func _weather_profiles_changed() -> bool:
	return JSON.stringify(_weather_profiles()) != JSON.stringify(weather_profile_baseline)


func _mark_dirty():
	if loading or draft == null: return
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved ruleset changes." if form_dirty else "No unsaved changes."; status_label.modulate = Color("f2cf74")
