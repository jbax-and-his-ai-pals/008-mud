# tests/m2_route_journeys_smoke.gd
#
# M2's gate: edit a supported family through the editor, then prove the route in
# play. Each check below edits a scratch copy of fantasy_frontier through the
# real inspectors inside the editor scene, saves through the engine-checked save
# path (Main._save_everything), and then runs toolkit/edited_route_check.py
# against both the edited copy and the shipped set: the edit must change what
# happens in a real game, not merely what is written to disk.
#
#   godot --headless --path mud-world-editor --script tests/m2_route_journeys_smoke.gd

extends SceneTree

var failures := 0
var repo := ""
var fixture := ""
var shipped := ""
var main: Node2D = null
var checks_run := false
var inspectors: Array = []


func _initialize() -> void:
	repo = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	shipped = repo.path_join("content_sets/fantasy_frontier")
	fixture = repo.path_join("tmp/m2-routes-%s/fantasy_frontier" % Time.get_ticks_usec())
	_copy(shipped, fixture)
	DataRoot._resolved = fixture
	DataRoot._source = "test fixture"
	main = load("res://scenes/Main.tscn").instantiate()
	root.add_child(main)


func _process(_delta: float) -> bool:
	if checks_run: return false
	checks_run = true
	_run.call_deferred()
	return false


func _run() -> void:
	_combat_ability_route()
	_gather_craft_use_route()
	_dialogue_quest_reward_route()
	await _discovery_advancement_route()
	await _gift_relationship_route()
	await _kill_loot_route()
	_hazard_route()
	_spawner_route()
	await _weather_route()
	await _economy_route()
	await _crime_route()
	if failures > 0: push_error("m2 route journeys failed (%d)" % failures)
	quit(1 if failures > 0 else 0)


# --- combat / ability ---------------------------------------------------------
# "Changing a declaration demonstrably changes a real encounter": Magic Missile
# (8 damage) cannot kill a cave bear in one cast; edited to 300, it does.

func _combat_ability_route() -> void:
	print("\n[combat / ability: edit an ability's damage, then cast it]")
	var arguments := ["spell=magic_missile", "target=cave_bear"]
	var before := _route(shipped, "combat_ability", arguments)
	_assert(before.get("ok", false) and not before.get("died", true), "shipped: one Magic Missile does not kill a cave bear (%s)" % _brief(before))

	var ability: Dictionary = main.database_mgr.magic["magic_missile"]
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := MagicInspector.new(); inspectors.append(inspector)
	inspector.build(holder, ability, main.database_mgr.magic_groups, "magic_missile", main.database_mgr)
	(holder.find_child("Effect_0", true, false).find_child("value", true, false) as SpinBox).value = 300
	_assert(int(ability["effects"][0]["value"]) == 300, "the damage is edited through the ability inspector")
	main.database_mgr.mark_dirty("magic", "magic_missile")
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "and saved through the engine-checked save path")

	var after := _route(fixture, "combat_ability", arguments)
	_assert(after.get("ok", false) and after.get("died", false) and int(after.get("health_after", -1)) == 0, "edited: the same cast now kills it (%s)" % _brief(after))


# --- gather / craft / use -------------------------------------------------------
# Gather herbs, bind a bandage, use it. Edited: the recipe makes three bandages
# (RecipeInspector) and each heals 20 instead of 8 (ItemInspector).

