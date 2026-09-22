# scripts/data/NPCVocabulary.gd
#
# Two engine-owned, closed vocabularies an NPC template names directly:
# `faction` (`engine/config/config_world.py`, resolved per set by
# `engine/world/factions.py`) and `behavior_type` (`engine/config/config_npc.py`'s
# `NPC_BEHAVIOR_TYPES`, dispatched by `ai/dispatcher.py`). Both fail *quietly* on
# a bad value -- an unknown faction becomes a bystander, an unknown behaviour
# stands still forever -- which is exactly why `content_set.py`'s
# `_validate_npc_faction_and_behavior` only warns, and why offering the real
# list here is worth doing.
#
# Hardcoded rather than read from a subprocess at edit time, the same tradeoff
# `DialogueSchema` makes for conditions and effects: the editor cannot import
# Python, so this is a copy, and `schema_parity_smoke.gd` asserts it against
# `toolkit/engine_vocabulary_dump.py` so the copy cannot drift silently.

class_name NPCVocabulary
extends RefCounted

const BUILT_IN_FACTIONS := ["player", "friendly", "neutral", "hostile", "player_minion"]
const FACTION_DISPOSITIONS := ["hostile", "friendly", "neutral", "player"]

# `player_minion` defaults to `player` on purpose -- a summoned thing fights for
# you (`engine/config/config_world.py::FACTION_DEFAULT_DISPOSITIONS`).
const FACTION_DEFAULT_DISPOSITIONS := {
	"player": "player",
	"player_minion": "player",
	"friendly": "friendly",
	"neutral": "neutral",
	"hostile": "hostile",
}

const BEHAVIOR_TYPES := [
	"stationary", "wanderer", "aggressive", "patrol", "follower", "scheduled",
	"healer", "minion",
]


## Every faction this content set's ruleset gives a disposition to, engine's five
## first so a set's own names can never redefine what `friendly` means by
## accident -- mirrors `engine/world/factions.py::dispositions()`.
static func resolved_dispositions(ruleset: Dictionary) -> Dictionary:
	var factions_section: Dictionary = {}
	var factions_value = ruleset.get("factions", {})
	if factions_value is Dictionary:
		factions_section = factions_value

	var overrides: Dictionary = {}
	var overrides_value = factions_section.get("overrides", {})
	if overrides_value is Dictionary:
		overrides = overrides_value

	var resolved := {}
	for faction_id in BUILT_IN_FACTIONS:
		var override = overrides.get(faction_id, "")
		if override is String and str(override).strip_edges() != "":
			resolved[faction_id] = str(override).strip_edges()
		else:
			resolved[faction_id] = FACTION_DEFAULT_DISPOSITIONS.get(faction_id, "neutral")

	var extra = factions_section.get("extra", [])
	if extra is Array:
		for entry in extra:
			if not (entry is Dictionary):
				continue
			var faction_id := str(entry.get("id", "")).strip_edges()
			var disposition := str(entry.get("disposition", "")).strip_edges()
			if faction_id != "" and disposition != "":
				resolved[faction_id] = disposition

	return resolved


## The raw ruleset this content set declares, or an empty dict if it has none.
## Read directly rather than through `RulesetDraft` -- this only ever reads, and a
## missing or unparseable ruleset should degrade to "just the engine's five", not
## a load error in an inspector that has nothing to do with saving one.
static func load_ruleset() -> Dictionary:
	var path := DataRoot.ruleset_path()
	if not FileAccess.file_exists(path):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}
