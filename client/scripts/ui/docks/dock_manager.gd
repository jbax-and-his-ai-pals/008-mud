# scripts/ui/docks/dock_manager.gd
#
# The left and right docks of the game view: which info panels exist, where each one sits,
# whether it is collapsed, and how the layout is remembered between runs
# (`user://dock_layout.json`). Also owns the panels that are drawn from the server's `character`
# and `world` events (Character, Attributes, Equipment, Spells, Skills, World); the rest wrap
# labels the main controller already updates (Pack, Surroundings, Quests...).
#
# Reached through `preload`.
extends RefCounted

const DOCK_PANEL = preload("res://scripts/ui/docks/dock_panel.gd")
const DOCK_COLUMN = preload("res://scripts/ui/docks/dock_column.gd")
# One file holds every saved arrangement: "<server>|<character>" -> layout, plus "_last", the most
# recent one, which a character with no arrangement of their own starts from.
const LAYOUT_PATH := "user://dock_layouts.json"
const LAST := "_last"
const DOCK_WIDTH := 300

# id -> [title, default dock, start collapsed]. The order here is the default order.
const PANELS := [
	["character", "Character", "left", false],
	["attributes", "Attributes", "left", false],
	["equipment", "Equipment", "left", false],
	["spells", "Spells", "left", false],
	["skills", "Skills", "left", false],
	["world", "World", "right", false],
	["surroundings", "Surroundings", "right", false],
	["pack", "Pack", "right", false],
	["quests", "Quests", "right", false],
	["combat", "Combat", "right", false],
	["crafting", "Crafting", "right", false],
	["collections", "Collections", "right", false],
	["discoveries", "Discoveries", "right", false],
	["relationships", "Relationships", "right", false],
]

var left_column: VBoxContainer
var right_column: VBoxContainer
var left_scroll: ScrollContainer
var right_scroll: ScrollContainer
var panels: Dictionary = {}    # id -> DockPanel

var _hp_bar: ProgressBar
var _mp_bar: ProgressBar
var _xp_bar: ProgressBar
var _identity: RichTextLabel
var _hp_text: Label
var _mp_text: Label
var _xp_text: Label
var _effects: RichTextLabel
var _attributes: RichTextLabel
var _equipment: RichTextLabel
var _spells: RichTextLabel
var _skills: RichTextLabel
var _world: RichTextLabel
var _on_link: Callable
var _layout_key: String = ""


## `existing` maps a panel id to the nodes that already display it (the main controller keeps
## updating them); they are moved into that panel's card.
func _init(existing: Dictionary, on_link: Callable) -> void:
	_on_link = on_link
	left_column = _make_column()
	right_column = _make_column()
	left_scroll = _make_scroll(left_column)
	right_scroll = _make_scroll(right_column)
	var saved: Variant = _load_all().get(LAST, {})
	for spec in PANELS:
		var id: String = spec[0]
		var content := _content_for(id, existing.get(id, []))
		var card = DOCK_PANEL.new()
		card.setup(id, spec[1], content, bool(spec[3]))
		card.changed.connect(save_layout)
		panels[id] = card
	# default placement first, then whatever the player arranged
	for spec in PANELS:
		(left_column if spec[2] == "left" else right_column).add_child(panels[spec[0]])
	_apply_saved(saved if saved is Dictionary else {})


func _make_column() -> VBoxContainer:
	var column: VBoxContainer = DOCK_COLUMN.new()
	column.add_theme_constant_override("separation", 6)
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.layout_changed.connect(save_layout)
	return column


func _make_scroll(column: VBoxContainer) -> ScrollContainer:
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size = Vector2(DOCK_WIDTH, 0)
	scroll.add_child(column)
	# The column fills the dock's height, so a panel can be dropped into the empty space below the last one.
	scroll.resized.connect(func() -> void: column.custom_minimum_size.y = scroll.size.y)
	return scroll


# --- content ----------------------------------------------------------------------------

