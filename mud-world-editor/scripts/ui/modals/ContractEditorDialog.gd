# Configuration form over the contract sections. Drafts preserve unowned values;
# the engine validates a staged set before a configuration file is replaced.
class_name ContractEditorDialog
extends "res://scripts/ui/modals/ConfigurationDialog.gd"

signal contracts_saved

const ITEM_CLASSES := ["Item", "Weapon", "Armor", "Consumable", "Container", "Key", "Lockpick", "ResourceNode", "Interactive", "Gem", "Junk", "Treasure"]
const RESOURCE_KINDS := ["vital", "ability", "currency", "other"]
const STAT_ROLES := ["health", "attack", "defence", "evasion", "regeneration", "power", "ability_power", "resistance"]

var draft: ContractDraft
var status_label: Label
var resource_rows: VBoxContainer
var family_rows: VBoxContainer
var profile_rows: VBoxContainer
var attack_rows: VBoxContainer
var defense_rows: VBoxContainer
var ability_rows: VBoxContainer
var effect_rows: VBoxContainer
var work_rows: VBoxContainer
var stats_order: LineEdit
var stats_short: LineEdit
var stat_role_inputs: Dictionary = {}
var form_dirty := false
var loading := false

func setup():
	_install_guard()
	title = "Contract Editor"
	min_size = Vector2i(960, 650)
	ok_button_text = "Save Contract Changes"
	confirmed.connect(_save)
	var root := VBoxContainer.new(); root.custom_minimum_size = Vector2(920, 560); root.add_theme_constant_override("separation", 10); add_child(root)
	status_label = Label.new(); status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM; root.add_child(status_label)
	var tabs := TabContainer.new(); tabs.size_flags_vertical = Control.SIZE_EXPAND_FILL; root.add_child(tabs)
	resource_rows = _make_section(tabs, "Resources", "Resources define named pools such as health, charge, or a setting-specific equivalent.", "+ Add Resource", func(): _add_resource_row({}))
	family_rows = _make_section(tabs, "Item Families", "Families pair engine item behavior with content-facing capabilities and a default generation profile.", "+ Add Item Family", func(): _add_family_row({}))
	profile_rows = _make_section(tabs, "Generation Profiles", "Profiles define named distributions. Their tiers can describe gems, salvage, gear quality, or any other generated family.", "+ Add Generation Profile", func(): _add_profile_row({}))
	attack_rows = _make_section(tabs, "Attack Profiles", "Attack profiles describe a damage channel, optional material interaction, and the cost of using it.", "+ Add Attack Profile", func(): _add_attack_row({}))
	defense_rows = _make_section(tabs, "Defense Profiles", "Defense profiles keep protection, material, and per-channel resistance together.", "+ Add Defense Profile", func(): _add_defense_row({}))
	effect_rows = _make_section(tabs, "Effect Packets", "Effect packets describe an outcome independently of fantasy or sci-fi vocabulary.", "+ Add Effect Packet", func(): _add_effect_row({}))
	ability_rows = _make_section(tabs, "Abilities", "Abilities bind a target, cost, cooldown, and effect packet into a reusable action.", "+ Add Ability", func(): _add_ability_row({}))
	work_rows = _make_section(tabs, "Work", "Work declarations describe actions that take time: inputs, outputs, a station, and an optional skill gate.", "+ Add Work", func(): _add_work_row({}))
	_make_stats_page(tabs)
	DialogStyle.style_window(self)
	get_ok_button().custom_minimum_size = Vector2(300, 40)
	get_ok_button().disabled = true

