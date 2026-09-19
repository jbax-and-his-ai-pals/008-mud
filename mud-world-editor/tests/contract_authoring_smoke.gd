# tests/contract_authoring_smoke.gd
#
# An item's contract is authorable, and what the editor writes is what the engine
# accepts.
#
# The editor could already *read* `data/contracts/world_contracts.json`
# (`ContractCatalog`, used by `content_source_check.gd`) but no inspector offered
# a single field from it: `item_family` and `generation_profile` are the two the
# content validator checks on every template, and neither had a control. Run with:
#
#   godot --headless --path mud-world-editor --script tests/contract_authoring_smoke.gd
#
# The fixture deliberately names its bands `scrap`/`serviceable` and
# `micro`/`bulk` rather than the fantasy set's names, because "the picker offers
# what this content set declares" is the property under test -- a hardcoded list
# would pass a test written against `common`/`rare` and fail this one.

extends SceneTree

const SaveIO = preload("res://scripts/data/SaveIO.gd")

var failure_count := 0
var repo_root: String = ""
var content_set_root: String = ""
var data_root: String = ""
var python_exe: String = ""
var holders: Array = []
var catalog: ContractCatalog


func _init() -> void:
	repo_root = ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	content_set_root = ProjectSettings.globalize_path("res://").path_join("../tmp/contract_authoring/content_set")
	data_root = content_set_root.path_join("data")
	python_exe = _python_from_args()
	if python_exe == "":
		python_exe = _probe_python()
	_build_fixture()
	DataRoot._resolved = content_set_root
	DataRoot._source = "test fixture"

	_check_the_catalog_reads_the_set()
	_check_family_picker_writes_the_family()
	_check_class_mismatch_is_named()
	_check_rarity_comes_from_the_profile()
	_check_browser_sections()

	if python_exe != "":
		_check_the_engine_accepts_what_this_wrote()
	else:
		print("\n[engine validation]")
		print("  skip  no Python interpreter found; pass --python <path>")

	if failure_count > 0:
		push_error("contract authoring smoke failed (%d)" % failure_count)
	quit(1 if failure_count > 0 else 0)


# --- cases -------------------------------------------------------------------

func _check_the_catalog_reads_the_set() -> void:
	print("\n[the catalog]")
	var database := DatabaseManager.new()
	catalog = database.catalog
	_assert(catalog.schema_version == ContractCatalog.KNOWN_SCHEMA_VERSION, "the contracts load")
	_assert(catalog.issues.is_empty(), "without issues: %s" % str(catalog.issues))
	_assert(catalog.family_ids().has("salvaged_part"), "families are indexed")
	_assert(catalog.attack_profiles.has("kinetic_round"), "attack profiles are indexed")
	_assert(catalog.defense_profiles.has("impact_shell"), "defense profiles are indexed")
	_assert(catalog.resources.has("charge"), "resources are indexed")
	_assert(catalog.abilities.has("overcharge"), "abilities are indexed")

	_assert(catalog.family_capabilities("salvaged_part").has("generated_instance"),
		"a family's capabilities are readable")
	_assert(catalog.profiles_for_family("salvaged_part") == ["salvage_grade"],
		"its profiles are enumerable: %s" % str(catalog.profiles_for_family("salvaged_part")))
	_assert(catalog.tier_ids("salvage_grade", "rarity_tiers") == ["scrap", "serviceable", "clean"],
		"and the bands it declares: %s" % str(catalog.tier_ids("salvage_grade", "rarity_tiers")))
	_assert(catalog.families_for_class("Junk").has("salvaged_part"),
		"families can be asked for by engine class")
	_assert(catalog.family_ids_for_capability("generated_instance") == ["salvaged_part"],
		"and by capability")


func _check_family_picker_writes_the_family() -> void:
	print("\n[a template's family]")
	var database := DatabaseManager.new()
	var item: Dictionary = database.items["item_probe"]
	_assert(str(item.get("item_family", "")) == "", "the fixture template starts with no family")

	var holder := _inspector_for(item, database)
	var picker := holder.find_child("FamilyPicker", true, false) as OptionButton
	_assert(picker != null, "the inspector offers a family picker")
	if picker == null:
		return
	var ids: Array = []
	for index in range(picker.item_count):
		ids.append(picker.get_item_text(index))
	_assert(ids.has("salvaged_part"), "listing this content set's families: %s" % str(ids))

	var chosen := ids.find("salvaged_part")
	picker.select(chosen)
	picker.item_selected.emit(chosen)
	_assert(str(item.get("item_family", "")) == "salvaged_part",
		"choosing one writes `item_family` on the template")


