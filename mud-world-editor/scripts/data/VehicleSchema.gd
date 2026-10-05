# scripts/data/VehicleSchema.gd
#
# What a vehicle (`data/vehicles/*.json`, `engine/world/vehicles.py`) may carry. The engine owns the vocabulary; this is
# the editor's copy, and `schema_parity_smoke.gd` checks it against `toolkit/engine_vocabulary_dump.py`. Reached through
# `preload`, not a `class_name`: a headless check must not depend on the editor having scanned a new class.
extends RefCounted

const KEYS := ["name", "description", "start", "board_text", "disembark_text", "lands_in_biomes", "note"]
