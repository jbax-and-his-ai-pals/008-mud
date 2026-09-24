# scripts/ui/modals/SocialSection.gd
#
# The ruleset's `social` section (social/relationships.py, use_give.py
# `_gift_affinity`), validated by content_set.py::_validate_social_rules:
# the relationship ladder (threshold, name, vendor discount) and what a gift
# is worth. Like the other ruleset sections, only what the author changed is
# written; unknown keys survive. A gift category that is not authored shows the
# engine's own default, which is what play uses for it.

class_name SocialSection
extends RefCounted

# [category, label, engine default] -- use_give.py `_gift_affinity`.
const GIFT_CATEGORIES := [
	["ordinary", "Any gift", 1], ["crafted", "A gift the player made", 5],
	["preferred_item", "An item they want", 4], ["preferred_category", "A kind of thing they like", 2],
	["preferred_tag", "A tag they like", 0], ["disliked_tag", "A tag they dislike", 0],
	["disliked_item", "An item they dislike", -3],
]

var on_change: Callable
var baseline = null
var tier_rows: VBoxContainer
var tag_rows: VBoxContainer
var gift_spins: Dictionary = {}
var tier_baseline: Array = []
var tag_baseline: Dictionary = {}


func build(box: VBoxContainer, changed: Callable) -> void:
	on_change = changed
	box.add_child(InspectorStyle.create_sub_header("Relationships"))
	var hint := InspectorStyle.lbl("The ladder a relationship climbs, highest first when played. With no tiers the game keeps no score and names no bond; include one at 0.", InspectorStyle.COLOR_TEXT_DIM)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART; box.add_child(hint)
	var header := HBoxContainer.new(); box.add_child(header)
	header.add_child(InspectorStyle.lbl("Tiers (from points, name, vendor discount)", InspectorStyle.COLOR_TEXT_DIM))
	var spacer := Control.new(); spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; header.add_child(spacer)
	var add := Button.new(); add.name = "AddTier"; add.text = "+ Tier"; InspectorStyle.apply_button_style(add, InspectorStyle.COLOR_SUCCESS)
	add.pressed.connect(func(): _add_tier({"min": 0, "label": "", "vendor_discount": 0.0}); _changed()); header.add_child(add)
	tier_rows = VBoxContainer.new(); tier_rows.name = "SocialTiers"; tier_rows.add_theme_constant_override("separation", 4); box.add_child(tier_rows)

	box.add_child(InspectorStyle.lbl("Gift value, in relationship points", InspectorStyle.COLOR_ACCENT))
	var grid := GridContainer.new(); grid.columns = 4; grid.add_theme_constant_override("h_separation", 10); box.add_child(grid)
	for spec in GIFT_CATEGORIES:
		grid.add_child(InspectorStyle.lbl(str(spec[1]), InspectorStyle.COLOR_TEXT_DIM))
		var spin := SpinBox.new(); spin.name = "Gift_" + str(spec[0]); spin.min_value = -100; spin.max_value = 100; spin.step = 1
		spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed())
		grid.add_child(spin); gift_spins[spec[0]] = spin

	var tag_header := HBoxContainer.new(); box.add_child(tag_header)
	tag_header.add_child(InspectorStyle.lbl("Extra points for an item's gift tag", InspectorStyle.COLOR_TEXT_DIM))
	var tag_spacer := Control.new(); tag_spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL; tag_header.add_child(tag_spacer)
	var add_tag := Button.new(); add_tag.name = "AddGiftTag"; add_tag.text = "+ Tag"; InspectorStyle.apply_button_style(add_tag, InspectorStyle.COLOR_SUCCESS)
	add_tag.pressed.connect(func(): _add_tag("", 1); _changed()); tag_header.add_child(add_tag)
	tag_rows = VBoxContainer.new(); tag_rows.name = "GiftTags"; tag_rows.add_theme_constant_override("separation", 4); box.add_child(tag_rows)


func load(ruleset: Dictionary) -> void:
	var social = ruleset.get("social", null)
	baseline = social.duplicate(true) if social is Dictionary else null
	var source: Dictionary = social if social is Dictionary else {}
	for child in tier_rows.get_children(): tier_rows.remove_child(child); child.queue_free()
	tier_baseline = source.get("tiers", []).duplicate(true) if source.get("tiers") is Array else []
	for tier in tier_baseline:
		if tier is Dictionary: _add_tier(tier)
	var values: Dictionary = source.get("gift_values", {}) if source.get("gift_values") is Dictionary else {}
	for spec in GIFT_CATEGORIES:
		var spin: SpinBox = gift_spins[spec[0]]
		spin.set_value_no_signal(float(values.get(spec[0], spec[2])))
		spin.set_meta("loaded", spin.value)
	for child in tag_rows.get_children(): tag_rows.remove_child(child); child.queue_free()
	tag_baseline = source.get("gift_tag_values", {}).duplicate(true) if source.get("gift_tag_values") is Dictionary else {}
	for tag in tag_baseline:
		if not str(tag).begins_with("_"): _add_tag(str(tag), float(tag_baseline[tag]))


