"""Does the engine keep a character, and the changes it made to the world, across a restart?

Asked of zelda_slice with a real database file. Answer as of 2026-09-28: a fresh
`char create` on the rebooted server makes a new character, and a lever pulled or a
wall bombed is not restored (the world is rebuilt from content on boot). That may be
this harness rather than the engine: the real transports resume sessions differently.
Not a conclusion; a question to settle before a story depends on it.
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