func open_active():
	if visible: return
	draft = null
	_form_baseline.clear()
	var result := ContractDraft.load(DataRoot.root().path_join(ContractCatalog.RELATIVE_PATH))
	if not result.get("ok", false):
		status_label.text = str(result.get("error", "Could not load contracts.")); status_label.modulate = DialogStyle.COLOR_DANGER; get_ok_button().disabled = true; popup_centered(); return
	draft = result["draft"]; loading = true
	_clear_rows(resource_rows); _clear_rows(family_rows); _clear_rows(profile_rows); _clear_rows(attack_rows); _clear_rows(defense_rows); _clear_rows(effect_rows); _clear_rows(ability_rows); _clear_rows(work_rows)
	var resources: Array = draft.data.get("resources", []) if draft.data.get("resources", []) is Array else []
	var families: Array = draft.data.get("item_families", []) if draft.data.get("item_families", []) is Array else []
	var profiles: Array = draft.data.get("generation_profiles", []) if draft.data.get("generation_profiles", []) is Array else []
	var attacks: Array = draft.data.get("attack_profiles", []) if draft.data.get("attack_profiles", []) is Array else []
	var defenses: Array = draft.data.get("defense_profiles", []) if draft.data.get("defense_profiles", []) is Array else []
	var effects: Array = draft.data.get("effect_packets", []) if draft.data.get("effect_packets", []) is Array else []
	var abilities: Array = draft.data.get("abilities", []) if draft.data.get("abilities", []) is Array else []
	var work: Array = draft.data.get("work", []) if draft.data.get("work", []) is Array else []
	for entry in resources:
		if entry is Dictionary: _add_resource_row(entry)
	for entry in families:
		if entry is Dictionary: _add_family_row(entry)
	for entry in profiles:
		if entry is Dictionary: _add_profile_row(entry)
	for entry in attacks:
		if entry is Dictionary: _add_attack_row(entry)
	for entry in defenses:
		if entry is Dictionary: _add_defense_row(entry)
	for entry in effects:
		if entry is Dictionary: _add_effect_row(entry)
	for entry in abilities:
		if entry is Dictionary: _add_ability_row(entry)
	for entry in work:
		if entry is Dictionary: _add_work_row(entry)
	_load_stats(draft.data.get("stats", {}))
	_reset_form_baseline()
	loading = false; form_dirty = false; get_ok_button().disabled = true
	status_label.text = "Editing %s. Other contract sections and unfamiliar fields are preserved unchanged." % draft.path; status_label.modulate = InspectorStyle.COLOR_TEXT_DIM
	popup_centered()

func _make_section(tabs: TabContainer, tab_name: String, hint_text: String, add_text: String, add_action: Callable) -> VBoxContainer:
	var page := VBoxContainer.new(); page.name = tab_name; page.add_theme_constant_override("separation", 8); tabs.add_child(page)
	var hint := Label.new(); hint.text = hint_text; hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; hint.modulate = InspectorStyle.COLOR_TEXT_DIM; page.add_child(hint)
	var scroll := ScrollContainer.new(); scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL; page.add_child(scroll)
	var rows := VBoxContainer.new(); rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL; rows.add_theme_constant_override("separation", 8); scroll.add_child(rows)
	var add := Button.new(); add.text = add_text; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(func(): add_action.call(); _mark_dirty()); page.add_child(add)
	return rows

func _add_resource_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); resource_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Resource", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_field(grid, "Short label", str(entry.get("short", "")), "short")
	_option(grid, "Kind", RESOURCE_KINDS, str(entry.get("kind", "other")), "kind")
	_field(grid, "Maximum stat", str(entry.get("max_stat", "")), "max_stat")
	_field(grid, "Regeneration stat", str(entry.get("regeneration_stat", "")), "regeneration_stat")
	var regenerates := CheckBox.new(); regenerates.text = "Regenerates"; regenerates.button_pressed = bool(entry.get("regenerates", false))
	regenerates.toggled.connect(func(value):
		if value == bool(source.get("regenerates", false)): _restore_owned_value(entry, "regenerates", source)
		else: entry["regenerates"] = value
		_mark_dirty()
	); box.add_child(regenerates)

func _add_family_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); family_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Item Family", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_option(grid, "Engine class", ITEM_CLASSES, str(entry.get("item_class", "Item")), "item_class")
	_field(grid, "Default profile", str(entry.get("generation_profile", "")), "generation_profile")
	_field(grid, "Capabilities (comma-separated)", _join(entry.get("capabilities", [])), "capabilities")
	_field(grid, "Icon style", str(entry.get("icon_style", "")), "icon_style")
	_field(grid, "Attack profile", str(entry.get("attack_profile", "")), "attack_profile")
	_field(grid, "Defense profile", str(entry.get("defense_profile", "")), "defense_profile")
	_field(grid, "Resource", str(entry.get("resource", "")), "resource")

