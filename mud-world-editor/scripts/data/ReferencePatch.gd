# scripts/data/ReferencePatch.gd
#
# Applying a rename to the data the editor already holds.
#
# `toolkit/reference_index.py` says *where* an id is named: a file, and a path
# inside that file's payload. This walks one of those paths and performs the edit,
# so renaming an entry repairs its referrers instead of leaving them dangling.
#
# It is the only place that knows how to walk a reference path, and it knows
# nothing about what the path *means* -- the index owns that. Two shapes occur,
# and the path itself says which:
#
#   * **value** -- `merchant.properties.work_location` holds the id, so the value
#     at that path is replaced;
#   * **key** -- `spawner.monster_types.giant_rat` names the id as a dictionary
#     *key* (the walker spells a keyed reference by ending the path with the id),
#     so the key is renamed. Order is preserved: a rename must not reorder a file
#     the round-trip check compares byte for byte.
class_name ReferencePatch
extends RefCounted

## `properties.sells_items[0].item_id` becomes
## `["properties", "sells_items", "0", "item_id"]`. Indices stay strings so one
## list describes both halves of a path.
static func parse_path(path: String) -> Array:
	var parts: Array = []
	for chunk in path.split(".", false):
		var name := str(chunk)
		while name.contains("["):
			var open := name.find("[")
			var close := name.find("]")
			if close < open:
				break
			var head := name.substr(0, open)
			if head != "":
				parts.append(head)
			parts.append(name.substr(open + 1, close - open - 1))
			name = name.substr(close + 1)
		if name != "":
			parts.append(name)
	return parts


## The container and final key a path addresses, or `{}` when it does not exist.
static func resolve(root, path: String) -> Dictionary:
	var parts := parse_path(path)
	if parts.is_empty():
		return {}
	var node = root
	for index in range(parts.size() - 1):
		node = _step(node, parts[index])
		if node == null:
			return {}
	return {"parent": node, "key": parts[parts.size() - 1]}


## Rename `old_id` to `new_id` at `path`.
##
## Returns `{ok, mode, path_after, error}`. `path_after` is the path that now
## addresses the same reference, which differs from the input in key mode -- the
## undo path is built from it rather than from the original.
static func rename(root, path: String, old_id: String, new_id: String) -> Dictionary:
	var resolved := resolve(root, path)
	if resolved.is_empty():
		return {"ok": false, "mode": "", "path_after": path, "error": "no value at %s" % path}
	var parent = resolved["parent"]
	var key := str(resolved["key"])
	if key == old_id:
		return _rename_key(parent, key, new_id, path)
	return _replace_value(parent, key, old_id, new_id, path)


static func _rename_key(parent, key: String, new_id: String, path: String) -> Dictionary:
	if not parent is Dictionary:
		return {"ok": false, "mode": "key", "path_after": path, "error": "%s is not an object" % path}
	var container: Dictionary = parent
	if container.has(new_id):
		return {"ok": false, "mode": "key", "path_after": path,
			"error": "'%s' already exists at %s" % [new_id, path]}
	# Rebuild in place so the renamed key keeps the position of the old one.
	var rebuilt: Dictionary = {}
	for existing in container:
		if str(existing) == key:
			rebuilt[new_id] = container[existing]
		else:
			rebuilt[existing] = container[existing]
	container.clear()
	container.merge(rebuilt)
	var parts := parse_path(path)
	parts[parts.size() - 1] = new_id
	return {"ok": true, "mode": "key", "path_after": ".".join(parts), "error": ""}


static func _replace_value(parent, key: String, old_id: String, new_id: String, path: String) -> Dictionary:
	var found = _step(parent, key)
	if found == null:
		return {"ok": false, "mode": "value", "path_after": path, "error": "no value at %s" % path}
	if str(found) != old_id:
		return {"ok": false, "mode": "value", "path_after": path,
			"error": "%s holds '%s', not '%s'" % [path, str(found), old_id]}
	if parent is Array:
		parent[int(key)] = new_id
	elif parent is Dictionary:
		parent[key] = new_id
	else:
		return {"ok": false, "mode": "value", "path_after": path, "error": "%s is not editable" % path}
	return {"ok": true, "mode": "value", "path_after": path, "error": ""}


static func _step(node, key: String):
	if node is Array:
		if not key.is_valid_int():
			return null
		var index := int(key)
		return node[index] if index >= 0 and index < node.size() else null
	if node is Dictionary:
		return node.get(key) if node.has(key) else null
	return null