func _text_block() -> RichTextLabel:
	var label := RichTextLabel.new()
	label.bbcode_enabled = true
	label.fit_content = true
	label.scroll_active = false
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.selection_enabled = false
	label.meta_clicked.connect(_on_link)
	return label


func _bar(color: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size = Vector2(0, 18)
	bar.show_percentage = false
	var fill := StyleBoxFlat.new()
	fill.bg_color = color
	bar.add_theme_stylebox_override("fill", fill)
	return bar


func _bar_caption() -> Label:
	var label := Label.new()
	label.add_theme_font_size_override("font_size", 13)
	label.add_theme_color_override("font_color", Color(0.85, 0.85, 0.85))
	return label


const EMPTY_TEXT := {
	"crafting": "No crafting recipes known.",
	"collections": "No collections started.",
	"discoveries": "No discoveries yet.",
	"relationships": "No relationships yet.",
}


func _content_for(id: String, nodes: Array) -> Control:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 3)
	match id:
		"character":
			_identity = _text_block()
			box.add_child(_identity)
			_hp_bar = _bar(Color(0.75, 0.25, 0.25))
			_mp_bar = _bar(Color(0.3, 0.45, 0.85))
			_xp_bar = _bar(Color(0.85, 0.7, 0.25))
			_hp_text = _bar_caption()
			_mp_text = _bar_caption()
			_xp_text = _bar_caption()
			# each reading sits above its own bar
			for pair in [[_hp_text, _hp_bar], [_mp_text, _mp_bar], [_xp_text, _xp_bar]]:
				box.add_child(pair[0])
				box.add_child(pair[1])
			_effects = _text_block()
			box.add_child(_effects)
			_identity.text = "[i]Waiting for the server...[/i]"
		"attributes":
			_attributes = _text_block()
			box.add_child(_attributes)
		"equipment":
			_equipment = _text_block()
			box.add_child(_equipment)
		"spells":
			_spells = _text_block()
			box.add_child(_spells)
		"skills":
			_skills = _text_block()
			box.add_child(_skills)
		"world":
			_world = _text_block()
			box.add_child(_world)
			_world.text = "[i]No clock yet.[/i]"
		_:
			for node in nodes:
				if node is Node:
					if node.get_parent() != null:
						node.reparent(box, false)
					else:
						box.add_child(node)
				# The scene gave these lists a fixed minimum height; in a card they size to their text.
				if node is RichTextLabel:
					node.fit_content = true
					node.scroll_active = false
					node.custom_minimum_size = Vector2.ZERO
					if EMPTY_TEXT.has(id) and node.bbcode_enabled and node == nodes[nodes.size() - 1]:   # the list, until the server says otherwise
						node.text = "[i][color=#808080]%s[/color][/i]" % EMPTY_TEXT[id]
	return box


# --- server data ------------------------------------------------------------------------

