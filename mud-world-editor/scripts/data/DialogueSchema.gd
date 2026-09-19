# scripts/data/DialogueSchema.gd
#
# The engine's conversation vocabulary, in one place.
#
# A dialogue graph is `data/dialogue/<one graph>.json`: nodes are what the NPC
# says, choices are what the player can say back. It is the one content system
# that can gate a line on what the player has done, teach a recipe mid-sentence,
# or let a negotiation go two ways -- and it had no authoring surface at all, so
# the nine shipped graphs were hand-written JSON.
#
# Two vocabularies decide whether a graph works, and both belong to the engine:
#
#   * conditions -- `engine/conditions.py`, the same evaluator that gates titles
#     and quest availability. An unrecognised kind fails *closed*, which is the
#     right behaviour and also means a typo silently closes a conversation rather
#     than opening it; the editor offers the known kinds and their fields so the
#     typo never happens.
#   * effects -- `engine/dialogue/effects.py` (`KNOWN_EFFECTS`).
#
# `engine/server/content_set.py::_validate_dialogue_content` checks references,
# condition kinds and effect keys, so anything authored through this schema is
# checked by the engine before a player can walk into it.

class_name DialogueSchema
extends RefCounted

# Field kinds: string, int, bool, item_id, npc_id, quest_id, recipe_id, region_id,
# list_of_string, json.
const CONDITION_KINDS := {
	"has_item": {
		"label": "Carrying an item",
		"fields": {"item_id": "item_id", "quantity": "int"},
		"note": "Counts the item in the player's inventory.",
	},
	"knows_recipe": {
		"label": "Knows a recipe",
		"fields": {"recipe_id": "recipe_id"},
		"note": "In `Player.known_recipe_ids`.",
	},
	"skill_at_least": {
		"label": "Skill at least",
		"fields": {"skill": "string", "value": "int"},
		"note": "Use-based skill level (see the ruleset's skills).",
	},
	"spell_known": {
		"label": "Knows an ability",
		"fields": {"spell_id": "string"},
		"note": "The ability id, from the set's ability definitions.",
	},
	"relationship_at_least": {
		"label": "Trust at least",
		"fields": {"npc_id": "npc_id", "value": "int"},
		"note": "Accepts an NPC template id or a live instance id.",
	},
	"quest_completed": {
		"label": "Quest completed",
		"fields": {"quest_id": "quest_id"},
		"note": "Matches the template id, instance id prefix, or the title.",
	},
	"quest_active": {
		"label": "Quest active",
		"fields": {"quest_id": "quest_id"},
		"note": "Same matching rules as quest_completed.",
	},
	"discovery": {
		"label": "Has discovered",
		"fields": {"discovery_id": "string"},
		"note": "An entry in the player's discovery ledger.",
	},
	"visited_region": {
		"label": "Has been to a region",
		"fields": {"region_id": "region_id"},
		"note": "Seeded silently for the region a character starts in.",
	},
	"in_region": {
		"label": "Is in a region",
		"fields": {"region_id": "region_id"},
		"note": "True only while the player is standing there.",
	},
	"level_at_least": {
		"label": "Level at least",
		"fields": {"value": "int"},
		"note": "Progression level.",
	},
	"gold_at_least": {
		"label": "Currency at least",
		"fields": {"value": "int"},
		"note": "The set's own currency, whatever it is called.",
	},
	"title_earned": {
		"label": "Title earned",
		"fields": {"title_id": "string"},
		"note": "Titles are conferred, never chosen.",
	},
	"background": {
		"label": "Background",
		"fields": {"background_id": "string"},
		"note": "Where the character began.",
	},
	"flag": {
		"label": "Flag set",
		"fields": {"flag": "string"},
		"note": "Written by `set_flag` effects elsewhere in content.",
	},
	"time_of_day": {
		"label": "Time of day",
		"fields": {"value": "string"},
		"note": "The world clock's current period.",
	},
	"season": {
		"label": "Season",
		"fields": {"value": "string"},
		"note": "The world clock's current season.",
	},
}

