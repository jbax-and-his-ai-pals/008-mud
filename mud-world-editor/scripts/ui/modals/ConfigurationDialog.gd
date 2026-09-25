extends AcceptDialog

# Shared lifecycle for configuration forms. The baseline is the rendered form,
# so inherited/default values do not make a newly opened dialog dirty.
var _form_baseline: Array = []
var _discard_prompt: ConfirmationDialog
var _allow_close := false

func _install_guard():
	dialog_hide_on_ok = false
	add_cancel_button("Cancel")
	_discard_prompt = ConfirmationDialog.new()
	_discard_prompt.title = "Discard configuration changes?"
	_discard_prompt.dialog_text = "Your unsaved draft will be discarded. The saved configuration will not change."
	_discard_prompt.ok_button_text = "Discard Changes"
	add_child(_discard_prompt)
	_discard_prompt.confirmed.connect(func(): _allow_close = true; hide())
	visibility_changed.connect(func():
		if not visible and not _allow_close and _form_changed(): _restore_for_discard.call_deferred()
	)

func _restore_for_discard():
	# Put away by the quit prompt, not dismissed: it comes back on "Keep editing".
	if get_meta("parked", false): return
	if not is_inside_tree() or _allow_close or not _form_changed(): return
	popup_centered()
	_discard_prompt.popup_centered()

func _reset_form_baseline():
	_allow_close = false
	_remember_fields(self)
	_form_baseline = _form_state(self)

func _remember_fields(node: Node):
	if node == _discard_prompt: return
	if node is LineEdit or node is TextEdit: node.set_meta("loaded_value", node.text)
	elif node is OptionButton: node.set_meta("loaded_value", node.selected)
	elif node is CheckBox: node.set_meta("loaded_value", node.button_pressed)
	elif node is SpinBox: node.set_meta("loaded_value", node.value)
	for child in node.get_children(): _remember_fields(child)

func _field_changed(node: Control) -> bool:
	var value = node.text if node is LineEdit or node is TextEdit else (node.selected if node is OptionButton else (node.value if node is SpinBox else node.button_pressed))
	return value != node.get_meta("loaded_value", null)

func _put_path(data: Dictionary, path: String, value):
	var keys := path.split(".")
	var section := data
	for i in range(keys.size() - 1):
		if not section.get(keys[i]) is Dictionary: section[keys[i]] = {}
		section = section[keys[i]]
	section[keys[-1]] = value

func _form_changed() -> bool:
	return not _form_baseline.is_empty() and _form_state(self) != _form_baseline

func _form_state(node: Node) -> Array:
	var values: Array = []
	if node == _discard_prompt: return values
	if node is LineEdit or node is TextEdit: values.append([node.get_instance_id(), node.text])
	elif node is OptionButton: values.append([node.get_instance_id(), node.selected])
	elif node is CheckBox: values.append([node.get_instance_id(), node.button_pressed])
	elif node is SpinBox: values.append([node.get_instance_id(), node.value])
	for child in node.get_children(): values.append_array(_form_state(child))
	return values

func _input_errors(node: Node = null) -> Array:
	if node == null: node = self
	var errors: Array = []
	if node.has_meta("input_error") and str(node.get_meta("input_error")) != "": errors.append(str(node.get_meta("input_error")))
	for child in node.get_children(): errors.append_array(_input_errors(child))
	return errors

func _remove_row(row: Node):
	row.get_parent().remove_child(row)
	row.queue_free()

func _finish_save():
	_reset_form_baseline()
	_allow_close = true
	hide()
