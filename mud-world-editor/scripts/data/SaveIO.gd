# scripts/data/SaveIO.gd
#
# The one place the editor writes a content file, and the one place that checks
# it actually landed.
#
# Every writer used to look like this:
#
#     var f = FileAccess.open(path, FileAccess.WRITE)
#     if f: f.store_string(JSON.stringify(payload, "\t"))
#
# with no `else` and no return value. A read-only file, a full disk or a bad
# path was therefore indistinguishable from success: the caller cleared the
# dirty flag, the Save button greyed out as "saved", and the author's edits were
# gone with no message anywhere they were looking.
#
# Two conventions also live here because they are the same decision in every
# writer: content files are 4-space indented (the editor used tabs, so any save
# reformatted a whole file and destroyed its `git blame`), and what is written is
# read back before it counts as written.
#
# Key order is preserved deliberately. `JSON.stringify`'s `sort_keys` defaults to
# true, so every editor save used to alphabetise every object in the file it
# touched -- `region_id` landed after `name`, `properties` blocks were reordered,
# and a one-field edit still produced a whole-file diff.

class_name SaveIO
extends RefCounted

const INDENT := "    "
const SORT_KEYS := false


# Write `payload` as JSON to `path`. Returns {"ok": bool, "error": String}.
#
# The read-back is deliberate: a write that silently failed is exactly the
# failure this exists to catch, and it is invisible to `FileAccess` itself.
static func write_json(path: String, payload) -> Dictionary:
	var text := JSON.stringify(payload, INDENT, SORT_KEYS)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return _failure(path, "could not open for writing (%s)" % _error_text(FileAccess.get_open_error()))
	file.store_string(text)
	file.close()

	if not FileAccess.file_exists(path):
		return _failure(path, "the file does not exist after writing")
	var check := FileAccess.open(path, FileAccess.READ)
	if check == null:
		return _failure(path, "the file was written but could not be read back (%s)"
			% _error_text(FileAccess.get_open_error()))
	var written := check.get_as_text()
	check.close()
	if written != text:
		return _failure(path, "what was written does not match what is on disk (wrote %d characters, read %d)"
			% [text.length(), written.length()])
	if JSON.parse_string(written) == null:
		return _failure(path, "the file read back is not valid JSON")
	return {"ok": true, "error": ""}


static func _failure(path: String, reason: String) -> Dictionary:
	var message := "Could not write %s: %s" % [path, reason]
	push_error(message)
	return {"ok": false, "error": message}


static func _error_text(code: int) -> String:
	return error_string(code) if code != OK else "unknown error"
