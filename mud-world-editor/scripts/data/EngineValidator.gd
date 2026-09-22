# scripts/data/EngineValidator.gd
#
# Runs the engine's own validation over the content set the editor is editing.
#
# The editor can check the things it understands -- exit links, district
# membership, whether a room's biome is in the ruleset vocabulary -- but only the
# engine decides whether a content set loads. Before this existed there was no
# way to ask it from the editor at all: the "Validate" button checks links, and
# the one button that shelled out to a validator was pointed at a directory that
# stopped existing when the editor moved onto the shared content set.
#
# `toolkit/editor_validate.py` is the entry point: it runs the same checks
# `run_content_checks.py` runs and prints one JSON document, so the editor and CI
# cannot drift onto different verdicts. This class only finds the pieces, runs it,
# and parses the result; it never reimplements a check.

class_name EngineValidator
extends RefCounted

const SCRIPT_RELATIVE_PATH := "toolkit/editor_validate.py"
const RELEASE_GATE_RELATIVE_PATH := "run_content_checks.py"

# Issue sources, in the order the validator runs them, for display.
const SOURCE_LABELS := {
	"engine": "content set",
	"references": "references",
	"templates": "text templates",
	"stale": "stale references",
	"json": "file integrity",
	"setup": "setup",
}


# Returns {"ok": bool, "ran": bool, "error": String, "issues": Array, "counts": Dictionary}.
	# `ran` is false when the toolchain is missing, which is a setup problem and not a
# content problem -- the two are reported differently so neither is mistaken for
# the other.
static func run(content_set_root: String, repo_root: String, python_exe: String) -> Dictionary:
	var script_path := repo_root.path_join(SCRIPT_RELATIVE_PATH)
	if not FileAccess.file_exists(script_path):
		return _not_run("Validator not found at %s." % script_path)
	if python_exe == "":
		return _not_run("No Python interpreter was found to run %s." % SCRIPT_RELATIVE_PATH)

	var arguments := [script_path, content_set_root, "--json"]
	var output: Array = []
	var exit_code := OS.execute(python_exe, arguments, output, false)
	var raw: String = str(output[0]) if output.size() > 0 else ""

	# The validator prints the engine's own startup logging first, so the JSON
	# document is the last balanced object in the output rather than the whole of
	# it. Anything else means it failed before printing a verdict.
	var payload = last_json_object(raw)
	if typeof(payload) != TYPE_DICTIONARY:
		return _not_run(
			"The validator did not print a verdict (exit code %d).\n\n%s"
			% [exit_code, raw.strip_edges().right(2000)]
		)

	var issues: Array = payload.get("issues", []) if payload.get("issues") is Array else []
	# The engine owns issue wording; the editor only derives a stable key for an
	# author acknowledgement. Errors are never assigned a suppressible key.
	var annotated_issues: Array = []
	for raw_issue in issues:
		if raw_issue is Dictionary:
			var issue: Dictionary = raw_issue.duplicate(true)
			if str(issue.get("severity", "error")) == "warning":
				issue["warning_id"] = warning_id(issue)
			annotated_issues.append(issue)
		else:
			annotated_issues.append(raw_issue)
	return {
		"ok": bool(payload.get("ok", false)),
		"ran": true,
		"error": "",
		"issues": annotated_issues,
		"counts": payload.get("counts", {"error": 0, "warning": 0}),
		"ran_checks": payload.get("ran", []),
		"skipped": payload.get("skipped", []),
		"not_run": payload.get("not_run", {}),
		"exit_code": exit_code,
	}

static func warning_id(issue: Dictionary) -> String:
	return "content:%s:%s" % [str(issue.get("path", "")), str(issue.get("message", ""))]

# The repository gate deliberately remains separate from open-set validation:
# it audits every shipped set, themes, manifests and fixtures. The editor runs
# the existing canonical runner rather than growing a second implementation.
static func run_release_gate(repo_root: String, python_exe: String) -> Dictionary:
	var script_path := repo_root.path_join(RELEASE_GATE_RELATIVE_PATH)
	if python_exe == "": return _not_run("No Python interpreter was found to run %s." % RELEASE_GATE_RELATIVE_PATH)
	if not FileAccess.file_exists(script_path): return _not_run("Release gate not found at %s." % script_path)
	var output: Array = []
	var exit_code := OS.execute(python_exe, [script_path], output, false)
	return {
		"ran": true,
		"ok": exit_code == 0,
		"exit_code": exit_code,
		"report": str(output[0]) if not output.is_empty() else "The release gate produced no output.",
	}


static func _not_run(reason: String) -> Dictionary:
	return {"ok": false, "ran": false, "error": reason, "issues": [], "counts": {}, "ran_checks": [], "skipped": [], "not_run": {}}


# Parse the last complete JSON object in `text`. The engine logs on import, so the
# payload is not the first thing in the stream.
#
# The document is printed with `indent=2`, so its own braces are the only ones at
# column zero -- inner objects are indented. Anchoring on column zero is what keeps
# this quiet: every candidate is real JSON rather than a fragment handed to the
# parser to complain about.
#
# Public because `ReferenceIndex.gd` runs a second toolkit tool the same way and
# must read its output with the same rule, not with a copy of it.
static func last_json_object(text: String):
	# Windows pipes CRLF even for a program that writes "\n", so normalise before
	# anchoring on column zero -- otherwise every line ends in "\r" and nothing
	# matches.
	var lines := text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
	var end := -1
	for index in range(lines.size() - 1, -1, -1):
		if lines[index] == "}":
			end = index
			break
	if end == -1:
		return null
	for start in range(end, -1, -1):
		if lines[start] != "{":
			continue
		var parsed = JSON.parse_string("\n".join(lines.slice(start, end + 1)))
		if typeof(parsed) == TYPE_DICTIONARY:
			return parsed
	return null
