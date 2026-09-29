"""Does the engine keep a character, and the changes it made to the world, across a restart?

Asked of zelda_slice with a real database file. Before chunk 7 Phase 1 (2026-09-28) the answer was
no, and it was the engine, not this harness: the running server persisted nothing (both transports
built an in-memory database, the entity table was written and never read back, a returning player
could not be told from a new one, and a lever pulled or a wall bombed was not restored). Now a
single-player story (`world.mode: single_player_story`, which both slices are) resumes its character
by name and its world with it, so this probe prints "Welcome back" and the lever's door and the
bomb wall still open. A shared world (`persistent_shard`, the default) still keeps nothing, by
Decision 7. Held by `TestPersistence` in server/tests/singles/test_adaptation_slices.py.
"""
import os, re, tempfile
from play import Game
NL = chr(10)
def clean(t): return re.sub(r"\[\[[^\]]*\]\]", "", t).strip()
def line(label, value): print("%-58s %s" % (label, value))

db = os.path.join(tempfile.mkdtemp(), "world.sqlite3")
g = Game("zelda_slice", db_path=db, player_id="persist")
for c in ["go west", "go in", "talk hermit", "reply 1", "equip wooden sword", "go out", "go east", "go north", "talk sage", "reply 1"]:
    g.run(c)
line("before: flags", g.player.flags)
line("before: quests", {q.get("title"): q.get("state") for q in g.player.runtime_state.quests.active.values()})
line("before: inventory", g.items(), )
p = g.player
p.current_region_id, p.current_room_id = "mossroot", "root_hall"
g.run("pull loose stone")
line("before: root_hall exits", dict(g.world.get_region("mossroot").get_room("root_hall").exits))
p.current_region_id, p.current_room_id = "drowned_vault", "bomb_chamber"
p.runtime_state.magic.known_spells.add("bomb"); p.runtime_state.magic.mana = 100
g.run("cast bomb on here")
line("before: bomb wall open", "north" not in (g.world.get_region("drowned_vault").get_room("bomb_chamber").properties.get("exit_requirements") or {}))
p.current_region_id, p.current_room_id = "aldermark", "village_green"
g.tick(50)
g.close()

g2 = Game("zelda_slice", db_path=db, player_id="persist", create=True)
print("   char create on reboot ->", clean(g2.log[0][1]).splitlines()[0][:100])
line("after reboot: player present", g2.player is not None)
if g2.player is not None:
    line("after: location", g2.where())
    line("after: flags", g2.player.flags)
    line("after: quests", {q.get("title"): q.get("state") for q in g2.player.runtime_state.quests.active.values()})
    line("after: inventory", g2.items())
    line("after: equipment", [getattr(i, "obj_id", "") for i in g2.player.equipment.values() if i])
line("after: root_hall exits", dict(g2.world.get_region("mossroot").get_room("root_hall").exits))
line("after: bomb wall open", "north" not in (g2.world.get_region("drowned_vault").get_room("bomb_chamber").properties.get("exit_requirements") or {}))
g2.close()
