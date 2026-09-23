# scripts/ui/modals/QuestGenerationSection.gd
#
# The ruleset's `quest_generation` section (`quests/manager.py`,
# `quest_generation/generator.py`, `objectives.py`, `text.py`,
# `commands/interaction/npcs.py`; validated by `content_set.py::
# _validate_ruleset_references`). Every key is optional and the engine falls
# back to `config_quests.py` defaults, so a field left empty is removed rather
# than written -- except where the file already authored that empty value.
#
# Composed from a copy of the loaded section: keys this form does not know
# (future policy, comments) and extra fields on an authored board entry
# survive an edit untouched.

class_name QuestGenerationSection
extends RefCounted

const TEXT_TYPES := ["kill", "fetch", "deliver"]
const INSTANCE_FIELDS := [
	["entry_exit_command", "Entry exit command", "e.g. enter"],
	["entry_description_when_visible", "Entry description", "shown in the room while the entrance exists"],
	["title_pattern", "Title pattern", "only {creature_name} is filled in"],
	["description_pattern", "Description pattern", "only {creature_name} is filled in"],
	["default_procedural_theme", "Default procedural theme", "region generator theme id"],
]

var on_change: Callable
var database: DatabaseManager
var baseline: Dictionary = {}
var room_refs: Array = []

var board_name: LineEdit
var turn_in: LineEdit
var delivery_item: OptionButton
var location_rows: VBoxContainer
var authored_rows: VBoxContainer
var interest_rows: VBoxContainer
var naming_adjectives: LineEdit
var naming_nouns: LineEdit
var naming_pattern: LineEdit
var naming_base: OptionButton
var instance_fields: Dictionary = {}
var text_fields: Dictionary = {}


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("Quest Generation"))
	_hint(box, "Board policy and procedural quest wording. Every field is optional; an empty one falls back to the engine default.")
	board_name = _line(box, "Board display name", "Quest Board")
	turn_in = _line(box, "Turn-in phrases (comma-separated)", "complete, turn in")
	turn_in.tooltip_text = "Typed after 'talk <npc>', these turn a quest in instead of asking about a topic. Matched lower-case."
	delivery_item = _picker_row(box, "Delivery package item")

	var locations := _list_header(box, "Board locations", "+ Location", func(): _add_location_row(""); _changed())
	location_rows = locations
	_hint(box, "Rooms that show the quest board. With none, the board stands in the start room.")

	authored_rows = _list_header(box, "Authored board notices", "+ Notice", func(): _add_authored_row({}); _changed())
	_hint(box, "Quest templates posted to the board before procedural work. A repeatable notice reposts after a hidden delay; its text explains the absence in-world.")

	interest_rows = _list_header(box, "NPC quest interests", "+ Interest", func(): _add_interest_row("", []); _changed())
	_hint(box, "Fallback for templates without properties.quest_interests. An NPC offers procedural kill/fetch/deliver work only for types listed here.")

	box.add_child(InspectorStyle.lbl("Procedural item naming", InspectorStyle.COLOR_TEXT_DIM))
	naming_adjectives = _line(box, "Adjectives (comma-separated)", "")
	naming_nouns = _line(box, "Nouns (comma-separated)", "")
	naming_pattern = _line(box, "Name pattern", "{Adjective} {Noun}")
	naming_pattern.tooltip_text = "Only {Adjective} and {Noun} are filled in."
	naming_base = _picker_row(box, "Base item template")

	box.add_child(InspectorStyle.lbl("Instance quests", InspectorStyle.COLOR_TEXT_DIM))
	for spec in INSTANCE_FIELDS:
		instance_fields[spec[0]] = _line(box, spec[1], spec[2])

	box.add_child(InspectorStyle.lbl("Generated quest text", InspectorStyle.COLOR_TEXT_DIM))
	_hint(box, "Placeholders: " + " ".join(RulesetDraft.QUEST_TEXT_FIELDS.map(func(field): return "{%s}" % field)))
	for quest_type in TEXT_TYPES:
		text_fields["%s.title" % quest_type] = _line(box, "%s title" % quest_type.capitalize(), "")
		text_fields["%s.description" % quest_type] = _line(box, "%s description" % quest_type.capitalize(), "")


