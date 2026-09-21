# scripts/ui/modals/CreateContentSetDialog.gd
#
# The form for a new content set. Everything it decides lives in
# `ContentSetScaffold`; this is the fields, the live validation and the report.
#
# Two things it deliberately shows rather than hides:
#
# * **What it will copy.** A new set is a copy of a set the author names, so the
#   dialog says which one and that its rules and presentation come with it. The
#   whole risk of this flow is a copied ruleset carrying a vocabulary into a world
#   it does not fit, and an author who did not notice the picker is how that
#   happens quietly.
# * **What the copied ruleset still demands.** `ContentSetScaffold` returns notes
#   when a source's ruleset requires something a scaffold cannot invent (every
#   mapped hazard placed in some room, for instance). They are shown after a
#   successful create, not swallowed: the set opens, and the author knows what it
#   still needs.

class_name CreateContentSetDialog
extends AcceptDialog

signal content_set_created(path, result)

var id_field: LineEdit
var title_field: LineEdit
var source_picker: OptionButton
var copy_rules_check: CheckBox
var status_label: Label
var source_hint: Label
var rules_hint: Label
var create_button: Button

var _sets_root: String = ""
# Set once the set exists. The dialog then reports what was written instead of
# closing on the spot, because the notes below are the part an author must not
# miss -- "the rules you copied require six hazards to be placed" is not something
# to discover three sessions later.
var _created_path: String = ""
var _created_result: Dictionary = {}

func setup(sets_root: String) -> void:
	set_target_root(sets_root)
	title = "New content set"
	ok_button_text = "Create"
	min_size = Vector2i(520, 380)
	# The dialog hides itself only when the set was actually created: a failed
	# create keeps the message beside the fields it is about.
	dialog_hide_on_ok = false

	var vbox := VBoxContainer.new()
	vbox.custom_minimum_size = Vector2(500, 300)
	vbox.add_theme_constant_override("separation", 8)

	var intro := _hint("A new content set starts as a copy of one you pick: its rules, presentation and opening come with it, and its own world begins empty.")
	vbox.add_child(intro)

	vbox.add_child(_label("Id (the directory name, and what the engine calls this set)"))
	id_field = LineEdit.new()
	id_field.placeholder_text = "new_frontier"
	id_field.text_changed.connect(func(_text): _validate())
	vbox.add_child(id_field)

	vbox.add_child(_label("Title (what an author sees)"))
	title_field = LineEdit.new()
	title_field.placeholder_text = "New Frontier"
	vbox.add_child(title_field)

	vbox.add_child(_label("Copy the rules and presentation from"))
	source_picker = OptionButton.new()
	source_picker.item_selected.connect(func(_index): _on_source_changed())
	vbox.add_child(source_picker)

	source_hint = _hint("")
	vbox.add_child(source_hint)

	# The one choice with a consequence the author cannot see from the fields. A
	# ruleset names the world it was written for, so copying one without that world
	# leaves every named thing unresolved -- and Validate says so, loudly, forever.
	copy_rules_check = CheckBox.new()
	copy_rules_check.text = "Copy its rules too"
	copy_rules_check.button_pressed = false
	copy_rules_check.toggled.connect(func(_pressed): _on_rules_toggled())
	vbox.add_child(copy_rules_check)
	rules_hint = _hint("")
	vbox.add_child(rules_hint)

	status_label = _hint("")
	vbox.add_child(status_label)
	vbox.add_child(HSeparator.new())

	add_child(vbox)
	confirmed.connect(_on_create_confirmed)
	# The dialog's own OK button is disabled until the id is usable, so the
	# commonest mistake cannot be submitted at all.
	register_text_enter(id_field)
	register_text_enter(title_field)


## Where a new set is created. `setup()` passes the one place sets live beside a
## checkout; a check points it at scratch state so driving the dialog does not
## write into the repository's `content_sets/`.
func set_target_root(path: String) -> void:
	_sets_root = path


