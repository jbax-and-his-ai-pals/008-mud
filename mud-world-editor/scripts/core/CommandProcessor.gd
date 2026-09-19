# scripts/core/CommandProcessor.gd
class_name CommandProcessor
extends RefCounted

var undo_stack: Array = []
var redo_stack: Array = []
var max_history: int = 50

class Command:
	var do_func: Callable
	var undo_func: Callable
	var description: String
	
	func _init(d: Callable, u: Callable, desc: String = ""):
		do_func = d
		undo_func = u
		description = desc

func commit(do_action: Callable, undo_action: Callable, desc: String = "Action"):
	var cmd = Command.new(do_action, undo_action, desc)
	cmd.do_func.call()
	undo_stack.append(cmd)
	redo_stack.clear()
	if undo_stack.size() > max_history:
		undo_stack.pop_front()
	print("CMD: ", desc)

func undo():
	if undo_stack.is_empty(): return
	var cmd = undo_stack.pop_back()
	cmd.undo_func.call()
	redo_stack.append(cmd)
	print("UNDO: ", cmd.description)

func redo():
	if redo_stack.is_empty(): return
	var cmd = redo_stack.pop_back()
	cmd.do_func.call()
	undo_stack.append(cmd)
	print("REDO: ", cmd.description)

# Drop the history. Undo closures capture the data they were built against, so
# they belong to the region that was loaded when they were committed: replaying
# one after a region switch either corrupts the newly loaded region or raises a
# missing-key error. `Main._load_region_now` calls this on every load.
func clear_history():
	if undo_stack.is_empty() and redo_stack.is_empty(): return
	undo_stack.clear()
	redo_stack.clear()
	print("CMD: history cleared")