func _add_profile_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); profile_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Generation Profile", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_family_option(grid, entry)
	_field(grid, "Property prefix", str(entry.get("property_prefix", "")), "property_prefix")
	_field(grid, "Name template", str(entry.get("name_template", "{quality} {size} {base}")), "name_template")
	_number_field(grid, "Size bias", float(entry.get("size_bias", 0.0)), "size_bias")
	_number_field(grid, "Quality bias", float(entry.get("quality_bias", 0.0)), "quality_bias")
	_add_tier_section(box, entry, "rarity_tiers", "Rarity tiers", ["ID", "Rank", "Weight"])
	_add_tier_section(box, entry, "size_tiers", "Size tiers", ["ID", "Label", "Score", "Value ×", "Weight ×"])
	_add_tier_section(box, entry, "quality_tiers", "Quality tiers", ["ID", "Label", "Score", "Value ×"])

func _add_attack_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); attack_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Attack Profile", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_field(grid, "Damage channel", str(entry.get("damage_type", "")), "damage_type")
	_field(grid, "Material interaction", str(entry.get("weapon_damage_type", "")), "weapon_damage_type")
	_number_field(grid, "Damage", float(entry.get("damage", 0.0)), "damage")
	_number_field(grid, "Cooldown", float(entry.get("cooldown", 0.0)), "cooldown")
	_field(grid, "Tags (comma-separated)", _join(entry.get("tags", [])), "tags")
	var cost: Dictionary = entry.get("resource_cost", {}) if entry.get("resource_cost", {}) is Dictionary else {}
	_field(grid, "Cost resource", str(cost.get("resource", "")), "resource_cost.resource")
	_number_field(grid, "Cost amount", float(cost.get("amount", 0.0)), "resource_cost.amount")

func _add_defense_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); defense_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Defense Profile", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_number_field(grid, "Defense", float(entry.get("defense", 0.0)), "defense")
	_field(grid, "Material", str(entry.get("material", "")), "material")
	_field(grid, "Tags (comma-separated)", _join(entry.get("tags", [])), "tags")
	_field(grid, "Resistances (channel=value)", _map_join(entry.get("resistances", {})), "resistances")

func _add_effect_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); effect_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Effect Packet", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_field(grid, "Kind", str(entry.get("kind", "")), "kind")
	_field(grid, "Resource", str(entry.get("resource", "")), "resource")
	_number_field(grid, "Value", float(entry.get("value", 0.0)), "value")
	_number_field(grid, "Duration", float(entry.get("duration", 0.0)), "duration")
	_field(grid, "Tags (comma-separated)", _join(entry.get("tags", [])), "tags")
	_text_area(box, "Description", str(entry.get("description", "")), entry, "description")
	_text_area(box, "Payload (typed JSON object)", JSON.stringify(entry.get("payload", {}), "  "), entry, "payload")

func _add_ability_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); ability_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Ability", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_field(grid, "Effect packet", str(entry.get("effect_packet", "")), "effect_packet")
	_option(grid, "Target", ["self", "ally", "enemy", "room", "item", "area"], str(entry.get("target_type", "enemy")), "target_type")
	var cost: Dictionary = entry.get("cost", {}) if entry.get("cost", {}) is Dictionary else {}
	_field(grid, "Cost resource", str(cost.get("resource", "")), "cost.resource")
	_number_field(grid, "Cost amount", float(cost.get("amount", 0.0)), "cost.amount")
	_number_field(grid, "Cooldown", float(entry.get("cooldown", 0.0)), "cooldown")
	_number_field(grid, "Level required", float(entry.get("level_required", 0.0)), "level_required")
	_text_area(box, "Description", str(entry.get("description", "")), entry, "description")

