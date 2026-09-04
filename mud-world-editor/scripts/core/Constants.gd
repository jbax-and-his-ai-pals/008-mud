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

const DIR_VECTORS = { 
	DIR_N: Vector2(0, -1), DIR_S: Vector2(0, 1), 
	DIR_E: Vector2(1, 0), DIR_W: Vector2(-1, 0), 
	DIR_NE: Vector2(1, -1), DIR_NW: Vector2(-1, -1), 
	DIR_SE: Vector2(1, 1), DIR_SW: Vector2(-1, 1), 
	DIR_UP: Vector2(0.5, -0.5), DIR_DOWN: Vector2(-0.5, 0.5), 
	DIR_IN: Vector2(0.2, 0.2), DIR_OUT: Vector2(-0.2, -0.2),
	DIR_CLIMB: Vector2(0.5, -0.5), DIR_DIVE: Vector2(0.5, 0.5) 
}

const INV_DIR_MAP = {
	DIR_N: DIR_S, DIR_S: DIR_N, 
	DIR_E: DIR_W, DIR_W: DIR_E, 
	DIR_UP: DIR_DOWN, DIR_DOWN: DIR_UP, 
	DIR_IN: DIR_OUT, DIR_OUT: DIR_IN,
	DIR_NE: DIR_SW, DIR_SW: DIR_NE,
	DIR_NW: DIR_SE, DIR_SE: DIR_NW,
	DIR_CLIMB: DIR_DIVE, DIR_DIVE: DIR_CLIMB
}

const ANCHORS = {
	DIR_N: Vector2(0, -50), DIR_S: Vector2(0, 50),
	DIR_E: Vector2(100, 0), DIR_W: Vector2(-100, 0),
	DIR_NE: Vector2(100, -50), DIR_NW: Vector2(-100, -50),
	DIR_SE: Vector2(100, 50), DIR_SW: Vector2(-100, 50),
	DIR_UP: Vector2(80, -50), DIR_CLIMB: Vector2(80, -50),
	DIR_DOWN: Vector2(80, 50), DIR_DIVE: Vector2(80, 50),
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