func apply_character(p: Dictionary) -> void:
	var health: Dictionary = p.get("health", {})
	var lines := "[b]%s[/b]" % _esc(str(p.get("name", "")))
	var cls := str(p.get("class", ""))
	var level := int(p.get("level", 0))
	if level > 0:
		lines += "   Level %d%s" % [level, (" " + _esc(cls)) if cls != "" else ""]
	if p.has("gold"):
		lines += "\n[color=#ffe45c]%d %s[/color]" % [int(p.get("gold", 0)), _esc(str(p.get("currency", "gold")))]
	_identity.text = lines
	_set_bar(_hp_bar, int(health.get("current", 0)), int(health.get("max", 1)))
	_hp_text.text = "HP %d/%d" % [int(health.get("current", 0)), int(health.get("max", 0))]
	var pool: Variant = p.get("ability_resource")
	_mp_bar.visible = pool is Dictionary and int((pool as Dictionary).get("max", 0)) > 0
	_mp_text.visible = _mp_bar.visible
	if pool is Dictionary and _mp_bar.visible:
		var pool_d: Dictionary = pool
		_set_bar(_mp_bar, int(pool_d.get("current", 0)), int(pool_d.get("max", 1)))
		_mp_text.text = "%s %d/%d" % [str(pool_d.get("short", "MP")), int(pool_d.get("current", 0)), int(pool_d.get("max", 0))]
	_xp_bar.visible = p.has("experience_to_level") and int(p.get("experience_to_level", 0)) > 0
	_xp_text.visible = _xp_bar.visible
	if _xp_bar.visible:
		_set_bar(_xp_bar, int(p.get("experience", 0)), int(p.get("experience_to_level", 1)))
		_xp_text.text = "XP %d/%d" % [int(p.get("experience", 0)), int(p.get("experience_to_level", 0))]

	var effect_lines: PackedStringArray = []
	for effect in p.get("effects", []):
		var e: Dictionary = effect
		var detail := ""
		var per_tick := int(e.get("per_tick", 0))
		if per_tick > 0:
			detail = " [color=%s]%s%d/tick[/color]" % ["#ff6060" if str(e.get("type", "")) == "dot" else "#6cff6c", "-" if str(e.get("type", "")) == "dot" else "+", per_tick]
		effect_lines.append("%s%s (%s)" % [_esc(str(e.get("name", "Effect"))), detail, _duration(float(e.get("remaining", 0)))])
	_effects.text = ("[color=#c0c0c0]Effects:[/color] " + ", ".join(effect_lines)) if not effect_lines.is_empty() else "[color=#808080]No active effects[/color]"

	# two attributes to a row: label, value, label, value
	var stat_cells := ""
	var stat_count := 0
	for stat in p.get("stats", []):
		var s: Dictionary = stat
		stat_cells += "[cell][color=#c0c0c0]%s[/color][/cell][cell][b]%d[/b]   [/cell]" % [_esc(str(s.get("label", ""))), int(s.get("value", 0))]
		stat_count += 1
	if stat_count % 2 == 1:
		stat_cells += "[cell][/cell][cell][/cell]"
	_attributes.text = ("[table=4]%s[/table]" % stat_cells) if stat_count > 0 else "[i]No attributes[/i]"

	var worn: PackedStringArray = []
	for slot in p.get("equipment", []):
		var q: Dictionary = slot
		var item := str(q.get("item", ""))
		var text := "[color=#c0c0c0]%s[/color]  " % _esc(str(q.get("label", "")))
		text += _esc(item) if item != "" else "[color=#808080](empty)[/color]"
		if str(q.get("durability", "")) != "":
			text += " [color=#ffa540][%s][/color]" % str(q.get("durability", ""))
		worn.append(text)
	_equipment.text = "\n".join(worn)

	var spell_lines: PackedStringArray = []
	for spell in p.get("spells", []):
		var sp: Dictionary = spell
		var line := "%s [color=#6f9bff](%d)[/color]" % [_esc(str(sp.get("name", ""))), int(sp.get("cost", 0))]
		if float(sp.get("cooldown", 0)) > 0.0:
			line += " [color=#ffa540]cooldown %.0fs[/color]" % float(sp.get("cooldown", 0))
		spell_lines.append(line)
	_spells.text = "\n".join(spell_lines) if not spell_lines.is_empty() else "[i][color=#808080]No spells known.[/color][/i]"

	var skill_lines: PackedStringArray = []
	for skill in p.get("skills", []):
		var k: Dictionary = skill
		skill_lines.append("%s  %d" % [_esc(str(k.get("name", ""))), int(k.get("level", 0))])
	_skills.text = "\n".join(skill_lines) if not skill_lines.is_empty() else "[i][color=#808080]No skills learned yet.[/color][/i]"


