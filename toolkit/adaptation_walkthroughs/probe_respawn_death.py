"""Two questions the adaptation slices raised about the engine, asked of zelda_slice.

    .venv/Scripts/python.exe toolkit/adaptation_walkthroughs/probe_respawn_death.py

1. Does a hostile NPC that a room places come back after it is killed?
2. What does dying do?

Answers as of 2026-09-28: no (its `respawn_cooldown` is inert; only a region's
ambient spawner refills a room), and the hero returns to the start with full health.
"""
import re

from play import Game

NL = chr(10)


def line(label, value):
    print("%-52s %s" % (label, value))


g = Game("zelda_slice")
for command in ["go west", "go in", "talk hermit", "reply 1", "equip wooden sword",
                "go out", "go east", "go north", "go north"]:
    g.run(command)

print("== a placed hostile NPC ==")
line("green blob at the crossroads", bool(g._alive("blob")))
print("   ", g.fight("blob"))
line("alive right after the kill", bool(g._alive("blob")))
g.tick(3200)
line("alive 320 s later (respawn_cooldown is 180)", bool(g._alive("blob")))
g.tick(6000)
line("alive 920 s later", bool(g._alive("blob")))
g.close()

print(NL + "== death ==")
g = Game("zelda_slice")
g.player.current_region_id, g.player.current_room_id = "aldermark", "crossroads"
g.player.health = 1
g.run("attack blob")
g.tick(400)
line("hero alive after a fight at 1 hp", g.player.is_alive)
if not g.player.is_alive:
    text = re.sub(r"\[\[[^\]]*\]\]", "", g.run("respawn"))
    line("respawn says", text.strip().splitlines()[0])
    line("respawn location", g.where())
    line("health after respawn", "%s/%s" % (g.player.health, g.player.max_health))
g.close()