func load(section: Dictionary, db: DatabaseManager) -> void:
	database = db
	baseline = section.duplicate(true)
	room_refs = _scan_room_refs()
	board_name.text = str(section.get("board_display_name", ""))
	turn_in.text = _joined(section.get("turn_in_phrases", []))
	_fill_picker(delivery_item, _item_ids(), _item_labels(), str(section.get("delivery_package_item_id", "")), "Engine default")
	_clear(location_rows)
	for location in _array(section.get("quest_board_locations", [])): _add_location_row(str(location))
	_clear(authored_rows)
	for entry in _array(section.get("authored_board_templates", [])):
		if entry is Dictionary: _add_authored_row(entry)
	_clear(interest_rows)
	var interests: Dictionary = _dict(section.get("npc_quest_interests", {}))
	for template_id in interests: _add_interest_row(str(template_id), _array(interests[template_id]))
	var naming: Dictionary = _dict(section.get("procedural_naming", {}))
	naming_adjectives.text = _joined(naming.get("adjectives", []))
	naming_nouns.text = _joined(naming.get("nouns", []))
	naming_pattern.text = str(naming.get("default_name_pattern", ""))
	_fill_picker(naming_base, _item_ids(), _item_labels(), str(naming.get("default_base_template_id", "")), "No base item")
	var instance: Dictionary = _dict(section.get("instance_quest", {}))
	for key in instance_fields: instance_fields[key].text = str(instance.get(key, ""))
	var templates: Dictionary = _dict(section.get("text_templates", {}))
	for quest_type in TEXT_TYPES:
		var template: Dictionary = _dict(templates.get(quest_type, {}))
		text_fields["%s.title" % quest_type].text = str(template.get("title", ""))
		text_fields["%s.description" % quest_type].text = str(template.get("description", ""))


func compose() -> Dictionary:
	var out := baseline.duplicate(true)
	_put(out, baseline, "board_display_name", board_name.text.strip_edges())
	_put(out, baseline, "turn_in_phrases", _split(turn_in.text))
	_put(out, baseline, "delivery_package_item_id", _picked(delivery_item))

	var locations: Array = []
	for row in location_rows.get_children():
		if row is HBoxContainer:
			var ref := _picked(row.get_node("Room"))
			if ref != "": locations.append(ref)
	_put(out, baseline, "quest_board_locations", locations)

	var notices: Array = []
	for card in authored_rows.get_children():
		if card is VBoxContainer and card.name.begins_with("Notice"):
			var notice := _read_authored(card)
			if not notice.is_empty(): notices.append(notice)
	_put(out, baseline, "authored_board_templates", notices)

	var interests := {}
	for row in interest_rows.get_children():
		if not (row is HBoxContainer): continue
		var template_id := _picked(row.get_node("Npc"))
		if template_id != "": interests[template_id] = _split((row.get_node("Tags") as LineEdit).text)
	_put(out, baseline, "npc_quest_interests", interests)

	var naming_base_dict: Dictionary = _dict(baseline.get("procedural_naming", {}))
	var naming := naming_base_dict.duplicate(true)
	_put(naming, naming_base_dict, "adjectives", _split(naming_adjectives.text))
	_put(naming, naming_base_dict, "nouns", _split(naming_nouns.text))
	_put(naming, naming_base_dict, "default_name_pattern", naming_pattern.text.strip_edges())
	_put(naming, naming_base_dict, "default_base_template_id", _picked(naming_base))
	_put(out, baseline, "procedural_naming", naming)

	var instance_base: Dictionary = _dict(baseline.get("instance_quest", {}))
	var instance := instance_base.duplicate(true)
	for key in instance_fields: _put(instance, instance_base, key, (instance_fields[key] as LineEdit).text.strip_edges())
	_put(out, baseline, "instance_quest", instance)

	var templates_base: Dictionary = _dict(baseline.get("text_templates", {}))
	var templates := templates_base.duplicate(true)
	for quest_type in TEXT_TYPES:
		var type_base: Dictionary = _dict(templates_base.get(quest_type, {}))
		var template := type_base.duplicate(true)
		_put(template, type_base, "title", (text_fields["%s.title" % quest_type] as LineEdit).text.strip_edges())
		_put(template, type_base, "description", (text_fields["%s.description" % quest_type] as LineEdit).text.strip_edges())
		_put(templates, templates_base, quest_type, template)
	_put(out, baseline, "text_templates", templates)
	return out


func changed() -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(compose())) != JSON.stringify(SaveIO._normalize_numbers(baseline))


# --- rows -------------------------------------------------------------------

func _add_location_row(ref: String) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new(); picker.name = "Room"; picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_fill_picker(picker, room_refs, {}, ref, "Choose room")
	InspectorStyle.apply_button_style(picker); picker.item_selected.connect(func(index): picker.select(index); _changed()); row.add_child(picker)
	row.add_child(_remove_button(row))
	location_rows.add_child(row)