func _add_work_row(source: Dictionary):
	var entry: Dictionary = source.duplicate(true)
	var card := InspectorStyle.create_card(); var box: VBoxContainer = card.get_child(0).get_child(0); box.set_meta("entry", entry); work_rows.add_child(card)
	var header := HBoxContainer.new(); box.add_child(header)
	var title := InspectorStyle.lbl("Work Declaration", InspectorStyle.COLOR_ACCENT); title.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(title)
	var remove := Button.new(); remove.text = "Remove"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER); remove.pressed.connect(func(): _remove_row(card); _mark_dirty()); header.add_child(remove)
	var grid := GridContainer.new(); grid.columns = 2; box.add_child(grid)
	_field(grid, "ID", str(entry.get("id", "")), "id")
	_field(grid, "Label", str(entry.get("label", "")), "label")
	_number_field(grid, "Duration (days)", float(entry.get("duration_days", 0.0)), "duration_days")
	_field(grid, "Station", str(entry.get("station", "")), "station")
	_field(grid, "Skill", str(entry.get("skill", "")), "skill")
	_number_field(grid, "Difficulty", float(entry.get("difficulty", 0.0)), "difficulty")
	_field(grid, "Inputs (item_id x quantity)", _item_list_join(entry.get("inputs", [])), "inputs")
	_field(grid, "Outputs (item_id x quantity)", _item_list_join(entry.get("outputs", [])), "outputs")
	_field(grid, "Tags (comma-separated)", _join(entry.get("tags", [])), "tags")
	_text_area(box, "Description", str(entry.get("description", "")), entry, "description")

func _make_stats_page(tabs: TabContainer):
	var page := VBoxContainer.new(); page.name = "Stats"; page.add_theme_constant_override("separation", 8); tabs.add_child(page)
	var hint := Label.new(); hint.text = "Stats are the shared vocabulary for this content set. Roles connect generic engine mechanics to the stat names this world uses."; hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; hint.modulate = InspectorStyle.COLOR_TEXT_DIM; page.add_child(hint)
	var order_row := VBoxContainer.new(); order_row.add_child(InspectorStyle.lbl("Display order (comma-separated)", InspectorStyle.COLOR_TEXT_DIM)); stats_order = LineEdit.new(); InspectorStyle.apply_input_style(stats_order); stats_order.text_changed.connect(func(_text): _mark_dirty()); order_row.add_child(stats_order); page.add_child(order_row)
	var short_row := VBoxContainer.new(); short_row.add_child(InspectorStyle.lbl("Short labels (stat=short, comma-separated)", InspectorStyle.COLOR_TEXT_DIM)); stats_short = LineEdit.new(); InspectorStyle.apply_input_style(stats_short); stats_short.text_changed.connect(func(_text): _mark_dirty()); short_row.add_child(stats_short); page.add_child(short_row)
	page.add_child(InspectorStyle.create_sub_header("Engine Roles"))
	var grid := GridContainer.new(); grid.columns = 2; page.add_child(grid)
	for role in STAT_ROLES:
		grid.add_child(InspectorStyle.lbl(role.replace("_", " ").capitalize(), InspectorStyle.COLOR_TEXT_DIM))
		var field := LineEdit.new(); field.placeholder_text = "stat name"; InspectorStyle.apply_input_style(field); field.text_changed.connect(func(_text): _mark_dirty()); grid.add_child(field); stat_role_inputs[role] = field

func _load_stats(value):
	var stats: Dictionary = value if value is Dictionary else {}
	stats_order.text = _join(stats.get("order", [])); stats_short.text = _map_join(stats.get("short", {}))
	var roles: Dictionary = stats.get("roles", {}) if stats.get("roles", {}) is Dictionary else {}
	for role in STAT_ROLES: stat_role_inputs[role].text = str(roles.get(role, ""))

func _family_option(parent: GridContainer, entry: Dictionary):
	var wanted := str(entry.get("item_family", ""))
	var ids := _family_ids()
	if not ids.has(wanted): ids.push_front(wanted)
	_option(parent, "Item family", ids, wanted, "item_family")

