# scripts/data/EncounterSchema.gd
#
# What an encounter zone (`data/encounters/*.json`, `engine/world/encounters.py`) may carry. The engine owns the vocabulary;
# this is the editor's copy, and `schema_parity_smoke.gd` checks it against `toolkit/engine_vocabulary_dump.py`. Reached
# through `preload`, not a `class_name`: a headless check must not depend on the editor having scanned a new class.
extends RefCounted

const KEYS := ["region", "rooms", "monsters", "chance", "count", "cooldown", "message", "note"]
const REPEL_TAG := "repel"