func _check_class_mismatch_is_named() -> void:
	print("\n[family against legacy type]")
	var database := DatabaseManager.new()
	var item: Dictionary = database.items["item_probe"]
	item["type"] = "Item"
	item["item_family"] = "salvaged_part"  # a Junk family
	var holder := _inspector_for(item, database)
	var summary := holder.find_child("ContractSummary", true, false) as Label
	_assert(summary != null, "the inspector shows what the family means")
	if summary == null:
		return
	_assert(summary.text.contains("Junk"), "naming the class the engine will build: %s" % summary.text)
	_assert(summary.text.contains("legacy `type` says Item"),
		"and saying that the family overrides the template's own type: %s" % summary.text)
	_assert(summary.text.contains("generated_instance"), "and listing the capabilities")


func _check_rarity_comes_from_the_profile() -> void:
	print("\n[intrinsic rarity]")
	var database := DatabaseManager.new()
	var item: Dictionary = database.items["item_probe"]
	item["item_family"] = "salvaged_part"
	var holder := _inspector_for(item, database)

	var rarity := holder.find_child("RarityPicker", true, false) as OptionButton
	_assert(rarity != null, "a generating family gets a rarity picker")
	if rarity == null:
		return
	var options: Array = []
	for index in range(rarity.item_count):
		options.append(rarity.get_item_text(index))
	_assert(options.has("serviceable"), "offering this profile's bands: %s" % str(options))
	_assert(not options.has("legendary"),
		"and not another content set's band names: %s" % str(options))

	var chosen := options.find("clean")
	rarity.select(chosen)
	rarity.item_selected.emit(chosen)
	_assert(str(item.get("rarity", "")) == "clean", "choosing one writes `rarity`")


func _check_browser_sections() -> void:
	print("\n[the contract browser]")
	var sections := catalog.sections()
	_assert(sections.size() == 7, "every contract kind has a section (%d)" % sections.size())
	var titles: Array = []
	for section in sections:
		titles.append(str(section["title"]))
	_assert(str(titles[0]).begins_with("Item families"), "families come first: %s" % str(titles))
	var families: Array = sections[0]["entries"]
	_assert(not families.is_empty(), "with entries")
	var detail := str(families[0].get("detail", "")) if families.size() > 0 else ""
	_assert(detail.contains("class:"), "each entry says what the family builds: %s" % detail)


# The proof, as everywhere else: the engine has the last word.
func _check_the_engine_accepts_what_this_wrote() -> void:
	print("\n[the engine's verdict]")
	var database := DatabaseManager.new()
	# Write a family onto the item through the inspector, then save and validate.
	var holder := _inspector_for(database.items["item_probe"], database)
	var picker := holder.find_child("FamilyPicker", true, false) as OptionButton
	if picker == null:
		return
	var ids: Array = []
	for index in range(picker.item_count):
		ids.append(picker.get_item_text(index))
	var chosen := ids.find("salvaged_part")
	picker.select(chosen)
	picker.item_selected.emit(chosen)
	database.mark_dirty("item", "item_probe")
	var saved := database.save_all()
	_assert(saved.get("ok", false), "the edited item saves: %s" % str(saved.get("errors", [])))

	var result := EngineValidator.run(content_set_root, repo_root, python_exe)
	_assert(result.get("ran", false), "the validator runs: %s" % result.get("error", ""))
	var contract_errors: Array = []
	for issue in result.get("issues", []):
		var path := str(issue.get("path", ""))
		if path.contains("items") or path.contains("contract"):
			contract_errors.append(issue)
	_assert(contract_errors.is_empty(), "a family chosen here validates: %s" % str(contract_errors))
	_assert(result.get("ok", false), "and the content set as a whole passes: %s" % str(result.get("issues", [])))


# --- helpers -----------------------------------------------------------------

func _inspector_for(item: Dictionary, database: DatabaseManager) -> VBoxContainer:
	var holder := VBoxContainer.new()
	root.add_child(holder)
	holders.append(holder)
	var inspector := ItemInspector.new()
	inspector.build(holder, item, database)
	return holder