func _add_tier_section(parent: VBoxContainer, entry: Dictionary, key: String, label_text: String, columns: Array):
	parent.add_child(InspectorStyle.create_sub_header(label_text))
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 4); rows.set_meta("tiers", entry.get(key, []).duplicate(true) if entry.get(key, []) is Array else []); parent.add_child(rows)
	for tier in rows.get_meta("tiers"):
		if tier is Dictionary: _add_tier_row(rows, entry, key, tier, columns)
	var add := Button.new(); add.text = "+ Add " + label_text.trim_suffix("s"); InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(func(): _add_tier_row(rows, entry, key, {}, columns); _sync_tiers(rows, entry, key); _mark_dirty()); parent.add_child(add)

func _add_tier_row(rows: VBoxContainer, entry: Dictionary, key: String, source: Dictionary, columns: Array):
	var tier: Dictionary = source.duplicate(true); var row := HBoxContainer.new(); row.set_meta("tier", tier); rows.add_child(row)
	for column in columns:
		var field := LineEdit.new(); field.placeholder_text = str(column); field.text = _tier_value(tier, str(column)); field.custom_minimum_size.x = 95; InspectorStyle.apply_input_style(field)
		field.text_changed.connect(func(text):
			var numeric := not str(column) in ["ID", "Label"]
			var valid: bool = text.is_valid_float() and is_finite(float(text)) if numeric else true
			if str(column) in ["Rank", "Score"]: valid = text.is_valid_int()
			field.set_meta("input_error", "" if valid else "Tier %s must be a valid number." % str(column))
			if valid: _set_tier_value(tier, str(column), text)
			_sync_tiers(rows, entry, key); _mark_dirty()
		); row.add_child(field)
	var remove := Button.new(); remove.text = "×"; remove.tooltip_text = "Remove tier"; remove.pressed.connect(func(): _remove_row(row); _sync_tiers(rows, entry, key); _mark_dirty()); row.add_child(remove)


func _tier_value(tier: Dictionary, column: String) -> String:
	var keys := {"ID": "id", "Label": "label", "Rank": "rank", "Score": "score", "Weight": "weight", "Value ×": "value_multiplier", "Weight ×": "weight_multiplier"}
	return str(tier.get(keys.get(column, ""), ""))

func _set_tier_value(tier: Dictionary, column: String, text: String):
	var keys := {"ID": "id", "Label": "label", "Rank": "rank", "Score": "score", "Weight": "weight", "Value ×": "value_multiplier", "Weight ×": "weight_multiplier"}
	var key := str(keys.get(column, "")); var value := text.strip_edges()
	if key in ["rank", "score"]: tier[key] = int(value) if value.is_valid_int() else 0
	elif key in ["weight", "value_multiplier", "weight_multiplier"]: tier[key] = float(value) if value.is_valid_float() else 0.0
	else: tier[key] = value

func _sync_tiers(rows: VBoxContainer, entry: Dictionary, key: String):
	var tiers: Array = []
	for row in rows.get_children():
		var tier: Dictionary = row.get_meta("tier")
		tiers.append(tier)
	entry[key] = tiers

func _family_ids() -> Array:
	var ids: Array = []
	for card in family_rows.get_children():
		var entry: Dictionary = card.get_child(0).get_child(0).get_meta("entry"); var id := str(entry.get("id", "")).strip_edges()
		if id != "": ids.append(id)
	ids.sort(); return ids

func _field(parent: GridContainer, label_text: String, value: String, key: String):
	parent.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); field.text = value; InspectorStyle.apply_input_style(field); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var box: VBoxContainer = parent.get_parent(); var entry: Dictionary = box.get_meta("entry")
	_wire_entry_text(field, entry, key, value)
	parent.add_child(field)

func _number_field(parent: GridContainer, label_text: String, value: float, key: String):
	parent.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); field.text = str(value); field.placeholder_text = "0"; InspectorStyle.apply_input_style(field); field.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var box: VBoxContainer = parent.get_parent(); var entry: Dictionary = box.get_meta("entry")
	_wire_entry_text(field, entry, key, str(value))
	parent.add_child(field)

func _text_area(parent: VBoxContainer, label_text: String, value: String, entry: Dictionary, key: String):
	parent.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var field := TextEdit.new(); field.text = value; field.custom_minimum_size.y = 68; InspectorStyle.apply_input_style(field)
	_wire_entry_text(field, entry, key, value)
	parent.add_child(field)

