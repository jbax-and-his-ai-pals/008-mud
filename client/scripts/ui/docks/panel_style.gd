# scripts/ui/docks/panel_style.gd
#
# The look shared by every panel in the game view: a slightly darker fill, a thin light border and
# rounded corners. One place, so the game log and the dock cards cannot drift apart. Reached
# through `preload`.
extends RefCounted

const FILL := Color(0.2, 0.2, 0.21, 1.0)
const BORDER := Color(0.46, 0.46, 0.5, 1.0)
const RADIUS := 10


## `margin` is the space between the border and what is inside it.
static func card(margin: int = 8) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = FILL
	style.border_color = BORDER
	style.set_border_width_all(1)
	style.set_corner_radius_all(RADIUS)
	style.anti_aliasing = true
	style.content_margin_left = margin
	style.content_margin_right = margin
	style.content_margin_top = margin - 2
	style.content_margin_bottom = margin - 2
	return style