func _build_fixture() -> void:
	_remove_recursive(content_set_root)
	DirAccess.make_dir_recursive_absolute(data_root.path_join("items"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("npcs"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("regions"))
	DirAccess.make_dir_recursive_absolute(data_root.path_join("contracts"))
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("rules"))

	SaveIO.write_json(content_set_root.path_join("content_set.manifest.json"), {
		"id": "contract_fixture", "title": "Contract Fixture", "version": "0.1.0",
		"manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
		"paths": {
			"content_root": "data",
			"ruleset": "rules/ruleset.json",
			"presentation": "presentation/default.json",
		},
		"start": {"scenario_id": "fixture", "region_id": "fixture", "room_id": "start"},
		"capabilities": ["inventory"],
	})
	DirAccess.make_dir_recursive_absolute(content_set_root.path_join("presentation"))
	SaveIO.write_json(content_set_root.path_join("presentation/default.json"), {
		"presentation_id": "contract_fixture", "display_name": "Contract Fixture",
	})
	SaveIO.write_json(content_set_root.path_join("rules/ruleset.json"), {"ruleset_id": "contract_fixture"})
	SaveIO.write_json(data_root.path_join("regions/fixture.json"), {
		"region_id": "fixture", "rooms": {"start": {"name": "Start", "exits": {}}},
	})
	SaveIO.write_json(data_root.path_join("items/library.json"), {
		"item_probe": {"name": "probe", "type": "Item", "value": 10, "weight": 0.1},
	})
	SaveIO.write_json(data_root.path_join("contracts/world_contracts.json"), {
		"schema_version": 1,
		"label": "Contract fixture",
		"resources": [
			{"id": "health", "label": "Health", "kind": "vital", "max_stat": "constitution"},
			{"id": "charge", "label": "Charge", "short": "CHG", "kind": "ability",
			 "regenerates": true, "regeneration_stat": "intelligence", "max_stat": "intelligence"},
		],
		"item_families": [
			{"id": "salvaged_part", "label": "Salvaged part", "item_class": "Junk",
			 "capabilities": ["generated_instance", "vendor_trash"],
			 "generation_profile": "salvage_grade", "icon_style": "pick"},
			{"id": "kinetic_sidearm", "label": "Kinetic sidearm", "item_class": "Weapon",
			 "capabilities": ["equippable", "weapon"], "attack_profile": "kinetic_round",
			 "icon_style": "blade"},
		],
		"generation_profiles": [
			{"id": "salvage_grade", "item_family": "salvaged_part", "property_prefix": "component",
			 "name_template": "{size} {quality} {base}",
			 "rarity_tiers": [
				{"id": "scrap", "rank": 1, "weight": 80},
				{"id": "serviceable", "rank": 2, "weight": 28},
				{"id": "clean", "rank": 3, "weight": 8},
			 ],
			 "size_tiers": [
				{"id": "micro", "label": "micro", "score": 1, "value_multiplier": 0.5, "weight_multiplier": 0.4},
				{"id": "bulk", "label": "bulk", "score": 3, "value_multiplier": 2.1, "weight_multiplier": 2.4},
			 ],
			 "quality_tiers": [
				{"id": "worn", "label": "worn", "score": 1, "value_multiplier": 0.4},
				{"id": "true", "label": "true", "score": 2, "value_multiplier": 1.0},
			 ]},
		],
		"attack_profiles": [
			{"id": "kinetic_round", "damage_type": "kinetic", "weapon_damage_type": "piercing",
			 "damage": 7, "cooldown": 1.8},
		],
		"defense_profiles": [
			{"id": "impact_shell", "defense": 2, "material": "synthetic"},
		],
		"effect_packets": [
			{"id": "discharge", "kind": "damage", "value": 11},
		],
		"abilities": [
			{"id": "overcharge", "effect_packet": "discharge",
			 "cost": {"resource": "charge", "amount": 6}, "cooldown": 6.0,
			 "target_type": "enemy", "level_required": 1},
		],
	})


func _remove_recursive(path: String) -> void:
	var dir := DirAccess.open(path)
	if dir == null:
		return
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		var child := path.path_join(name)
		if dir.current_is_dir():
			_remove_recursive(child)
		else:
			DirAccess.remove_absolute(child)
		name = dir.get_next()
	dir.list_dir_end()
	DirAccess.remove_absolute(path)


func _python_from_args() -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size()):
		if args[index] == "--python" and index + 1 < args.size():
			return args[index + 1]
	return ""


func _probe_python() -> String:
	var candidates := [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
		"python",
	]
	for candidate in candidates:
		if candidate == "python" or FileAccess.file_exists(candidate):
			return candidate
	return ""


func _assert(condition: bool, message: String) -> void:
	if condition:
		print("  ok   ", message)
	else:
		failure_count += 1
		push_error("FAIL: " + message)