# Composite conditions. They nest, so the editor shows them as JSON rather than
# as a form that would have to grow a tree editor to stay honest.
const COMPOSITES := {
	"all": "Every nested condition must hold.",
	"any": "At least one nested condition must hold.",
	"not": "The nested condition must not hold.",
}

# Effect payload shapes, as `engine/dialogue/effects.py` reads them.
const EFFECTS := {
	"start_quest": {"label": "Start a quest", "shape": "quest id, or a list of them", "kind": "quest_id"},
	"start_campaign": {"label": "Start a campaign", "shape": "campaign id", "kind": "string"},
	"advance_quest": {"label": "Advance a quest stage", "shape": "quest id, or a list of them", "kind": "quest_id"},
	"complete_quest": {"label": "Complete a quest", "shape": "quest id, or a list of them", "kind": "quest_id"},
	"grant_recipe": {"label": "Teach a recipe", "shape": "recipe id, or a list of them", "kind": "string"},
	"grant_discovery": {"label": "Grant a discovery", "shape": "discovery id, or a list", "kind": "string"},
	"teach_spell": {"label": "Teach an ability", "shape": "ability id, or a list of them", "kind": "string"},
	"give_item": {"label": "Give an item", "shape": "item id, or {item_id, quantity}", "kind": "item_id"},
	"take_item": {"label": "Take an item", "shape": "item id, or {item_id, quantity}", "kind": "item_id"},
	"give_gold": {"label": "Give currency", "shape": "a number", "kind": "int"},
	"adjust_relationship": {"label": "Change trust", "shape": "{amount}", "kind": "json"},
	"set_flag": {"label": "Set a flag", "shape": "flag name, or {name, value}", "kind": "string"},
	"reveal_exit": {"label": "Open a hidden exit", "shape": "{room: \"region:room\", direction}", "kind": "json"},
	"move_npc": {"label": "Move an NPC", "shape": "{npc_id, region_id, room_id}", "kind": "json"},
	"give_rewards": {"label": "Give a reward bundle", "shape": "{xp, gold, items: [...]}", "kind": "json"},
}

const CHECK_FIELDS := {
	"skill": "string",
	"difficulty": "int",
	"success_node": "node_id",
	"fail_node": "node_id",
}


static func condition_kinds() -> Array:
	var ids := CONDITION_KINDS.keys()
	ids.sort()
	return ids


static func has_condition_kind(kind: String) -> bool:
	return CONDITION_KINDS.has(kind)


static func condition_fields(kind: String) -> Dictionary:
	return CONDITION_KINDS.get(kind, {}).get("fields", {})


static func condition_note(kind: String) -> String:
	return str(CONDITION_KINDS.get(kind, {}).get("note", "Not a condition kind the editor knows; shown as authored."))


static func effect_keys() -> Array:
	var ids := EFFECTS.keys()
	ids.sort()
	return ids


static func has_effect(key: String) -> bool:
	return EFFECTS.has(key)


# The hint shown beside an effect's value: what the engine expects there.
static func effect_shape(key: String) -> String:
	return str(EFFECTS.get(key, {}).get("shape", "JSON"))


static func effect_kind(key: String) -> String:
	return str(EFFECTS.get(key, {}).get("kind", "json"))


# GDScript's `or` yields a *bool*, unlike Python's, so `x or ""` used as a value
# is a trap: it produces "true"/"false" strings. Optional ids read out of content
# go through here instead -- content JSON has keys that exist with a null value.
static func value_of(value) -> String:
	return str(value) if value != null else ""


# A node reference, i.e. `next_node` and a check's success/fail targets. Content
# validation reports a target that does not exist, so these are shown as pickers
# over the graph's own node ids.
static func choice_targets(choice: Dictionary) -> Array:
	var targets: Array = []
	var next_node := value_of(choice.get("next_node", ""))
	if next_node != "":
		targets.append(next_node)
	var check = choice.get("check")
	if check is Dictionary:
		for key in ["success_node", "fail_node"]:
			var target := value_of(check.get(key, ""))
			if target != "":
				targets.append(target)
	return targets