func _add_interest_row(template_id: String, tags: Array) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var picker := OptionButton.new(); picker.name = "Npc"; picker.custom_minimum_size.x = 200
	_fill_picker(picker, _npc_ids(), _npc_labels(), template_id, "Choose NPC template")
	InspectorStyle.apply_button_style(picker); picker.item_selected.connect(func(index): picker.select(index); _changed()); row.add_child(picker)
	var tag_field := LineEdit.new(); tag_field.name = "Tags"; tag_field.text = _joined(tags); tag_field.placeholder_text = "kill, fetch, deliver, ..."
	tag_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(tag_field)
	tag_field.text_changed.connect(func(_t): _changed()); row.add_child(tag_field)
	row.add_child(_remove_button(row))
	interest_rows.add_child(row)


func _add_authored_row(source: Dictionary) -> void:
	var card := VBoxContainer.new(); card.name = "Notice%d" % authored_rows.get_child_count()
	card.add_theme_constant_override("separation", 4); card.set_meta("source", source.duplicate(true))
	var head := HBoxContainer.new(); head.name = "Head"; head.add_theme_constant_override("separation", 6); card.add_child(head)
	var quest := OptionButton.new(); quest.name = "Quest"; quest.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_fill_picker(quest, _quest_ids(), {}, str(source.get("template_id", "")), "Choose quest template")
	InspectorStyle.apply_button_style(quest); quest.item_selected.connect(func(index): quest.select(index); _changed()); head.add_child(quest)
	var giver := OptionButton.new(); giver.name = "Giver"; giver.custom_minimum_size.x = 190
	_fill_picker(giver, _npc_ids(), _npc_labels(), str(source.get("giver_template_id", "")), "No giver (board)")
	InspectorStyle.apply_button_style(giver); giver.item_selected.connect(func(index): giver.select(index); _changed()); head.add_child(giver)
	head.add_child(InspectorStyle.lbl("Min. relationship", InspectorStyle.COLOR_TEXT_DIM))
	var relationship := SpinBox.new(); relationship.name = "Relationship"; relationship.min_value = 0; relationship.max_value = 100; relationship.step = 1
	relationship.value = float(source.get("relationship_min", 0)); relationship.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(relationship)
	relationship.value_changed.connect(func(_v): _changed()); head.add_child(relationship)
	head.add_child(_remove_button(card))

	var repeat_policy: Dictionary = _dict(source.get("repeatable", {}))
	var repeat := HBoxContainer.new(); repeat.name = "Repeat"; repeat.add_theme_constant_override("separation", 6); card.add_child(repeat)
	var repeatable := CheckBox.new(); repeatable.name = "Repeatable"; repeatable.text = "Repeatable, after (s)"; repeatable.button_pressed = source.get("repeatable") is Dictionary
	repeatable.toggled.connect(func(_v): _changed()); repeat.add_child(repeatable)
	var delay := SpinBox.new(); delay.name = "Delay"; delay.min_value = 1; delay.max_value = 604800; delay.step = 1
	delay.value = float(repeat_policy.get("delay_seconds", 1800)); delay.custom_minimum_size.x = 90; InspectorStyle.apply_input_style(delay)
	delay.value_changed.connect(func(_v): _changed()); repeat.add_child(delay)
	var unavailable := LineEdit.new(); unavailable.name = "Unavailable"; unavailable.text = str(repeat_policy.get("unavailable_text", ""))
	unavailable.placeholder_text = "in-world reason the notice is down"; unavailable.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	InspectorStyle.apply_input_style(unavailable); unavailable.text_changed.connect(func(_t): _changed()); repeat.add_child(unavailable)
	authored_rows.add_child(card)


func _read_authored(card: VBoxContainer) -> Dictionary:
	var source: Dictionary = card.get_meta("source", {})
	var template_id := _picked(card.get_node("Head/Quest"))
	if template_id == "": return {}
	var entry := source.duplicate(true)
	entry["template_id"] = template_id
	var giver := _picked(card.get_node("Head/Giver"))
	if giver == "": entry.erase("giver_template_id")
	else: entry["giver_template_id"] = giver
	var relationship := int((card.get_node("Head/Relationship") as SpinBox).value)
	if relationship > 0 or source.has("relationship_min"): entry["relationship_min"] = relationship
	else: entry.erase("relationship_min")
	if (card.get_node("Repeat/Repeatable") as CheckBox).button_pressed:
		var policy: Dictionary = _dict(source.get("repeatable", {})).duplicate(true)
		policy["delay_seconds"] = int((card.get_node("Repeat/Delay") as SpinBox).value)
		policy["unavailable_text"] = (card.get_node("Repeat/Unavailable") as LineEdit).text.strip_edges()
		entry["repeatable"] = policy
	else:
		entry.erase("repeatable")
	return entry


# --- helpers ----------------------------------------------------------------

## Sets `key` unless `value` is empty; an empty value is removed, except when
## the source already authored that same empty value (kept, so an untouched
## section round-trips exactly).
static func _put(out: Dictionary, source: Dictionary, key: String, value) -> void:
	if _is_empty(value):
		if source.has(key) and _is_empty(source[key]): out[key] = source[key]
		else: out.erase(key)
	else:
		out[key] = value


