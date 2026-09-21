# tests/npc_stat_vocabulary_smoke.gd
#
# Track G item 5: an NPC's attribute rows come from the content set's own stat
# declaration, not from eight fantasy names hard-coded in the panel.
#
#   godot --headless --path mud-world-editor --script tests/npc_stat_vocabulary_smoke.gd
#
# The defect this exists for
# -------------------------
# `NPCInspector.attr_keys` named strength, dexterity, constitution, agility,
# intelligence, wisdom, spell_power and magic_resist -- always, for every content
# set. `orbital_salvage` declares six stats and `modern_capsule` declares none, so
# two of those rows offered to write a stat the set does not have. The panel also
# built `cur_data["stats"] = {}` merely by being opened, which is a write nobody
# asked for and exactly the kind of implicit write the round-trip check exists to
# catch.
#
# What is asserted here
# ---------------------
# The precedence the editor follows is the engine's own (`World.declared_status_stats`
# then `contracts/stats.py`), and it is asserted one source at a time so a fixture
# can only pass by reading the source it names:
#
#   1. `stats.order` in the contracts
#   2. `status.stats` in the ruleset
#   3. the stats `stats.roles` names
#   4. the stats the set's own NPCs carry
#   5. nothing -- no rows, and a sentence saying why
#
# Plus the shipped set: fantasy_frontier's eight rows are unchanged, and every row
# shows the number the file holds.

extends SceneTree

var failure_count := 0
var repo_root: String = ""
var scratch: String = ""

