# scripts/data/TriggerSchema.gd
#
# What a trigger (`data/triggers/*.json`, `engine/world/triggers.py`) may carry: the
# events it can be `on`, its keys, and how often it fires. The engine owns the
# vocabulary; this is the editor's copy, and `schema_parity_smoke.gd` checks it against
# `toolkit/engine_vocabulary_dump.py`. Reached through `preload`, not a `class_name`:
# a headless check must not depend on the editor having scanned a new class.
extends RefCounted

const EVENTS := ["on_enter", "npc_killed", "room_cleared"]
# The fields each event's `on` may carry, and the ones it needs (`region` and `room`
# always come as a pair). Mirrors `engine/world/triggers.py`.
const EVENT_FIELDS := {
	"on_enter": ["region", "room"],
	"npc_killed": ["npc", "region", "room"],
	"room_cleared": ["region", "room"],
}
const EVENT_REQUIRED := {
	"on_enter": ["region", "room"],
	"npc_killed": ["npc"],
	"room_cleared": ["region", "room"],
}
const EVENT_LABELS := {
	"on_enter": "the player enters a room",
	"npc_killed": "a creature is killed",
	"room_cleared": "the last enemy in a room dies",
}
const KEYS := ["on", "when", "once", "effects", "note"]
const ONCE_MODES := ["player", "world"]
const DEFAULT_ONCE := "player"

# The three ways a trigger can repeat, as an author reads them. `once` absent means
# `player`; `false` means every time.
const ONCE_CHOICES := [
	{"value": "player", "label": "Once for each player"},
	{"value": "world", "label": "Once for the whole world"},
	{"value": "every", "label": "Every time"},
]


static func once_choice_of(trigger: Dictionary) -> String:
	var once = trigger.get("once", DEFAULT_ONCE)
	if once is bool and once == false:
		return "every"
	return str(once) if str(once) in ONCE_MODES else DEFAULT_ONCE


## Writes a choice back: `player` is the default, so it erases the key rather than
## writing what the engine assumes anyway.
static func set_once_choice(trigger: Dictionary, choice: String) -> void:
	match choice:
		"world": trigger["once"] = "world"
		"every": trigger["once"] = false
		_: trigger.erase("once")