static func _is_empty(value) -> bool:
	if value is String or value is Array or value is Dictionary: return value.is_empty()
	return value == null


func _scan_room_refs() -> Array:
	var refs: Array = []
	var dir_path := DataRoot.content_dir("regions")
	var dir := DirAccess.open(dir_path)
	if dir == null: return refs
	var files: Array = []
	for file_name in dir.get_files():
		if file_name.ends_with(".json"): files.append(file_name)
	files.sort()
	for file_name in files:
		var region = JSON.parse_string(FileAccess.get_file_as_string(dir_path.path_join(file_name)))
		if not (region is Dictionary) or region.get("themes") is Dictionary: continue
		var region_id := str(region.get("region_id", file_name.get_basename())).strip_edges()
		var rooms = region.get("rooms", {})
		if region_id == "" or not (rooms is Dictionary): continue
		for room_id in rooms: refs.append("%s:%s" % [region_id, str(room_id)])
	return refs


func _item_ids() -> Array: return database.get_item_ids() if database != null else []
func _npc_ids() -> Array: return database.get_npc_ids() if database != null else []
func _quest_ids() -> Array: return database.get_ids("quest") if database != null else []


func _item_labels() -> Dictionary:
	var labels := {}
	for item_id in _item_ids():
		if database.items.get(item_id) is Dictionary: labels[item_id] = "%s — %s" % [str(database.items[item_id].get("name", item_id)), item_id]
	return labels


func _npc_labels() -> Dictionary:
	var labels := {}
	for npc_id in _npc_ids():
		if database.npcs.get(npc_id) is Dictionary: labels[npc_id] = "%s — %s" % [str(database.npcs[npc_id].get("name", npc_id)), npc_id]
	return labels


## Index 0 is the empty choice; an authored id the picker does not know is kept
## as a visible "Missing:" entry rather than silently dropped.
static func _fill_picker(picker: OptionButton, ids: Array, labels: Dictionary, selected_id: String, empty_label: String) -> void:
	picker.clear(); picker.add_item(empty_label); picker.set_item_metadata(0, "")
	for id in ids:
		picker.add_item(str(labels.get(id, id))); picker.set_item_metadata(picker.item_count - 1, str(id))
		if str(id) == selected_id: picker.select(picker.item_count - 1)
	if selected_id != "" and picker.selected == 0:
		picker.add_item("Missing: " + selected_id); picker.set_item_metadata(picker.item_count - 1, selected_id); picker.select(picker.item_count - 1)


static func _picked(picker: OptionButton) -> String:
	return str(picker.get_item_metadata(picker.selected)) if picker.selected >= 0 else ""


func _line(box: VBoxContainer, label: String, placeholder: String) -> LineEdit:
	var row := VBoxContainer.new(); row.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var field := LineEdit.new(); field.placeholder_text = placeholder; InspectorStyle.apply_input_style(field)
	field.text_changed.connect(func(_t): _changed()); row.add_child(field); box.add_child(row)
	return field


func _picker_row(box: VBoxContainer, label: String) -> OptionButton:
	var row := HBoxContainer.new(); row.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var picker := OptionButton.new(); picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_button_style(picker)
	picker.item_selected.connect(func(index): picker.select(index); _changed()); row.add_child(picker); box.add_child(row)
	return picker


func _list_header(box: VBoxContainer, label: String, button_text: String, on_add: Callable) -> VBoxContainer:
	var header := HBoxContainer.new(); header.add_child(InspectorStyle.lbl(label, InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.text = button_text; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS); add.pressed.connect(on_add); header.add_child(add)
	box.add_child(header)
	var rows := VBoxContainer.new(); rows.add_theme_constant_override("separation", 5); box.add_child(rows)
	return rows


func _remove_button(row: Control) -> Button:
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): row.get_parent().remove_child(row); row.queue_free(); _changed())
	return remove


func _hint(box: VBoxContainer, text: String) -> void:
	var label := InspectorStyle.lbl(text, InspectorStyle.COLOR_TEXT_DIM); label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(label)


func _clear(rows: VBoxContainer) -> void:
	for child in rows.get_children(): rows.remove_child(child); child.queue_free()


func _changed() -> void:
	if on_change.is_valid(): on_change.call()


static func _split(text: String) -> Array:
	if text.strip_edges() == "": return []
	var out: Array = []
	for value in text.split(","):
		var trimmed := value.strip_edges()
		if trimmed != "": out.append(trimmed)
	return out


static func _joined(value) -> String: return ", ".join(value) if value is Array else ""
static func _array(value) -> Array: return value if value is Array else []
static func _dict(value) -> Dictionary: return value if value is Dictionary else {}
