# scripts/ui/modals/ContractBrowserDialog.gd
#
# What this content set declares, in one window.
#
# The editor asks an author to name a family, a roll table, an attack profile, an
# ability -- ids that live in `data/contracts/world_contracts.json` and that
# nothing in the UI would otherwise show. Opening the JSON to find out what
# `collectible_stone` means, then coming back to type it, is how typos become
# content-validation failures.
#
# Read-only on purpose. The schema decides what fields may exist
# (`engine/contracts/registry.py`), the engine refuses anything it does not
# recognise, and an editor that offered to write them freehand would be inventing
# a second schema. What it can do honestly is show what is declared, and it reads
# the same file the engine does.

class_name ContractBrowserDialog
extends AcceptDialog

const ContractCatalogScript = preload("res://scripts/data/ContractCatalog.gd")

var catalog: ContractCatalog
var section_list: ItemList
var detail: RichTextLabel
var sections: Array = []


func setup(contract_catalog: ContractCatalog):
	for child in get_children():
		if child is HBoxContainer:
			remove_child(child)
			child.queue_free()
	catalog = contract_catalog
	title = "Content contracts"
	min_size = Vector2i(880, 560)

	var row := HBoxContainer.new()
	row.set_anchors_preset(Control.PRESET_FULL_RECT)
	row.custom_minimum_size = Vector2(860, 520)
	add_child(row)

	section_list = ItemList.new()
	section_list.custom_minimum_size = Vector2(260, 0)
	section_list.item_selected.connect(func(index): _show_section(index))
	row.add_child(section_list)

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.custom_minimum_size = Vector2(560, 0)
	detail = RichTextLabel.new()
	detail.bbcode_enabled = true
	detail.fit_content = true
	detail.selection_enabled = true
	detail.custom_minimum_size = Vector2(540, 0)
	scroll.add_child(detail)
	row.add_child(scroll)


func refresh():
	if catalog == null:
		return
	sections = catalog.sections()
	section_list.clear()
	for section in sections:
		section_list.add_item(str(section["title"]))
	if sections.is_empty():
		detail.text = "[color=orange]This content set declares no contracts.[/color]"
		return
	section_list.select(0)
	_show_section(0)


func _show_section(index: int):
	if index < 0 or index >= sections.size():
		return
	var section: Dictionary = sections[index]
	var lines: Array = []
	var header := str(section["title"])
	lines.append("[b]%s[/b]" % _escape(header))
	if catalog.source_path != "":
		lines.append("[color=gray]%s[/color]" % _escape(catalog.source_path))
	if not catalog.issues.is_empty():
		lines.append("")
		for issue in catalog.issues:
			lines.append("[color=salmon]%s[/color]" % _escape(str(issue)))
	lines.append("")

	var entries: Array = section["entries"]
	if entries.is_empty():
		lines.append("[color=gray]none declared[/color]")
	for entry in entries:
		lines.append("[color=cyan]%s[/color]" % _escape(str(entry["id"])))
		var detail_text := str(entry.get("detail", ""))
		if detail_text != "":
			lines.append("    [color=gray]%s[/color]" % _escape(detail_text))
	detail.text = "\n".join(lines)


func _escape(text: String) -> String:
	return text.replace("[", "[lb]")