## The whole `social` section as it should be written, or {} for none.
func compose() -> Dictionary:
	var out: Dictionary = baseline.duplicate(true) if baseline is Dictionary else {}
	var tiers := _tiers()
	if not _same(tiers, tier_baseline):
		if tiers.is_empty(): out.erase("tiers")
		else: out["tiers"] = tiers
	for spec in GIFT_CATEGORIES:
		var spin: SpinBox = gift_spins[spec[0]]
		if spin.value == spin.get_meta("loaded"): continue
		if not out.get("gift_values") is Dictionary: out["gift_values"] = {}
		out["gift_values"][spec[0]] = int(spin.value)
	var tags := _tags()
	var authored_tags := {}
	for tag in tag_baseline:
		if not str(tag).begins_with("_"): authored_tags[tag] = tag_baseline[tag]
	if not _same(tags, authored_tags):
		var kept := {}
		for tag in tag_baseline:
			if str(tag).begins_with("_"): kept[tag] = tag_baseline[tag]
		kept.merge(tags)
		if kept.is_empty(): out.erase("gift_tag_values")
		else: out["gift_tag_values"] = kept
	return out


func changed() -> bool:
	var before = baseline if baseline is Dictionary else {}
	return not _same(compose(), before)


func _add_tier(source: Dictionary) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6); row.set_meta("source", source.duplicate(true))
	var minimum := SpinBox.new(); minimum.name = "Min"; minimum.min_value = 0; minimum.max_value = 100000; minimum.step = 1
	minimum.value = float(source.get("min", 0)); minimum.custom_minimum_size.x = 80; InspectorStyle.apply_input_style(minimum)
	minimum.value_changed.connect(func(_v): _changed()); row.add_child(minimum)
	var label := LineEdit.new(); label.name = "Label"; label.text = str(source.get("label", "")); label.placeholder_text = "tier name"
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(label); label.text_changed.connect(func(_t): _changed()); row.add_child(label)
	row.add_child(InspectorStyle.lbl("discount", InspectorStyle.COLOR_TEXT_DIM))
	var discount := SpinBox.new(); discount.name = "Discount"; discount.min_value = 0; discount.max_value = 0.95; discount.step = 0.01
	discount.value = float(source.get("vendor_discount", 0.0)); discount.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(discount)
	discount.value_changed.connect(func(_v): _changed()); row.add_child(discount)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): tier_rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	tier_rows.add_child(row)


func _tiers() -> Array:
	var out: Array = []
	for row in tier_rows.get_children():
		var tier: Dictionary = row.get_meta("source", {}).duplicate(true)
		tier["min"] = int((row.get_node("Min") as SpinBox).value)
		var label := (row.get_node("Label") as LineEdit).text.strip_edges()
		if label == "": tier.erase("label")
		else: tier["label"] = label
		var discount := snappedf((row.get_node("Discount") as SpinBox).value, 0.01)
		# An unauthored discount stays unauthored while it is still 0.
		if discount == 0.0 and not row.get_meta("source", {}).has("vendor_discount"): tier.erase("vendor_discount")
		else: tier["vendor_discount"] = discount
		out.append(tier)
	return out


func _add_tag(tag: String, value: float) -> void:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 6)
	var name_field := LineEdit.new(); name_field.name = "Tag"; name_field.text = tag; name_field.placeholder_text = "item gift tag"
	name_field.size_flags_horizontal = Control.SIZE_EXPAND_FILL; InspectorStyle.apply_input_style(name_field); name_field.text_changed.connect(func(_t): _changed()); row.add_child(name_field)
	var spin := SpinBox.new(); spin.name = "Points"; spin.min_value = -100; spin.max_value = 100; spin.step = 1; spin.value = value
	spin.custom_minimum_size.x = 70; InspectorStyle.apply_input_style(spin); spin.value_changed.connect(func(_v): _changed()); row.add_child(spin)
	var remove := Button.new(); remove.text = "×"; InspectorStyle.apply_button_style(remove, DialogStyle.COLOR_DANGER)
	remove.pressed.connect(func(): tag_rows.remove_child(row); row.queue_free(); _changed()); row.add_child(remove)
	tag_rows.add_child(row)


func _tags() -> Dictionary:
	var out := {}
	for row in tag_rows.get_children():
		var tag := (row.get_node("Tag") as LineEdit).text.strip_edges()
		if tag != "": out[tag] = int((row.get_node("Points") as SpinBox).value)
	return out


static func _same(a, b) -> bool:
	return JSON.stringify(SaveIO._normalize_numbers(a)) == JSON.stringify(SaveIO._normalize_numbers(b))


func _changed() -> void:
	if on_change.is_valid(): on_change.call()