func _option(parent: GridContainer, label_text: String, options: Array, value: String, key: String):
	parent.add_child(InspectorStyle.lbl(label_text, InspectorStyle.COLOR_TEXT_DIM))
	var choice := OptionButton.new(); var selected := options.find(value)
	for option in options: choice.add_item(str(option))
	if selected < 0: choice.add_item(value); selected = choice.item_count - 1
	choice.select(maxi(0, selected)); InspectorStyle.apply_button_style(choice)
	var box: VBoxContainer = parent.get_parent(); var entry: Dictionary = box.get_meta("entry")
	var saved_entry := entry.duplicate(true)
	choice.item_selected.connect(func(index):
		if choice.get_item_text(index) == value: _restore_owned_value(entry, key, saved_entry)
		else: entry[key] = choice.get_item_text(index)
		_mark_dirty()
	); parent.add_child(choice)

func _save():
	if draft == null: return
	if not _form_changed(): _finish_save(); return
	var errors := _input_errors()
	if not errors.is_empty():
		status_label.text = "\n".join(errors); status_label.modulate = DialogStyle.COLOR_DANGER; return
	draft.data = draft.original.duplicate(true)
	var sections := {"resources": resource_rows, "item_families": family_rows, "generation_profiles": profile_rows,
		"attack_profiles": attack_rows, "defense_profiles": defense_rows, "effect_packets": effect_rows,
		"abilities": ability_rows, "work": work_rows}
	for key in sections:
		var entries := _entries(sections[key])
		if entries != draft.original.get(key, []): draft.data[key] = entries
	var stats_value := _stats_value()
	if stats_value != draft.original.get("stats", {}): draft.set_stats(stats_value)
	var result := draft.save()
	if not result.get("ok", false): status_label.text = str(result.get("error", "Could not save contracts.")); status_label.modulate = DialogStyle.COLOR_DANGER; return
	contracts_saved.emit()
	form_dirty = false; get_ok_button().disabled = true
	_finish_save()

func _entries(rows: VBoxContainer) -> Array:
	var out: Array = []
	for card in rows.get_children():
		var box: VBoxContainer = card.get_child(0).get_child(0); var entry: Dictionary = box.get_meta("entry"); out.append(entry)
	return out

func _clear_rows(rows: VBoxContainer):
	for child in rows.get_children(): _remove_row(child)

func _split(text: String) -> Array:
	var out: Array = []
	for piece in text.split(",", false):
		var cleaned := piece.strip_edges()
		if cleaned != "" and not out.has(cleaned): out.append(cleaned)
	return out

func _join(value) -> String: return ", ".join(value) if value is Array else ""

func _map_join(value) -> String:
	if not (value is Dictionary): return ""
	var parts: Array = []
	for key in value: parts.append("%s=%s" % [str(key), str(value[key])])
	parts.sort(); return ", ".join(parts)

# Parsing is strict: keep the last valid value in the draft while an incomplete
# input is visible, and refuse Save until it is repaired. Never coerce a typo to 0.
func _wire_entry_text(field: Control, entry: Dictionary, key: String, initial: String):
	var original := entry.duplicate(true)
	var changed := func():
		field.set_meta("input_error", "")
		if field.text == initial:
			_restore_owned_value(entry, key, original)
		else:
			var parsed := _parse_field(key, field.text, original)
			if parsed.has("error"): field.set_meta("input_error", str(parsed["error"]))
			else: _put_path(entry, key, parsed["value"])
		_mark_dirty()
	if field is TextEdit: field.text_changed.connect(changed)
	else: field.text_changed.connect(func(_text): changed.call())

func _restore_owned_value(entry: Dictionary, key: String, source: Dictionary):
	var parts := key.split(".")
	if parts.size() == 1:
		if source.has(key): entry[key] = source[key]
		else: entry.erase(key)
	else:
		var section: Dictionary = entry.get(parts[0], {}).duplicate(true)
		var saved: Dictionary = source.get(parts[0], {})
		if saved.has(parts[1]): section[parts[1]] = saved[parts[1]]
		else: section.erase(parts[1])
		if section.is_empty() and not source.has(parts[0]): entry.erase(parts[0])
		else: entry[parts[0]] = section

