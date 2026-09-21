# scripts/core/Constants.gd
class_name Constants
extends RefCounted

const DIR_N = "north"
const DIR_S = "south"
const DIR_E = "east"
const DIR_W = "west"
const DIR_NE = "northeast"
const DIR_NW = "northwest"
const DIR_SE = "southeast"
const DIR_SW = "southwest"
const DIR_UP = "up"
const DIR_DOWN = "down"
const DIR_IN = "in"
const DIR_OUT = "out"
const DIR_CLIMB = "climb"
const DIR_DIVE = "dive"
const DIR_DESCEND = "descend"
const DIR_SURFACE = "surface"

# The engine's authorable exit vocabulary. Keep this ordered for forms, but
# keep its reciprocal meaning in INV_DIR_MAP below; schema_parity_smoke compares
# that map with the engine's exported contract.
const AUTHORABLE_DIRECTIONS = [
	"north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest",
	"up", "down", "in", "out", "enter", "exit", "inside", "outside",
	"surface", "dive", "climb", "descend", "upstream", "downstream",
]

const DIR_VECTORS = { 
	DIR_N: Vector2(0, -1), DIR_S: Vector2(0, 1), 
	DIR_E: Vector2(1, 0), DIR_W: Vector2(-1, 0), 
	DIR_NE: Vector2(1, -1), DIR_NW: Vector2(-1, -1), 
	DIR_SE: Vector2(1, 1), DIR_SW: Vector2(-1, 1), 
	DIR_UP: Vector2(0.5, -0.5), DIR_DOWN: Vector2(-0.5, 0.5), 
	DIR_IN: Vector2(0.2, 0.2), DIR_OUT: Vector2(-0.2, -0.2),
	DIR_CLIMB: Vector2(0.5, -0.5), DIR_DESCEND: Vector2(0.5, 0.5),
	DIR_SURFACE: Vector2(0.5, -0.5), DIR_DIVE: Vector2(0.5, 0.5)
}

# Editor-only semantic defaults for exits that describe travel rather than a
# compass bearing. Authors can override these through `_editor_exit_layout`.
const MAP_DIRECTION_ALIASES = {
	"upstream": DIR_N,
	"downstream": DIR_S,
	"surface": DIR_UP,
	"descend": DIR_DOWN,
	"enter": DIR_IN,
	"exit": DIR_OUT,
	"inside": DIR_IN,
	"outside": DIR_OUT,
}

const INV_DIR_MAP = {
	DIR_N: DIR_S, DIR_S: DIR_N, 
	DIR_E: DIR_W, DIR_W: DIR_E, 
	DIR_UP: DIR_DOWN, DIR_DOWN: DIR_UP, 
	DIR_IN: DIR_OUT, DIR_OUT: DIR_IN,
	"enter": "exit", "exit": "enter",
	"inside": "outside", "outside": "inside",
	DIR_NE: DIR_SW, DIR_SW: DIR_NE,
	DIR_NW: DIR_SE, DIR_SE: DIR_NW,
	DIR_SURFACE: DIR_DIVE, DIR_DIVE: DIR_SURFACE,
	DIR_CLIMB: DIR_DESCEND, DIR_DESCEND: DIR_CLIMB,
	"upstream": "downstream", "downstream": "upstream",
}

# Reciprocal labels begin with a pair's authored emitter. The two parts swap
# only when the readable text itself flips 180 degrees.
static func format_reciprocal_label(first: String, second: String, from: Vector2, to: Vector2) -> String:
	var angle := (to - from).angle()
	var text_flipped := angle > PI * 0.5 or angle < -PI * 0.5
	return "%s ↔ %s" % [second.capitalize(), first.capitalize()] if text_flipped else "%s ↔ %s" % [first.capitalize(), second.capitalize()]

# Preserve the author-selected emitter when one exists. A caller can provide a
# legacy source from stable room-creation order when metadata is unavailable.
#
# Only for a genuinely mismatched pair, though (an "opening"/"out"-style custom
# reciprocal with no natural geometric opposite): swapping which position
# anchors the angle above shifts it by exactly PI, which reliably flips
# `text_flipped` for almost any angle -- except exactly at the +-90 degree
# boundary itself (a perfectly vertical or horizontal connector), where both
# the original and the PI-shifted angle land on the same side of the strict
# `>`/`<` comparison. `GraphRenderer._draw_label_rotated` always rotates the
# drawn text by the *unswapped* angle, so that one-value coincidence desyncs
# this label's word order from the actual rotation precisely when a room is
# moved to sit exactly north/south (or east/west) of its neighbour -- which is
# exactly the bug: two rooms connected due south swapped the direction words
# the instant they were grid-aligned, and moving either one room off that
# exact alignment made it correct again. A clean compass inverse has one
# always-correct physical placement regardless of authored_source, so it skips
# the swap entirely rather than relying on a boundary that can coincide.
static func format_reciprocal_pair_label(first_id: String, second_id: String, first_direction: String, second_direction: String, first_pos: Vector2, second_pos: Vector2, authored_source: String = "") -> String:
	var is_clean_inverse: bool = INV_DIR_MAP.get(first_direction.to_lower(), "") == second_direction.to_lower()
	if not is_clean_inverse:
		var use_second := authored_source == second_id
		if use_second:
			return format_reciprocal_label(second_direction, first_direction, second_pos, first_pos)
	return format_reciprocal_label(first_direction, second_direction, first_pos, second_pos)

const ANCHORS = {
	DIR_N: Vector2(0, -50), DIR_S: Vector2(0, 50),
	DIR_E: Vector2(100, 0), DIR_W: Vector2(-100, 0),
	DIR_NE: Vector2(100, -50), DIR_NW: Vector2(-100, -50),
	DIR_SE: Vector2(100, 50), DIR_SW: Vector2(-100, 50),
	DIR_UP: Vector2(80, -50), DIR_CLIMB: Vector2(80, -50), DIR_SURFACE: Vector2(80, -50),
	DIR_DOWN: Vector2(80, 50), DIR_DIVE: Vector2(80, 50), DIR_DESCEND: Vector2(80, 50),
	DIR_IN: Vector2(30, 30), DIR_OUT: Vector2(-30, -30)
}

# New Icon Definitions for Dynamic Visuals
const ICON_DEFINITIONS = {
	"dark": { "shape": "moon", "color": Color(0.6, 0.6, 0.8) },
	"water": { "shape": "drop", "color": Color(0.2, 0.6, 1.0) },
	"underwater": { "shape": "drop", "color": Color(0.2, 0.4, 0.8) },
	"danger": { "shape": "skull", "color": Color(1.0, 0.3, 0.3) },
	"boss": { "shape": "skull", "color": Color(1.0, 0.1, 0.1) },
	"safe_zone": { "shape": "shield", "color": Color(0.3, 0.8, 0.4) },
	"outdoors": { "shape": "tree", "color": Color(0.2, 0.6, 0.2) },
	"noisy": { "shape": "note", "color": Color(1.0, 0.8, 0.2) },
	"cold": { "shape": "flake", "color": Color(0.7, 0.9, 1.0) },
	"hot": { "shape": "flame", "color": Color(1.0, 0.5, 0.2) }
}