func _gather_craft_use_route() -> void:
	print("\n[gather / craft / use: edit a recipe's yield and an item's effect, then play it]")
	var arguments := ["node=node_herb_bed", "tool=item_foraging_knife", "recipe=bind_herbal_bandage", "extra=item_leather_strip:3"]
	var before := _route(shipped, "gather_craft_use", arguments)
	_assert(before.get("ok", false) and int(before.get("gathered", 0)) == 1 and int(before.get("crafted", 0)) == 1 and int(before.get("healed", 0)) == 8, "shipped: gather 1, craft 1 bandage, which heals 8 (%s)" % _brief_craft(before))

	var recipe: Dictionary = main.database_mgr.recipes["bind_herbal_bandage"]
	var recipe_holder := VBoxContainer.new(); root.add_child(recipe_holder)
	var recipe_inspector := RecipeInspector.new(recipe_holder, main.database_mgr); inspectors.append(recipe_inspector)
	recipe_inspector.build("bind_herbal_bandage", recipe)
	_spin_beside(recipe_holder, "Quantity").value = 3
	_assert(int(recipe["result_quantity"]) == 3, "the recipe's yield is edited through the recipe inspector")

	var bandage: Dictionary = main.database_mgr.items["item_herbal_bandage"]
	var item_holder := VBoxContainer.new(); root.add_child(item_holder)
	var item_inspector := ItemInspector.new(); inspectors.append(item_inspector)
	item_inspector.build(item_holder, bandage, main.database_mgr)
	_spin_beside_key(item_holder, "effect_value").value = 20
	_assert(int(bandage["properties"]["effect_value"]) == 20, "the bandage's healing is edited through the item inspector")

	main.database_mgr.mark_dirty("recipe", "bind_herbal_bandage")
	main.database_mgr.mark_dirty("item", "item_herbal_bandage")
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "both saved through the engine-checked save path")

	var after := _route(fixture, "gather_craft_use", arguments)
	_assert(after.get("ok", false) and int(after.get("crafted", 0)) == 3 and int(after.get("result_left", 0)) == 2 and int(after.get("healed", 0)) == 20, "edited: the same gathering makes 3 bandages, and one heals 20 (%s)" % _brief_craft(after))


# --- dialogue / quest / reward ----------------------------------------------------
# The first commission: accept it from the board, have Elder Thorne teach the
# posy in conversation, make one and hand it over. Edited through the quest
# inspector: what it pays, and what the elder says when it is done.

const NEW_CLOSING := "Splendid work -- the whole valley will hear of it."

func _dialogue_quest_reward_route() -> void:
	print("\n[dialogue / quest / reward: edit a quest's rewards and closing line, then complete it]")
	var arguments := ["giver=Elder Thorne", "topic=commission", "recipe=tie_wildflower_posy", "deliver=wildflower posy", "inputs=item_wild_herbs:2"]
	var before := _route(shipped, "dialogue_quest_reward", arguments)
	_assert(before.get("ok", false) and before.get("recipe_learned", false) and before.get("completed", false) and int(before.get("xp_paid", 0)) == 25 and int(before.get("gold_gained", 0)) == 12, "shipped: taught in conversation, completed for 25 XP and 12 gold (%s)" % _brief_quest(before))

	var quest: Dictionary = main.database_mgr.quests["quest_wildflower_commission"]
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := QuestInspector.new(holder, main.database_mgr, main.world_mgr); inspectors.append(inspector)
	inspector.build("quest_wildflower_commission", quest)
	(holder.find_child("RewardXp", true, false) as SpinBox).value = 77
	(holder.find_child("RewardGold", true, false) as SpinBox).value = 33
	(holder.find_child("Relationships_0", true, false).find_child("Amount", true, false) as SpinBox).value = 4
	var closing := _text_edit_with(holder, str(quest["stages"][0]["completion_dialogue"]))
	closing.text = NEW_CLOSING; closing.text_changed.emit()
	_assert(quest["rewards"]["xp"] == 77 and quest["rewards"]["gold"] == 33 and quest["rewards"]["relationships"][0]["amount"] == 4 and quest["stages"][0]["completion_dialogue"] == NEW_CLOSING, "rewards and the closing line are edited through the quest inspector")
	main.database_mgr.mark_dirty("quest", "quest_wildflower_commission")
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "and saved through the engine-checked save path")

	var after := _route(fixture, "dialogue_quest_reward", arguments)
	_assert(after.get("ok", false) and after.get("completed", false) and int(after.get("xp_paid", 0)) == 77 and int(after.get("gold_gained", 0)) == 33 and int(after.get("relationships", {}).get("village_elder", 0)) == 4, "edited: the same route now pays 77 XP, 33 gold and 4 trust (%s)" % _brief_quest(after))
	_assert(NEW_CLOSING in str(after.get("output", "")), "and the elder closes with the edited line")


