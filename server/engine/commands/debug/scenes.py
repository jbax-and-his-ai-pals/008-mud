# engine/commands/debug/scenes.py
"""Debugging aids for scenes and the story so far: watch less, jump ahead.

    scene                   the set's scenes, and which are running or seen
    scene skip              tell what is left of the running scene(s) at once
    scene play <id>         begin a scene again (even one already seen)
    scene end <id>          finish a scene without telling it
    checkpoint              the set's checkpoints
    checkpoint <name>       jump to one: the scene `checkpoint_<name>` is played and told at once

A checkpoint is an ordinary scene whose id starts with `checkpoint_`: its beats carry effects (`end_scene` for the story
told so far, `set_flag`, `give_item`, `recruit`, `teleport`...) that stand in for playing up to a point. The commands are
for testing; scenes are the player's and these are allowed while one is running.
"""

from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.world.scenes import DONE_PREFIX

CHECKPOINT_PREFIX = "checkpoint_"


def _runner(context):
    world = context.get("world")
    return getattr(world, "scene_runner", None), context.get("player")


@command("scene", ["scenes"], "debug", "Watch less: list, skip, replay or end scenes.\nUsage: scene | scene skip | scene play <id> | scene end <id>")
def scene_handler(args, context):
    runner, player = _runner(context)
    if runner is None or player is None:
        return "Scenes are unavailable."
    action = args[0].lower() if args else "list"
    if action == "list":
        if not runner.scenes:
            return "This set has no scenes."
        running = set(runner.running(player))
        lines = []
        for scene_id in sorted(runner.scenes):
            state = "running" if scene_id in running else "seen" if player.flags.get(DONE_PREFIX + scene_id) else ""
            lines.append("  %s%s" % (scene_id, ("  [%s]" % state) if state else ""))
        return "Scenes:\n" + "\n".join(lines)
    if action == "skip":
        count = runner.skip(player)
        return ("%sSkipped %d scene%s: the rest of it is told now.%s" % (FORMAT_SUCCESS, count, "" if count == 1 else "s", FORMAT_RESET)
                if count else "No scene is running.")
    if action in ("play", "end") and len(args) > 1:
        scene_id = args[1]
        done = runner.play(player, scene_id) if action == "play" else runner.end(player, scene_id)
        if not done:
            return "%sNo scene named '%s'.%s" % (FORMAT_ERROR, scene_id, FORMAT_RESET)
        return "%s%s '%s'.%s" % (FORMAT_SUCCESS, "Playing" if action == "play" else "Ended", scene_id, FORMAT_RESET)
    return "Usage: scene | scene skip | scene play <id> | scene end <id>"


@command("checkpoint", ["jump"], "debug", "Jump ahead in the story.\nUsage: checkpoint | checkpoint <name>")
def checkpoint_handler(args, context):
    runner, player = _runner(context)
    if runner is None or player is None:
        return "Checkpoints are unavailable."
    # In the order the set declares them, which is the order of its story: not alphabetical.
    names = [scene_id[len(CHECKPOINT_PREFIX):] for scene_id in runner.scenes if scene_id.startswith(CHECKPOINT_PREFIX)]
    if not args:
        if not names:
            return "This set has no checkpoints (scenes named checkpoint_<name>)."
        notes = {name: str(runner.scenes[CHECKPOINT_PREFIX + name].get("note", "") or "") for name in names}
        return "Checkpoints (checkpoint <name>):\n" + "\n".join("  %s%s" % (name, ("  - " + notes[name]) if notes[name] else "") for name in names)
    name = args[0].lower()
    scene_id = CHECKPOINT_PREFIX + name
    if scene_id not in runner.scenes:
        return "%sNo checkpoint named '%s'. Try: %s%s" % (FORMAT_ERROR, name, ", ".join(names) or "(none)", FORMAT_RESET)
    for playing in runner.running(player):
        runner.end(player, playing)   # what is playing now is not wanted
    runner.play(player, scene_id)
    runner.skip(player, scene_id)
    return "%sJumped to '%s'.%s" % (FORMAT_SUCCESS, name, FORMAT_RESET)
