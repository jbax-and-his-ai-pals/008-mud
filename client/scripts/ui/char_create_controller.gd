extends Control
class_name CharCreateController

## Character creation overlay.
##
## Shown automatically after connecting when the server requires a character
## and the session does not already have one.  Also triggered defensively when
## the server returns a "No character yet" text response.
##
## Public API:
##   show_dialog()   — display the overlay and focus the name input
##   hide_dialog()   — hide the overlay without submitting
##   signal name_submitted(name: String) — emitted when the player confirms

signal name_submitted(name: String)

const NAME_MIN_LEN := 3
const NAME_MAX_LEN := 24

@onready var name_input: LineEdit       = $CenterContainer/Panel/VBox/NameInput
@onready var error_label: Label         = $CenterContainer/Panel/VBox/ErrorLabel
@onready var create_button: Button      = $CenterContainer/Panel/VBox/ButtonRow/CreateButton
@onready var cancel_button: Button      = $CenterContainer/Panel/VBox/ButtonRow/CancelButton

var _name_re: RegEx = RegEx.new()


func _ready() -> void:
	_name_re.compile("^[A-Za-z0-9 _'\\-]+$")
	create_button.pressed.connect(_on_create_pressed)
	cancel_button.pressed.connect(hide_dialog)
	name_input.text_submitted.connect(func(_t: String) -> void: _on_create_pressed())
	visible = false


func show_dialog() -> void:
	"""Display the overlay and focus the name input."""
	error_label.text = ""
	error_label.visible = false
	name_input.text = ""
	visible = true
	# Defer focus so the overlay is fully laid out before grab_focus.
	name_input.call_deferred("grab_focus")


func hide_dialog() -> void:
	"""Hide the overlay without submitting."""
	visible = false


func _on_create_pressed() -> void:
	var raw: String = name_input.text.strip_edges()
	var err := _validate(raw)
	if err != "":
		error_label.text = err
		error_label.visible = true
		return
	hide_dialog()
	name_submitted.emit(raw)


func _validate(name: String) -> String:
	if name.length() < NAME_MIN_LEN:
		return "Name must be at least %d characters." % NAME_MIN_LEN
	if name.length() > NAME_MAX_LEN:
		return "Name must be at most %d characters." % NAME_MAX_LEN
	if _name_re.search(name) == null:
		return "Name may only contain letters, numbers, spaces, _, -, and '."
	return ""