## Repopulate from the sets beside this checkout. Called every time the dialog
## opens, so a set created a moment ago is offered as a source.
func refresh(source_sets: Array) -> void:
	source_picker.clear()
	for path in source_sets:
		source_picker.add_item(str(path).get_file())
		source_picker.set_item_metadata(source_picker.item_count - 1, path)
	if source_sets.is_empty():
		source_picker.add_item("no content sets found beside this checkout")
	_created_path = ""
	_created_result = {}
	ok_button_text = "Create"
	id_field.editable = true
	title_field.editable = true
	source_picker.disabled = false
	copy_rules_check.disabled = false
	copy_rules_check.button_pressed = false
	_on_source_changed()
	id_field.text = ""
	title_field.text = ""
	status_label.text = ""
	_validate()
	id_field.grab_focus()


func _on_source_changed() -> void:
	var path := _selected_source()
	if path == "":
		source_hint.text = "There is nothing to copy from, so a new set cannot be created yet."
		_validate()
		return
	source_hint.text = "The presentation and opening come from %s. Its regions, items and NPCs do not: the new world starts with one empty room." % str(path).get_file()
	_on_rules_toggled()


func _on_rules_toggled() -> void:
	if copy_rules_check.button_pressed:
		rules_hint.text = "The rules you copy name that world's items, quests and NPCs. This set has none of them, so Validate will list every one until you author your own. Choose this to start a close copy, not a new world."
		rules_hint.modulate = Color(0.85, 0.7, 0.5)
	else:
		rules_hint.text = "The new set starts with a ruleset that declares nothing, so the engine's own defaults apply and the set validates straight away."
		rules_hint.modulate = Color(0.65, 0.68, 0.74)
	_validate()


func _validate() -> void:
	# Once the set exists the form is a receipt: the id it was created with is by
	# definition already taken, so validating again would disable the button that
	# now means "open it".
	if _created_path != "":
		return
	var identity := id_field.text.strip_edges()
	var problem := ContentSetScaffold.id_problem(identity, _sets_root)
	if _selected_source() == "":
		problem = "Pick a set to copy from."
	status_label.text = problem
	status_label.modulate = Color(0.85, 0.55, 0.45) if problem != "" else Color(0.6, 0.7, 0.6)
	if create_button == null:
		create_button = get_ok_button()
	if create_button != null:
		create_button.disabled = problem != ""


func _on_create_confirmed() -> void:
	# Second press, after the set exists: this is the "open it" step.
	if _created_path != "":
		var created := _created_path
		var result := _created_result
		_created_path = ""
		hide()
		content_set_created.emit(created, result)
		return

	var identity := id_field.text.strip_edges()
	if ContentSetScaffold.id_problem(identity, _sets_root) != "":
		return
	var source := _selected_source()
	if source == "":
		return
	var outcome := ContentSetScaffold.create(
		identity, title_field.text, source, _sets_root, copy_rules_check.button_pressed
	)
	if not outcome.get("ok", false):
		var errors: Array = outcome.get("errors", [])
		status_label.text = "Could not create it: %s" % " ".join(errors)
		status_label.modulate = Color(0.85, 0.55, 0.45)
		# Left open on purpose: the message belongs beside the fields it is about.
		return

	_created_path = str(outcome.get("path", ""))
	_created_result = outcome
	_report(outcome, source)


## What was written, and what is still owed. The fields are locked rather than
## cleared: the dialog is now a receipt, and the OK button is "Open it".
func _report(result: Dictionary, source: String) -> void:
	id_field.editable = false
	title_field.editable = false
	source_picker.disabled = true
	copy_rules_check.disabled = true
	ok_button_text = "Open it"

	var lines: Array = [
		"Created %s from %s." % [str(result.get("path", "")).get_file(), str(source).get_file()],
		"%d file(s) copied, %d written." % [Array(result.get("copied", [])).size(), Array(result.get("wrote", [])).size()],
	]
	var notes: Array = result.get("notes", [])
	if not notes.is_empty():
		lines.append("")
		for note in notes:
			lines.append("Still to do: " + str(note))
	status_label.text = "\n".join(lines)
	status_label.modulate = Color(0.7, 0.8, 0.7)


func _selected_source() -> String:
	if source_picker == null or source_picker.selected < 0:
		return ""
	return str(source_picker.get_item_metadata(source_picker.selected))


func _label(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size", 12)
	return label


func _hint(text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 11)
	label.modulate = Color(0.65, 0.68, 0.74)
	return label
