extends Control
class_name OnboardingController

## First-run onboarding overlay.
##
## Shows a welcome panel with quick-start tips the first time the game runs.
## Completion is tracked by the presence of MARKER_PATH (user://onboarding_complete).
##
## Public API used by main_controller.gd:
##   onboarding.show_if_first_run()   — call from _ready(); shows panel if never seen
##   onboarding.show_panel()          — force-show (re-read via "onboarding show" command)
##   onboarding.dismiss()             — hide and write marker (button callback + command)
##   onboarding.is_complete() -> bool — true if the marker file exists

const MARKER_PATH := "user://onboarding_complete"

@onready var dismiss_button: Button = $CenterContainer/Panel/VBox/DismissButton
@onready var tips_label: RichTextLabel = $CenterContainer/Panel/VBox/TipsLabel


func _ready() -> void:
	dismiss_button.pressed.connect(dismiss)
	visible = false


func show_if_first_run() -> void:
	"""Show the panel only if the player has never dismissed it before."""
	if not is_complete():
		show_panel()


func show_panel() -> void:
	"""Show the onboarding overlay unconditionally."""
	visible = true


func dismiss() -> void:
	"""Hide the overlay and record completion so it is not shown again."""
	visible = false
	_write_marker()


func is_complete() -> bool:
	"""Return true if the player has already completed (dismissed) onboarding."""
	return FileAccess.file_exists(MARKER_PATH)


func _write_marker() -> void:
	var file := FileAccess.open(MARKER_PATH, FileAccess.WRITE)
	if file == null:
		push_warning("OnboardingController: cannot write marker %s (err %d)" % [
			MARKER_PATH, FileAccess.get_open_error()
		])
		return
	file.store_string("1")
	file.close()
