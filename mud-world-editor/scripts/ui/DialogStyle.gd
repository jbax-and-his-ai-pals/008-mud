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
