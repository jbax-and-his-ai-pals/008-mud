# scripts/ui/DialogStyle.gd
# Shared look for the built-in AcceptDialog/ConfirmationDialog popups (confirm
# prompts, error messages, quit/unsaved-changes dialogs). Custom bespoke windows
# like DistrictModal keep their own layout, but use these same colors so the
# whole app reads as one theme.
class_name DialogStyle
extends RefCounted

const COLOR_BG = Color("172033")
const COLOR_BORDER = Color("4f82bd")
const COLOR_TITLE = Color("8fceff")
const COLOR_TEXT = Color("b7c5d8")
const COLOR_CONFIRM = Color("23744d")
const COLOR_DISCARD = Color("5a3d48")
const COLOR_NEUTRAL = Color("293548")
const COLOR_DANGER = Color("7a2f2f")
const COLOR_BUTTON_TEXT = Color("e8eef7")

# Panel background, border, title and body-text colors for any AcceptDialog or
# ConfirmationDialog. ok_color lets a caller pick the OK button's meaning
# (confirm/save vs. a destructive default action).
static func style_window(dialog: Window, ok_color: Color = COLOR_CONFIRM) -> void:
	var panel := StyleBoxFlat.new()
	panel.bg_color = COLOR_BG
	panel.border_color = COLOR_BORDER
	panel.set_border_width_all(1)
	panel.set_corner_radius_all(8)
	panel.shadow_color = Color(0, 0, 0, 0.5)
	panel.shadow_size = 12
	panel.content_margin_left = 20
	panel.content_margin_right = 20
	panel.content_margin_top = 18
	panel.content_margin_bottom = 16
	dialog.add_theme_stylebox_override("panel", panel)
	# AcceptDialog is an embedded Window: its title bar is themed separately from
	# the content panel. Styling both makes one coherent rounded surface instead
	# of a stock gray frame wrapped around an otherwise themed dialog.
	var titlebar := StyleBoxFlat.new()
	titlebar.bg_color = COLOR_BG
	titlebar.border_color = COLOR_BORDER
	titlebar.border_width_left = 1
	titlebar.border_width_top = 1
	titlebar.border_width_right = 1
	titlebar.corner_radius_top_left = 8
	titlebar.corner_radius_top_right = 8
	titlebar.content_margin_left = 20
	titlebar.content_margin_right = 14
	titlebar.content_margin_top = 8
	titlebar.content_margin_bottom = 8
	dialog.add_theme_stylebox_override("titlebar", titlebar)
	dialog.add_theme_stylebox_override("titlebar_unfocused", titlebar)
	dialog.add_theme_color_override("title_color", COLOR_TITLE)
	dialog.add_theme_font_size_override("title_font_size", 18)

	if dialog is AcceptDialog:
		var label: Label = dialog.get_label()
		if label:
			label.add_theme_color_override("font_color", COLOR_TEXT)
			label.add_theme_font_size_override("font_size", 14)
			label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		style_button(dialog.get_ok_button(), ok_color)
	if dialog is ConfirmationDialog:
		style_button(dialog.get_cancel_button(), COLOR_NEUTRAL)

# Size a dialog to its content each time it opens, clamped to the window it
# opens in, and centre it. An AcceptDialog grows to fit its content and never
# shrinks back, and a word-wrapped label measured before it has a width asks
# for one word per line -- so several dialogs opened thousands of pixels tall
# and ran off the bottom of the screen with their buttons.
static func fit_to_screen(dialog: Window) -> void:
	if dialog.has_meta("fits_screen"):
		return
	dialog.set_meta("fits_screen", true)
	dialog.visibility_changed.connect(func():
		if dialog.visible:
			_fit_after_layout(dialog)
	)


# The growth happens during the first layout passes after the dialog shows, so
# fitting at the moment it becomes visible is undone a frame later.
static func _fit_after_layout(dialog: Window) -> void:
	var tree := dialog.get_tree()
	if tree == null:
		return
	await tree.process_frame
	await tree.process_frame
	_fit(dialog)


static func _fit(dialog: Window) -> void:
	if not is_instance_valid(dialog) or not dialog.visible:
		return
	var parent := dialog.get_parent()
	if parent == null:
		return
	var wanted := dialog.get_contents_minimum_size()
	var width := maxf(float(dialog.size.x), wanted.x)
	var height := maxf(float(dialog.min_size.y), wanted.y)
	var screen := parent.get_viewport().get_visible_rect().size
	# A headless or placeholder viewport has no real size to clamp or centre in;
	# the dialog still drops back to its content's height.
	var real_screen := screen.y >= 300.0
	if real_screen:
		width = minf(width, screen.x * 0.92)
		height = minf(height, screen.y * 0.92)
	dialog.size = Vector2i(int(width), int(height))
	if real_screen:
		dialog.position = Vector2i(int((screen.x - width) / 2.0), int((screen.y - height) / 2.0))


static func style_button(button: Button, color: Color) -> void:
	if button == null: return
	var normal := StyleBoxFlat.new()
	normal.bg_color = color
	normal.set_border_width_all(1)
	normal.border_color = color.lightened(0.25)
	normal.set_corner_radius_all(4)
	normal.content_margin_left = 14; normal.content_margin_right = 14
	normal.content_margin_top = 6; normal.content_margin_bottom = 6
	var hover := normal.duplicate(); hover.bg_color = color.lightened(0.12)
	var pressed := normal.duplicate(); pressed.bg_color = color.darkened(0.12)
	button.add_theme_stylebox_override("normal", normal)
	button.add_theme_stylebox_override("hover", hover)
	button.add_theme_stylebox_override("pressed", pressed)
	button.add_theme_stylebox_override("focus", normal)
	button.add_theme_color_override("font_color", COLOR_BUTTON_TEXT)
	button.add_theme_color_override("font_hover_color", Color.WHITE)