# --- discovery / advancement --------------------------------------------------------
# Pick up a rose quartz: it makes two discoveries and pays the gem grant (15)
# and the discovery grant (15 each) -- 45 XP. Edited: the discovery renamed
# (DiscoveryInspector), and in the live Ruleset dialog the discovery grant
# raised to 40 and the gem grant's message rewritten: 95 XP, new words.

const NEW_DISCOVERY_NAME := "Pink Crystal Seam"
const NEW_GEM_MESSAGE := "A gem for the valley ledger."

func _discovery_advancement_route() -> void:
	print("\n[discovery / advancement: edit a discovery and the ruleset's grants, then find it]")
	var arguments := ["item=item_rose_quartz"]
	var before := _route(shipped, "discovery_advancement", arguments)
	_assert(before.get("ok", false) and before.get("discoveries", []) == ["fieldcraft_basics", "rose_quartz"] and int(before.get("xp_gained", 0)) == 45, "shipped: a rose quartz makes two discoveries and pays 45 XP (%s)" % _brief_discovery(before))

	var discovery: Dictionary = main.database_mgr.discoveries["rose_quartz"]
	var holder := VBoxContainer.new(); root.add_child(holder)
	var inspector := DiscoveryInspector.new(holder, main.database_mgr); inspectors.append(inspector)
	inspector.build("rose_quartz", discovery)
	var name_field := _line_edit_with(holder, str(discovery["name"]))
	name_field.text = NEW_DISCOVERY_NAME; name_field.text_changed.emit(NEW_DISCOVERY_NAME)
	_assert(discovery["name"] == NEW_DISCOVERY_NAME, "the discovery is renamed through the discovery inspector")
	main.database_mgr.mark_dirty("discovery", "rose_quartz")
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "and saved through the engine-checked save path")

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	var discovery_grant := _grant_card(rules, "discovery_made")
	var gem_grant := _grant_card(rules, "item_gem")
	_assert(rules.visible and discovery_grant != null and gem_grant != null, "the Ruleset dialog opens from the editor with both grants")
	if discovery_grant == null or gem_grant == null: return
	(discovery_grant.find_child("XP", true, false) as SpinBox).value = 40
	var message: LineEdit = gem_grant.find_child("Message", true, false)
	message.text = NEW_GEM_MESSAGE; message.text_changed.emit(NEW_GEM_MESSAGE)
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	var paid := {}
	for grant in ruleset["advancement"]["grants"]: paid[str(grant.get("id", ""))] = grant
	var shipped_rules: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(shipped.path_join("rules/ruleset.json")))
	var shipped_ids: Array = shipped_rules["advancement"]["grants"].map(func(grant): return str(grant["id"]))
	# The dialog found its grant cards by node name, which Godot makes unique by
	# renaming every sibling after the first: this save kept 1 of 15 grants.
	_assert(paid.keys() == shipped_ids, "every one of the %d grants survives the save, in order (got %d)" % [shipped_ids.size(), paid.size()])
	_assert(paid.has("discovery_made") and paid.has("item_gem") and int(paid["discovery_made"]["xp"]) == 40 and str(paid["item_gem"].get("message", "")) == NEW_GEM_MESSAGE, "the grants are saved by the Ruleset dialog (staged, engine-validated)")

	var after := _route(fixture, "discovery_advancement", arguments)
	_assert(after.get("ok", false) and int(after.get("xp_gained", 0)) == 95, "edited: the same find now pays 95 XP (%s)" % _brief_discovery(after))
	var told := str(after.get("output", ""))
	_assert(NEW_DISCOVERY_NAME in told and NEW_GEM_MESSAGE in told, "and the player is told the new discovery name and grant message")