const STATS_ORDER := ["grit", "wits", "cool"]
const RULESET_STATS := ["vigor", "nerve", "focus", "luck"]
const ROLE_STATS := ["vitality", "force", "reflex"]
const NPC_STATS := ["grit", "nerve", "wits"]


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	scratch = ProjectSettings.globalize_path("res://").path_join("../tmp/npc_stat_vocabulary")
	_rebuild_fixtures()

	_check_declared_order_wins()
	_check_the_ruleset_is_read_when_the_contracts_are_silent()
	_check_roles_name_the_vocabulary_when_there_is_no_list()
	_check_the_sets_own_data_is_the_last_resort()
	_check_nothing_declared_shows_no_rows()
	_check_pool_labels_come_from_the_declared_resources()
	_check_opening_writes_nothing()
	_check_an_edit_writes_one_stat_as_an_int()
	_check_the_shipped_set_is_unchanged()

	if failure_count > 0:
		push_error("npc stat vocabulary failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- the sources, one at a time -----------------------------------------------

func _check_declared_order_wins() -> void:
	print("\n[a set that declares stats.order]")
	var holder := _inspect("declared", "npc_probe")
	var labels := _row_labels(holder)

	_assert(labels == ["Grit", "Wits", "Cool"],
		"the rows are the declared stats, in the declared order: %s" % str(labels))
	_assert(_row_spinboxes(holder).size() == 3, "three rows and no fourth")
	for undeclared in ["Strength", "Dexterity", "Spell Power", "Magic Resist", "Wisdom"]:
		_assert(not labels.has(undeclared), "no row for an undeclared stat (%s)" % undeclared)
	_assert(_attributes_tooltip(holder) == "Attribute rows come from the contracts' `stats.order`.",
		"and the panel says where they came from: %s" % _attributes_tooltip(holder))


func _check_the_ruleset_is_read_when_the_contracts_are_silent() -> void:
	print("\n[a set with no contracts, naming stats in its ruleset]")
	var holder := _inspect("ruleset", "npc_probe")
	var labels := _row_labels(holder)

	_assert(labels == ["Vigor", "Nerve", "Focus", "Luck"],
		"the ruleset's status.stats is the vocabulary: %s" % str(labels))
	_assert(_attributes_tooltip(holder) == "Attribute rows come from the ruleset's `status.stats`.",
		"and the panel says where they came from: %s" % _attributes_tooltip(holder))


func _check_roles_name_the_vocabulary_when_there_is_no_list() -> void:
	print("\n[a set that declares roles but no display list]")
	var holder := _inspect("roles", "npc_probe")
	var labels := _row_labels(holder)

	_assert(labels == ["Vitality", "Force", "Reflex"],
		"the distinct stats the roles name, in role order: %s" % str(labels))
	_assert(_attributes_tooltip(holder) == "Attribute rows come from the stats `stats.roles` names.",
		"and the panel says where they came from: %s" % _attributes_tooltip(holder))


func _check_the_sets_own_data_is_the_last_resort() -> void:
	print("\n[a set that declares nothing at all]")
	var holder := _inspect("data", "npc_probe")
	var labels := _row_labels(holder)

	_assert(labels == ["Grit", "Nerve", "Wits"],
		"the stats its NPCs already carry, sorted: %s" % str(labels))
	# The point of the fallback: the set's data, not a fantasy default. A set whose
	# NPCs carry three stats must not be offered eight.
	_assert(not labels.has("Spell Power") and not labels.has("Constitution"),
		"and nothing from the engine's own default names")
	_assert(_attributes_tooltip(holder) == "Attribute rows come from the stats this set's NPCs carry.",
		"and the panel says where they came from: %s" % _attributes_tooltip(holder))


func _check_nothing_declared_shows_no_rows() -> void:
	print("\n[a set with no vocabulary anywhere]")
	var holder := _inspect("empty", "npc_probe")

	_assert(_find_grid(holder) == null, "no attribute grid is built")
	_assert(_row_labels(holder).is_empty(), "and no stat rows")
	var hint := ""
	for text in _label_texts(holder):
		if text.contains("declares no stats"):
			hint = text
	_assert(hint != "", "an author is told why, and where to declare them")
	_assert(hint.contains("world_contracts.json"), "naming the file the declaration lives in")


func _check_pool_labels_come_from_the_declared_resources() -> void:
	print("\n[the pool rows]")
	var texts := _label_texts(_inspect("declared", "npc_probe"))
	_assert(texts.has("Charge"), "the ability pool is called what the set calls it: %s" % str(texts))
	_assert(texts.has("Starting Integrity"), "and so is the vital pool")
	_assert(not texts.has("Mana"), "the fantasy word is gone for a set that never says it")

	var bare := _label_texts(_inspect("data", "npc_probe"))
	_assert(bare.has("Ability"), "a set that declares no resource gets the engine's neutral label")
	_assert(bare.has("Starting Health"), "and its vital pool keeps the key's own name")
	_assert(not bare.has("Mana"), "never the genre word")


# --- writes ------------------------------------------------------------------

func _check_opening_writes_nothing() -> void:
	print("\n[opening an NPC that has no stats]")
	var manager := _manager_in(scratch.path_join("declared"))
	var npc: Dictionary = manager.npcs["npc_probe"]
	_assert(not npc.has("stats"), "the fixture NPC starts with no stats key")

	var holder := _build_inspector(manager, "npc_probe")
	_assert(_row_spinboxes(holder).size() == 3, "the panel built its rows")
	# The old panel did `if not cur_data.has("stats"): cur_data["stats"] = {}` in
	# `build()`, so merely opening an NPC added an empty object to the file.
	_assert(not npc.has("stats"), "and opening it did not add one")


func _check_an_edit_writes_one_stat_as_an_int() -> void:
	print("\n[editing one attribute]")
	var manager := _manager_in(scratch.path_join("declared"))
	var npc: Dictionary = manager.npcs["npc_probe"]
	var holder := _build_inspector(manager, "npc_probe")
	var boxes := _row_spinboxes(holder)
	_assert(boxes.size() == 3, "three rows to edit")
	if boxes.is_empty():
		return

	# Drive the row the way a SpinBox does.
	boxes[0].value = 9
	boxes[0].value_changed.emit(9.0)

	_assert(typeof(npc.get("stats")) == TYPE_DICTIONARY, "the edit creates the stats object")
	var stats: Dictionary = npc.get("stats", {})
	_assert(stats.keys() == ["grit"], "and writes the stat that row stands for: %s" % str(stats.keys()))
	_assert(typeof(stats.get("grit")) == TYPE_INT,
		"as an int, not the float a SpinBox emits (got %s)" % type_string(typeof(stats.get("grit"))))
	_assert(int(stats.get("grit", 0)) == 9, "with the value that was set")
	_assert(not stats.has("spell_power"), "and nothing the set does not declare")


# --- the shipped content set --------------------------------------------------

func _check_the_shipped_set_is_unchanged() -> void:
	print("\n[fantasy_frontier, the set this replaced]")
	var manager := _manager_in(repo_root.path_join("content_sets").path_join("fantasy_frontier"))
	if manager == null:
		return
	var declared := manager.catalog.stat_vocabulary()
	_assert(declared.size() == 8, "the set declares eight stats: %s" % str(declared))

	var npc_id := ""
	for candidate in manager.npcs.keys():
		var template = manager.npcs[candidate]
		if typeof(template) == TYPE_DICTIONARY and typeof(template.get("stats")) == TYPE_DICTIONARY \
		and template["stats"].size() >= 6:
			npc_id = str(candidate)
			break
	_assert(npc_id != "", "a shipped NPC with a full stat block was found")
	if npc_id == "":
		return

	var template: Dictionary = manager.npcs[npc_id]
	var holder := _build_inspector(manager, npc_id)
	var labels := _row_labels(holder)
	var expected: Array = []
	for stat in declared:
		expected.append(str(stat).capitalize())
	_assert(labels == expected,
		"every declared stat has a row, in the declared order (%s vs %s)" % [str(labels), str(expected)])

	# Shipped templates keep their existing numbers: each row shows what the file
	# holds, and opening the panel writes nothing back.
	var before := JSON.stringify(template["stats"])
	var boxes := _row_spinboxes(holder)
	for index in range(min(boxes.size(), declared.size())):
		var stat := str(declared[index])
		if not template["stats"].has(stat):
			continue
		_assert(int(boxes[index].value) == int(template["stats"][stat]),
			"%s shows the file's value (%d)" % [stat, int(template["stats"][stat])])
	_assert(JSON.stringify(template["stats"]) == before, "and opening the panel changed nothing")


# --- helpers ------------------------------------------------------------------

func _inspect(fixture: String, npc_id: String) -> Node:
	var manager := _manager_in(scratch.path_join(fixture))
	_assert(manager != null, "the %s fixture loads" % fixture)
	if manager == null:
		return null
	return _build_inspector(manager, npc_id)


## The real path: `DatabaseInspector` builds the NPC panel and passes the manager,
## which is where the catalog and the set's other NPCs come from.
func _build_inspector(manager: DatabaseManager, npc_id: String) -> Node:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _manager_in(root_path: String) -> DatabaseManager:
	DataRoot._resolved = root_path
	DataRoot._source = "test fixture"
	var manager := DatabaseManager.new()
	if manager.npcs.is_empty():
		printerr("  FAIL no NPCs loaded from %s" % root_path)
		failure_count += 1
		return null
	return manager


func _catalog(fixture: String) -> ContractCatalog:
	DataRoot._resolved = scratch.path_join(fixture)
	return DatabaseManager.new().catalog


## What the "Attributes:" row says about where its vocabulary came from, read off
## the built panel rather than recomputed -- the tooltip is the affordance an
## author actually has.
func _attributes_tooltip(node: Node) -> String:
	for label in _labels(node):
		if str(label.text) == "Attributes:":
			return str(label.tooltip_text)
	return "(no attributes row)"


func _find_grid(node: Node) -> GridContainer:
	if node == null:
		return null
	if node is GridContainer:
		return node
	for child in node.get_children():
		var found := _find_grid(child)
		if found != null:
			return found
	return null


## The label of each attribute row, in build order.
func _row_labels(node: Node) -> Array:
	var grid := _find_grid(node)
	var out: Array = []
	if grid == null:
		return out
	for row in grid.get_children():
		for child in row.get_children():
			if child is Label:
				out.append(str(child.text))
	return out


## The SpinBox of each attribute row, in the same order as `_row_labels`.
func _row_spinboxes(node: Node) -> Array:
	var grid := _find_grid(node)
	var out: Array = []
	if grid == null:
		return out
	for row in grid.get_children():
		for child in row.get_children():
			if child is SpinBox:
				out.append(child)
	return out


func _label_texts(node: Node) -> Array:
	var out: Array = []
	for label in _labels(node):
		out.append(str(label.text))
	return out


func _labels(node: Node) -> Array:
	var out: Array = []
	if node == null:
		return out
	if node is Label:
		out.append(node)
	for child in node.get_children():
		out.append_array(_labels(child))
	return out


# --- fixtures -----------------------------------------------------------------

func _rebuild_fixtures() -> void:
	_remove_recursive(scratch)

	# 1. stats.order in the contracts, plus two resources to label the pools with.
	_write("declared", "data/contracts/world_contracts.json", {
		"schema_version": 1,
		"label": "Declared stats fixture",
		"stats": {
			"order": STATS_ORDER,
			"roles": {"health": "grit", "attack": "wits", "power": "cool"},
			"short": {"grit": "GRT"},
		},
		"resources": [
			{"id": "health", "label": "Integrity", "short": "INT", "kind": "vital", "regenerates": false},
			{"id": "charge", "label": "Charge", "short": "CHG", "kind": "ability", "regenerates": true},
		],
	})
	_write_npcs("declared", {}, {"cool": 1})

	# 2. No contracts at all; the older spelling in the ruleset.
	_write("ruleset", "rules/ruleset.json", {"status": {"stats": RULESET_STATS}})
	_write_npcs("ruleset", {})

	# 3. Roles but no display list: `health` and `resistance` share a stat, so the
	#    vocabulary must be the distinct names rather than one row per role.
	#    Written as text because `JSON.stringify` sorts keys, and the order the
	#    roles are declared in is part of what this asserts.
	_write_raw("roles", "data/contracts/world_contracts.json", """
{
  "schema_version": 1,
  "label": "Roles-only fixture",
  "stats": {
    "roles": {
      "health": "vitality",
      "attack": "force",
      "evasion": "reflex",
      "resistance": "force"
    }
  }
}
""")
	_write_npcs("roles", {})

	# 4. Nothing declared; the NPCs carry the vocabulary.
	_write_npcs("data", {"wits": 4, "grit": 2}, {"nerve": 1})

	# 5. Nothing declared and nothing carried.
	_write("empty", "rules/ruleset.json", {})
	_write_npcs("empty", {})


## One probe NPC with no `stats` key at all (so "writes nothing on build" is
## observable), plus optional extra NPCs whose stats are the set's data.
func _write_npcs(fixture: String, probe_stats: Dictionary, extra_stats: Dictionary = {}) -> void:
	var probe := {
		"name": "Probe", "description": "", "level": 2, "health": 12,
		"friendly": true, "behavior_type": "static", "properties": {},
	}
	if not probe_stats.is_empty():
		probe["stats"] = probe_stats
	var payload := {"npc_probe": probe}
	if not extra_stats.is_empty():
		payload["npc_other"] = {
			"name": "Other", "description": "", "level": 1, "health": 10,
			"friendly": false, "behavior_type": "static", "properties": {},
			"stats": extra_stats,
		}
	_write(fixture, "data/npcs/probe.json", payload)


func _write(fixture: String, relative: String, payload: Dictionary) -> void:
	var path := scratch.path_join(fixture).path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(payload, "  "))
	file.close()


## For a fixture whose key order is part of the assertion: `JSON.stringify` sorts
## keys, so an object written through `_write` cannot declare roles in an order.
func _write_raw(fixture: String, relative: String, text: String) -> void:
	var path := scratch.path_join(fixture).path_join(relative)
	DirAccess.make_dir_recursive_absolute(path.get_base_dir())
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(text.strip_edges())
	file.close()


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var full := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(full)
		else:
			DirAccess.remove_absolute(full)
		name = dir.get_next()
	dir.list_dir_end()


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		printerr("  FAIL ", message)