func _parse_field(key: String, text: String, source: Dictionary = {}) -> Dictionary:
	var cleaned := text.strip_edges()
	if key == "payload":
		var parser := JSON.new()
		if parser.parse(text) != OK or not parser.data is Dictionary:
			return {"error": "Payload must be a valid JSON object (numbers, booleans and nested values are preserved)."}
		return {"value": parser.data}
	if key in ["inputs", "outputs"]: return _parse_items(text, source.get(key, []))
	if key in ["resistances", "short"]: return _parse_map(text, key == "resistances")
	if key in ["level_required", "difficulty"]:
		if not cleaned.is_valid_int(): return {"error": "%s must be a whole number." % key}
		return {"value": int(cleaned)}
	if key in ["damage", "cooldown", "defense", "size_bias", "quality_bias", "value", "duration", "duration_days"] or key.ends_with(".amount"):
		if not cleaned.is_valid_float() or not is_finite(float(cleaned)): return {"error": "%s must be a finite number." % key}
		return {"value": float(cleaned)}
	if key in ["capabilities", "tags"]: return {"value": _split(cleaned)}
	return {"value": cleaned}

func _parse_map(text: String, numeric: bool) -> Dictionary:
	var result := {}
	if text.strip_edges() == "": return {"value": result}
	for part in text.split(",", true):
		var pair := part.split("=", true, 1)
		if pair.size() != 2 or pair[0].strip_edges() == "" or pair[1].strip_edges() == "":
			return {"error": "Use one name=value pair per entry."}
		var key := pair[0].strip_edges(); var value := pair[1].strip_edges()
		if result.has(key): return {"error": "Repeated map key: %s." % key}
		if numeric and (not value.is_valid_float() or not is_finite(float(value))):
			return {"error": "Resistance for %s must be a finite number." % key}
		result[key] = float(value) if numeric else value
	return {"value": result}

func _item_list_join(value) -> String:
	if not value is Array: return ""
	var parts: Array = []
	for entry in value:
		if entry is Dictionary: parts.append("%s x %s" % [str(entry.get("item_id", "")), str(entry.get("quantity", 1))])
	return ", ".join(parts)

func _parse_items(text: String, original: Array) -> Dictionary:
	var result: Array = []
	if text.strip_edges() == "": return {"value": result}
	var seen := {}
	for part in text.split(",", true):
		var pair := part.rsplit(" x ", true, 1)
		if pair.size() != 2 or pair[0].strip_edges() == "" or not pair[1].strip_edges().is_valid_int() or int(pair[1]) <= 0:
			return {"error": "Work items use item_id x quantity; quantity must be a positive whole number."}
		var id := pair[0].strip_edges()
		if seen.has(id): return {"error": "Repeated work item: %s." % id}
		seen[id] = true
		var item := {}
		for existing in original:
			if existing is Dictionary and existing.get("item_id", "") == id: item = existing.duplicate(true); break
		item["item_id"] = id; item["quantity"] = int(pair[1])
		result.append(item)
	return {"value": result}

func _stats_value() -> Dictionary:
	var result: Dictionary = draft.original.get("stats", {}).duplicate(true)
	for role in STAT_ROLES:
		var field: LineEdit = stat_role_inputs[role]
		if _field_changed(field): _put_path(result, "roles." + role, field.text.strip_edges())
	if _field_changed(stats_order): result["order"] = _split(stats_order.text)
	if _field_changed(stats_short):
		var parsed := _parse_map(stats_short.text, false)
		if not parsed.has("error"): result["short"] = parsed["value"]
	return result

func _mark_dirty():
	if loading or draft == null: return
	var parsed := _parse_map(stats_short.text, false)
	stats_short.set_meta("input_error", parsed.get("error", ""))
	form_dirty = _form_changed()
	get_ok_button().disabled = not form_dirty
	status_label.text = "Unsaved contract changes." if form_dirty else "No unsaved changes."
	status_label.modulate = Color("f2cf74")