# --- characters / social ----------------------------------------------------------
# Give Elder Thorne a rose quartz: any gift (1) plus the gem tag (1) is 2
# points, a Stranger with no discount. Edited in the Ruleset dialog's
# Relationships section: the gem tag is worth 12, and the 10-point tier is
# renamed "Neighbour" with an 8% discount -- the same gift now reaches it.

func _gift_relationship_route() -> void:
	print("\n[characters / social: edit gift values and the ladder, then give a gift]")
	var arguments := ["item=item_rose_quartz", "npc=Elder Thorne", "template=village_elder"]
	var before := _route(shipped, "gift_relationship", arguments)
	_assert(before.get("ok", false) and int(before.get("points", 0)) == 2 and before.get("tier", "") == "Stranger" and is_zero_approx(float(before.get("discount", 1))), "shipped: one gem gift is 2 points, a Stranger with no discount (%s)" % _brief_gift(before))

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	var social: SocialSection = rules.social_section
	var acquaintance: Node = null
	for row in social.tier_rows.get_children():
		if int((row.get_node("Min") as SpinBox).value) == 10: acquaintance = row
	_assert(acquaintance != null, "the Relationships section shows the 10-point tier")
	if acquaintance == null: return
	var label: LineEdit = acquaintance.get_node("Label")
	label.text = "Neighbour"; label.text_changed.emit("Neighbour")
	(acquaintance.get_node("Discount") as SpinBox).value = 0.08
	for row in social.tag_rows.get_children():
		if (row.get_node("Tag") as LineEdit).text == "gem": (row.get_node("Points") as SpinBox).value = 12
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	_assert(int(ruleset["social"]["gift_tag_values"]["gem"]) == 12 and ruleset["social"]["tiers"][2]["label"] == "Neighbour", "saved by the Ruleset dialog (staged, engine-validated)")

	var after := _route(fixture, "gift_relationship", arguments)
	_assert(after.get("ok", false) and int(after.get("points", 0)) == 13 and after.get("tier", "") == "Neighbour" and is_equal_approx(float(after.get("discount", 0)), 0.08), "edited: the same gift is 13 points, a Neighbour with 8%% off (%s)" % _brief_gift(after))
	_assert("Neighbour" in str(after.get("output", "")), "and the player is told the new tier name")


# --- item generation / loot ---------------------------------------------------
# Ten wolves drop their own pelts and fangs, and now and then a gem from the
# ambient pools -- never an alexandrite. Edited in the Ruleset dialog's Loot
# section: a new pool for wolves alone, certain to drop one on every kill.

