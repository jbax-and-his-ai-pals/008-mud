# scripts/data/SceneSchema.gd
#
# What a scene (`data/scenes/*.json`, `engine/world/scenes.py`) may carry: its keys, its beats' keys and the
# waits between them. The engine owns the vocabulary; this is the editor's copy, and `schema_parity_smoke.gd`
# checks it against `toolkit/engine_vocabulary_dump.py`. Reached through `preload`, not a `class_name`: a
# headless check must not depend on the editor having scanned a new class.
extends RefCounted

const KEYS := ["beats", "lock", "note"]
const BEAT_KEYS := ["text", "after", "pace", "effects"]
# The wait before a beat when it does not say: none before the first, two seconds between the rest.
const DEFAULT_FIRST_WAIT := 0.0
const DEFAULT_WAIT := 2.0
const MAX_WAIT := 600


static func default_wait(index: int) -> float:
	return DEFAULT_FIRST_WAIT if index == 0 else DEFAULT_WAIT
