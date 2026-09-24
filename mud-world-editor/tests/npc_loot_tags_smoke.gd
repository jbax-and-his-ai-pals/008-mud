# tests/npc_loot_tags_smoke.gd
#
# `properties.loot_tags` (npc.py::_matches_ambient_loot_pool) is what the
# ruleset's ambient loot pools select on, and had no editor control: thirty
# fantasy hostiles were never tagged and so never rolled a pool. The NPC
# inspector now edits the tags and says which pools the NPC falls into.
# fantasy_frontier is the fixture; its four pools are "living" (18%),
# "living"+"beast" (10%), "living"+"humanoid" (10%) and "living"+"giant" (4%).
#
#   godot --headless --path mud-world-editor --script tests/npc_loot_tags_smoke.gd

extends SceneTree

var failures := 0


func _init(): _run.call_deferred()


func _run():
	var repo := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var fixture := repo.path_join("tmp/npc-loot-tags-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(repo.path_join("content_sets/fantasy_frontier"), fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	var manager := DatabaseManager.new()

	print("\n[a tagged beast]")
	var holder := _open(manager, "cave_bear")
	var field: LineEdit = holder.find_child("LootTags", true, false)
	var pools: Label = holder.find_child("LootPools", true, false)
	_assert(field != null and field.text == "living, beast", "the field shows the NPC's tags (%s)" % (field.text if field else "missing"))
	_assert(pools != null and pools.text == "Ambient loot pools: #1 (18%), #2 (10%)", "and the pools they select it for (%s)" % (pools.text if pools else "missing"))

	print("\n[retagging]")
	field.text = "living, giant"; field.text_changed.emit(field.text)
	_assert(manager.npcs["cave_bear"]["properties"]["loot_tags"] == ["living", "giant"], "an edit is written as a list")
	_assert(pools.text == "Ambient loot pools: #1 (18%), #4 (4%)", "and the pools line follows it (%s)" % pools.text)
	field.text = " "; field.text_changed.emit(field.text)
	_assert(not manager.npcs["cave_bear"]["properties"].has("loot_tags"), "an emptied field removes the key")
	_assert(pools.text == "No ambient loot pool selects this NPC.", "and says the NPC is out of every pool")

	print("\n[the undead and a pool naming a template]")
	var skeleton := _open(manager, "skeleton")
	_assert((skeleton.find_child("LootPools", true, false) as Label).text == "No ambient loot pool selects this NPC.", "an undead skeleton rolls no gem pool")
	var named := [{"chance": 1.0, "npc_template_ids": ["skeleton"], "entries": []}, {"chance": 0.5, "npc_tags_any": ["undead"], "npc_tags_none": ["construct"], "entries": []}]
	_assert(NPCInspector.ambient_pools_matched(named, ["undead"], "skeleton") == ["#1 (100%)", "#2 (50%)"], "template and any-tag selectors match")
	_assert(NPCInspector.ambient_pools_matched(named, ["undead", "construct"], "ghoul") == [], "another template and an excluded tag do not")

	print("\n[opening writes nothing]")
	var before := JSON.stringify(manager.npcs["wolf"])
	_open(manager, "wolf")
	_assert(JSON.stringify(manager.npcs["wolf"]) == before, "viewing a tagged NPC changes nothing")

	if failures > 0: push_error("npc loot tags smoke failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


func _open(manager: DatabaseManager, npc_id: String) -> Node:
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := DatabaseInspector.new(holder)
	inspector.set_db_manager(manager)
	inspector.build("npc", npc_id, manager.npcs[npc_id])
	return holder


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