func _kill_loot_route() -> void:
	print("
[item generation / loot: add an ambient loot pool, then kill]")
	var arguments := ["target=wolf", "kills=10"]
	var before := _route(shipped, "kill_loot", arguments)
	_assert(before.get("ok", false) and int(before.get("killed", 0)) == 10 and int(before.get("drops", {}).get("item_alexandrite", 0)) == 0, "shipped: ten wolves drop no alexandrite (%s)" % _brief_loot(before))

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	var loot: LootSection = rules.loot_section
	var pools_before := loot.pool_rows.get_child_count()
	loot._add_pool({"chance": 0.0})
	var card: Node = loot.pool_rows.get_child(loot.pool_rows.get_child_count() - 1)
	(card.find_child("Chance", true, false) as SpinBox).value = 1.0
	var only: LineEdit = card.find_child("npc_template_ids", true, false)
	only.text = "wolf"; only.text_changed.emit("wolf")
	loot._add_entry(card.get_node("Entries"), {"item_id": "item_alexandrite", "weight": 1})
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	var pools: Array = ruleset["loot"]["ambient_pools"]
	_assert(pools.size() == pools_before + 1 and pools[-1].get("npc_template_ids") == ["wolf"] and pools[-1]["entries"][0]["item_id"] == "item_alexandrite", "saved by the Ruleset dialog (staged, engine-validated)")

	var after := _route(fixture, "kill_loot", arguments)
	_assert(after.get("ok", false) and int(after.get("drops", {}).get("item_alexandrite", 0)) == 10, "edited: every wolf now drops an alexandrite (%s)" % _brief_loot(after))
	_assert(int(after.get("drops", {}).get("item_wolf_pelt", 0)) > 0, "and still drops its own loot table")


# --- world / hazards ------------------------------------------------------------
# Thirty seconds in the swamp's quicksand pit: six strikes of 6 (9 physical,
# raised by the swamp's mist, less a new character's defense). Edited in the
# room's environment panel: 20 damage every 2.5 seconds.

func _hazard_route() -> void:
	print("
[world / hazards: edit a room's hazard, then stand in it]")
	var arguments := ["region=swamp", "room=quicksand_pit", "ticks=300"]
	var before := _route(shipped, "hazard_exposure", arguments)
	_assert(before.get("ok", false) and int(before.get("strikes", 0)) == 6 and int(before.get("health_lost", 0)) == 36, "shipped: thirty seconds in the pit is six strikes, 36 health (%s)" % _brief_hazard(before))

	main._load_region_now("swamp.json", true)
	var pit: Dictionary = main.region_mgr.data.rooms["quicksand_pit"]
	var holder := VBoxContainer.new(); root.add_child(holder)
	var panel := RoomEnvironmentPanel.new(); inspectors.append(panel)
	panel.build(holder, pit, main.database_mgr)
	(holder.find_child("HazardDamage", true, false) as SpinBox).value = 20
	(holder.find_child("HazardTickInterval", true, false) as SpinBox).value = 2.5
	_assert(int(pit["properties"]["hazard_damage"]) == 20 and is_equal_approx(float(pit["properties"]["hazard_tick_interval"]), 2.5), "the damage and interval are edited through the environment panel")
	main.region_mgr.mark_room_dirty("quicksand_pit")
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "and saved through the engine-checked save path")

	var after := _route(fixture, "hazard_exposure", arguments)
	_assert(after.get("ok", false) and int(after.get("strikes", 0)) == 12 and int(after.get("health_lost", 0)) == 240, "edited: the same thirty seconds is twelve strikes, 240 health (%s)" % _brief_hazard(after))


# --- world / spawners -------------------------------------------------------------
# Five minutes in the swamp: its spawner fills the region with its own mix at
# levels 2-4 and never a cave bear. Edited in the region's spawner inspector:
# cave bears only, all at level 4.

func _spawner_route() -> void:
	print("
[world / spawners: edit a region's spawner, then let the world run]")
	var arguments := ["region=swamp", "ticks=3000"]
	var before := _route(shipped, "region_spawns", arguments)
	_assert(before.get("ok", false) and int(before.get("spawned", 0)) > 0 and not before.get("templates", {}).has("cave_bear"), "shipped: the swamp spawns its own mix, no cave bear (%s)" % _brief_spawns(before))

	var region: Dictionary = main.region_mgr.data
	_assert(str(region.get("region_id", "")) == "swamp", "the swamp is the open region")
	var holder := VBoxContainer.new(); root.add_child(holder)
	var spawner := SpawnerInspector.new(); inspectors.append(spawner)
	spawner.build(holder, region, main.database_mgr)
	# The add row's picker offers what is not yet in the table; choose the bear.
	for node in holder.find_children("*", "Button", true, false):
		if str(node.text) == "Add Monster":
			var picker: OptionButton = node.get_parent().get_child(0)
			for index in picker.item_count:
				if str(picker.get_item_metadata(index)) == "cave_bear": picker.select(index)
			node.pressed.emit()
			break
	# Remove every other creature, one row at a time (each removal rebuilds the list).
	var removed := true
	var passes := 0
	while removed and passes < 20:
		removed = false; passes += 1
		for node in holder.find_children("*", "Button", true, false):
			if str(node.text) != "x" or node.is_queued_for_deletion() or node.get_parent().get_parent().is_queued_for_deletion(): continue
			var row_picker: OptionButton = node.get_parent().get_child(0)
			if str(row_picker.get_item_metadata(row_picker.selected)) == "cave_bear": continue
			node.pressed.emit(); removed = true; break
	var ranges: Array = []
	for node in holder.find_children("*", "SpinBox", true, false):
		if node.get_parent().get_child(0) is Label and str(node.get_parent().get_child(0).text) == "Level Range:": ranges.append(node)
	for spin in ranges: (spin as SpinBox).value = 4
	_assert(region["spawner"]["monster_types"].keys() == ["cave_bear"] and int(region["spawner"]["level_range"][0]) == 4 and int(region["spawner"]["level_range"][1]) == 4, "cave bears only, at level 4, through the spawner inspector (%s)" % JSON.stringify(region["spawner"]))
	main.region_mgr.mark_region_dirty()
	var saved: bool = main._save_everything()
	if not saved: print("    refusal: ", _error_text().left(400))
	_assert(saved, "and saved through the engine-checked save path")

	var after := _route(fixture, "region_spawns", arguments)
	_assert(after.get("ok", false) and int(after.get("spawned", 0)) > 0 and after.get("templates", {}).keys() == ["cave_bear"] and after.get("levels", []) == [4.0], "edited: the same five minutes spawn only level-4 cave bears (%s)" % _brief_spawns(after))


# --- system policy / weather ------------------------------------------------------
# Two hundred summer weather changes on the engine's own table: clear, cloudy,
# rain and storm. Edited in the Ruleset dialog: fantasy gets its own seasonal
# table, where summer is clear or a heatwave (three to one), and the heatwave a
# description the `weather` command shows.

const HEATWAVE := "The air shimmers over baking ground."

func _weather_route() -> void:
	print("
[system policy / weather: give summer its own table, then let the weather turn]")
	var arguments := ["season=summer", "changes=200"]
	var before := _route(shipped, "weather_rolls", arguments)
	var shipped_types: Array = before.get("weather", {}).keys(); shipped_types.sort()
	_assert(before.get("ok", false) and shipped_types == ["clear", "cloudy", "rain", "storm"], "shipped: summer rolls the engine's clear, cloudy, rain and storm (%s)" % _brief_weather(before))

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	var section: WeatherChancesSection = rules.weather_chances_section
	section.own_table.button_pressed = true
	for row in section.season_rows["summer"].get_children():
		if (row.get_node("Type") as LineEdit).text != "clear": (row.get_node("Remove") as Button).pressed.emit()
		else: (row.get_node("Weight") as SpinBox).value = 1
	section._add_row(section.season_rows["summer"], "heatwave", 3)
	rules._add_string_map_row(rules.weather_description_rows, "heatwave", HEATWAVE, "weather type", "flavor text")
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	_assert(JSON.stringify(SaveIO._normalize_numbers(ruleset["weather"]["chances"]["summer"])) == JSON.stringify({"clear": 1, "heatwave": 3}) and ruleset["weather"]["descriptions"].get("heatwave") == HEATWAVE, "saved by the Ruleset dialog (staged, engine-validated)")

	var after := _route(fixture, "weather_rolls", arguments)
	var counts: Dictionary = after.get("weather", {})
	var edited_types: Array = counts.keys(); edited_types.sort()
	_assert(after.get("ok", false) and edited_types == ["clear", "heatwave"] and int(counts.get("heatwave", 0)) > int(counts.get("clear", 0)), "edited: summer is now clear or, mostly, a heatwave (%s)" % _brief_weather(after))
	if "Heatwave" in str(after.get("report", "")):
		_assert(HEATWAVE in str(after.get("report", "")), "and the weather command describes it in the set's words")


# --- system policy / economy -----------------------------------------------------------
# The same theft, caught the same way, before the crime edit below: the fine
# is charged in "gold". Renamed in the Ruleset dialog's World Rules, the same
# fine is charged in crowns.

func _economy_route() -> void:
	print("
[system policy / economy: rename the currency, then pay a fine in it]")
	var arguments := ["vendor=merchant", "item=healing potion"]
	var before := _route(shipped, "crime_theft", arguments)
	_assert("20 gold fine" in str(before.get("output", "")), "shipped: the fine is 20 gold (%s)" % str(before.get("output", "")).replace("
", " "))

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	var currency: LineEdit = rules.world_rules_section.controls["economy.currency_name"]
	currency.text = "crowns"; currency.text_changed.emit("crowns")
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	_assert(ruleset.get("economy", {}).get("currency_name") == "crowns", "saved by the Ruleset dialog (staged, engine-validated)")

	var after := _route(fixture, "crime_theft", arguments)
	_assert("20 crowns fine" in str(after.get("output", "")) and int(after.get("fine", 0)) == 20, "edited: the same fine is charged in crowns (%s)" % str(after.get("output", "")).replace("
", " "))


# --- system policy / crime ----------------------------------------------------------
# Steal a healing potion from Talia's stall until someone notices: the Guard
# Captain does, and a small theft is a fine. Edited in the Ruleset dialog's
# Crime section: any theft worth 5 or more means a cell, so the same catch
# ends in jail with nothing paid.

func _crime_route() -> void:
	print("
[system policy / crime: lower the jail threshold, then get caught stealing]")
	var arguments := ["vendor=merchant", "item=healing potion"]
	var before := _route(shipped, "crime_theft", arguments)
	_assert(before.get("ok", false) and before.get("caught_on") != null and int(before.get("fine", 0)) > 0 and not before.get("jailed", true), "shipped: caught, a fine, no cell (%s)" % _brief_crime(before))

	main.ui_mgr.side_panel.request_edit_ruleset.emit()
	await process_frame
	var rules = main.ui_mgr.ruleset_editor
	(rules.crime_section.controls["consequences.custody_value_threshold"] as SpinBox).value = 5
	rules.confirmed.emit()
	await process_frame
	var ruleset: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(fixture.path_join("rules/ruleset.json")))
	_assert(int(ruleset["crime"]["consequences"]["custody_value_threshold"]) == 5 and is_equal_approx(float(ruleset["crime"]["consequences"]["fine_rate"]), 2.0), "saved by the Ruleset dialog (staged, engine-validated); the fine rate untouched")

	var after := _route(fixture, "crime_theft", arguments)
	_assert(after.get("ok", false) and after.get("caught_on") == before.get("caught_on") and after.get("jailed", false) and int(after.get("fine", -1)) == 0, "edited: the same catch now ends in a cell, nothing paid (%s)" % _brief_crime(after))


func _brief_crime(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "caught on %s, fine %s, jailed %s, reputation %s" % [str(result.get("caught_on")), str(result.get("fine")), str(result.get("jailed")), str(result.get("reputation"))]


func _brief_weather(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "%s; report: %s" % [str(result.get("weather")), str(result.get("report", "")).replace("
", " ")]


func _brief_spawns(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "%s spawned: %s, levels %s" % [str(result.get("spawned")), str(result.get("templates")), str(result.get("levels"))]


func _brief_hazard(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "%s s, %s strikes, %s health: %s" % [str(result.get("seconds")), str(result.get("strikes")), str(result.get("health_lost")), str(result.get("lines", []).slice(0, 1))]


func _brief_loot(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "killed %s, ambient %s" % [str(result.get("killed")), str(result.get("ambient"))]


func _brief_gift(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "points %s, tier %s, discount %s" % [str(result.get("points")), str(result.get("tier")), str(result.get("discount"))]


func _brief_discovery(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "discoveries %s, xp %s" % [str(result.get("discoveries")), str(result.get("xp_gained"))]


func _grant_card(rules: Node, grant_id: String) -> Node:
	for card in rules.advancement_grant_rows.get_children():
		var field = card.find_child("GrantId", true, false)
		if field != null and str(field.text) == grant_id: return card
	return null


func _line_edit_with(node: Node, text: String) -> LineEdit:
	if node is LineEdit and node.text == text: return node
	for child in node.get_children():
		var found := _line_edit_with(child, text)
		if found != null: return found
	return null


func _brief_quest(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "learned %s, completed %s, xp %s, gold %s, trust %s" % [str(result.get("recipe_learned")), str(result.get("completed")), str(result.get("xp_paid")), str(result.get("gold_gained")), str(result.get("relationships", {}).get("village_elder"))]


func _text_edit_with(node: Node, text: String) -> TextEdit:
	if node is TextEdit and node.text == text: return node
	for child in node.get_children():
		var found := _text_edit_with(child, text)
		if found != null: return found
	return null


func _brief_craft(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "gathered %s, crafted %s, healed %s, left %s" % [str(result.get("gathered")), str(result.get("crafted")), str(result.get("healed")), str(result.get("result_left"))]


# The SpinBox in the row a Label names ("Quantity").
func _spin_beside(node: Node, label: String) -> SpinBox:
	for child in node.get_children():
		if child is Label and str(child.text).strip_edges() == label:
			for sibling in child.get_parent().get_children():
				if sibling is SpinBox: return sibling
		var found := _spin_beside(child, label)
		if found != null: return found
	return null


# The SpinBox in the generic property row whose key field reads `key`.
func _spin_beside_key(node: Node, key: String) -> SpinBox:
	for child in node.get_children():
		if child is LineEdit and str(child.text) == key:
			for sibling in child.get_parent().get_children():
				if sibling is SpinBox: return sibling
		var found := _spin_beside_key(child, key)
		if found != null: return found
	return null


# --- helpers ------------------------------------------------------------------

func _route(content_set: String, route: String, arguments: Array) -> Dictionary:
	var output: Array = []
	var python := repo.path_join(".venv/Scripts/python.exe")
	if not FileAccess.file_exists(python): python = repo.path_join(".venv/bin/python")
	OS.execute(python, [repo.path_join("toolkit/edited_route_check.py"), content_set, route] + arguments, output, true)
	var text := "\n".join(output)
	var at := text.rfind("ROUTE_RESULT ")
	if at < 0:
		print("    route output: ", text.right(400))
		return {"ok": false, "error": "no ROUTE_RESULT"}
	var parsed = JSON.parse_string(text.substr(at + "ROUTE_RESULT ".length()).get_slice("\n", 0))
	return parsed if parsed is Dictionary else {"ok": false, "error": "unparseable"}


func _brief(result: Dictionary) -> String:
	if not result.get("ok", false): return "error: %s" % str(result.get("error", ""))
	return "health %s -> %s, died %s" % [str(result.get("health_before")), str(result.get("health_after")), str(result.get("died"))]


func _error_text() -> String:
	var text := ""
	for node in _labels(main.ui_mgr.error_modal):
		text += str(node.dialog_text if node is AcceptDialog else node.text) + "\n"
	return text


func _labels(node: Node) -> Array:
	var out: Array = []
	if node is Label or node is RichTextLabel or node is AcceptDialog: out.append(node)
	for child in node.get_children(): out.append_array(_labels(child))
	return out


func _copy(source: String, destination: String):
	DirAccess.make_dir_recursive_absolute(destination)
	for name in DirAccess.get_files_at(source):
		if not name.ends_with(".bak"): DirAccess.copy_absolute(source.path_join(name), destination.path_join(name))
	for name in DirAccess.get_directories_at(source):
		if not name in ["editor", "saves"]: _copy(source.path_join(name), destination.path_join(name))


func _assert(condition: bool, message: String):
	print("  %s %s" % ["OK" if condition else "FAIL", message])
	if not condition: failures += 1