func apply_world(p: Dictionary) -> void:
	var period_colors := {"dawn": "#ffa540", "morning": "#d8d864", "afternoon": "#ffff96", "dusk": "#ff6464", "night": "#7d7dff", "day": "#ffff96"}
	var period := str(p.get("period", ""))
	var lines := "[b][color=%s]%s[/color][/b]   %s" % [period_colors.get(period, "#ffffff"), str(p.get("time", "")), period.capitalize()]
	if str(p.get("date", "")) != "":
		lines += "\n" + _esc(str(p.get("date", "")))
	var weather := str(p.get("weather", ""))
	if weather != "":
		var intensity := str(p.get("intensity", ""))
		lines += "\n[color=#add8e6]Weather:[/color] %s%s" % [weather.capitalize(), (" (%s)" % intensity) if intensity != "" else ""]
	if str(p.get("season", "")) != "":
		lines += "\n[color=#c0c0c0]Season:[/color] %s" % str(p.get("season", "")).capitalize()
	_world.text = lines


func _set_bar(bar: ProgressBar, current: int, maximum: int) -> void:
	bar.max_value = maxi(1, maximum)
	bar.value = clampi(current, 0, maxi(1, maximum))


func _duration(seconds: float) -> String:
	return "%.1fm" % (seconds / 60.0) if seconds > 60.0 else "%ds" % int(seconds)


func _esc(text: String) -> String:
	return text.replace("[", "[lb]")


# --- moving and remembering -------------------------------------------------------------

## The arrangement belongs to a character on a server: switching to one that has a saved layout
## applies it; one that has none keeps what is on screen and saves it as theirs from now on.
func use_layout_for(server: String, character: String) -> void:
	var key := "%s|%s" % [server.strip_edges(), character.strip_edges().to_lower()]
	if key == _layout_key or character.strip_edges() == "":
		return
	_layout_key = key
	var saves := _load_all()
	if saves.has(key) and saves[key] is Dictionary:
		_apply_saved(saves[key])
	else:
		save_layout()


func save_layout() -> void:
	var data := {}
	for pair in [["left", left_column], ["right", right_column]]:
		var column: VBoxContainer = pair[1]
		for card in column.get_children():
			if card.get("panel_id") == null:
				continue   # the drop preview box
			data[card.panel_id] = {"dock": pair[0], "index": card.get_index(), "collapsed": card.collapsed}
	var saves := _load_all()
	saves[LAST] = data
	if _layout_key != "":
		saves[_layout_key] = data
	var file := FileAccess.open(LAYOUT_PATH, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(saves))


func reset_layout() -> void:
	for spec in PANELS:
		var card: Control = panels[spec[0]]
		var column: VBoxContainer = left_column if spec[2] == "left" else right_column
		if card.get_parent() != column:
			card.get_parent().remove_child(card)
			column.add_child(card)
		card.set_collapsed(bool(spec[3]), false)
	for column in [left_column, right_column]:
		var order := []
		for spec in PANELS:
			if panels[spec[0]].get_parent() == column:
				order.append(spec[0])
		for i in range(order.size()):
			column.move_child(panels[order[i]], i)
	save_layout()


func _load_all() -> Dictionary:
	if not FileAccess.file_exists(LAYOUT_PATH):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(LAYOUT_PATH))
	return parsed if parsed is Dictionary else {}


func _apply_saved(saved: Dictionary) -> void:
	if saved.is_empty():
		return
	var placed: Array = []
	for id in saved:
		if not panels.has(id) or not (saved[id] is Dictionary):
			continue
		var entry: Dictionary = saved[id]
		var card: Control = panels[id]
		var column: VBoxContainer = right_column if str(entry.get("dock", "left")) == "right" else left_column
		if card.get_parent() != column:
			card.get_parent().remove_child(card)
			column.add_child(card)
		card.set_collapsed(bool(entry.get("collapsed", false)), false)
		placed.append([column, int(entry.get("index", 0)), card])
	placed.sort_custom(func(a, b) -> bool: return int(a[1]) < int(b[1]))
	for item in placed:
		var column: VBoxContainer = item[0]
		column.move_child(item[2], mini(column.get_child_count() - 1, int(item[1])))
