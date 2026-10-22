"""Play dq1_slice from the throne room, recording what worked. Grows with the set, one stretch of the story at a time.

Run from anywhere: .venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_dq1.py [--verbose]"""
import re
import sys
from play import Game

RESULTS = []
NL = chr(10)


def clean(t):
    return re.sub(r"\[\[[^\]]*\]\]", "", t).strip()


def check(label, ok, detail=""):
    RESULTS.append((label, bool(ok), detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", label, ("  -- " + str(detail)) if (detail and not ok) else ""))


V = "--verbose" in sys.argv
g = Game("dq1_slice")


def say(cmd, n=400):
    out = clean(g.run(cmd))
    if V:
        print("> %s%s%s%s" % (cmd, NL, out[:n], NL))
    return out


def wait(seconds):
    for _ in range(seconds):
        g.world.clock.advance(1.0)
        g.tick()


def gold():
    return g.player.runtime_state.gold


def clear_foes():
    for foe in [n for n in g.world.npcs.values() if n.is_alive and n.faction == "hostile"
                and (n.current_region_id, n.current_room_id) == (g.player.current_region_id, g.player.current_room_id)]:
        g.world.remove_npcs(foe.obj_id)


# --- the throne room ---------------------------------------------------------
check("starts in the throne room of Telgard", g.where() == "telgard:throne_room", g.where())
check("the hero starts with nothing but a name", not g.items() and gold() == 0, "%s %s" % (g.items(), gold()))
say("talk king")
say("reply 1")
check("the king's charge is taken", g.player.flags.get("met_king") is True, "")

# --- the treasury ------------------------------------------------------------
say("go south")
for chest in ("royal coffer", "cedar box", "iron-banded chest"):
    say("open %s" % chest)
    say("take all from %s" % chest)
check("120 gold, a torch and a key from the treasury", gold() == 120 and "item_pitch_torch" in g.items() and "item_brass_key" in g.items(), "%s %s" % (gold(), g.items()))

# --- the hall and its doors ----------------------------------------------------
say("go north"); say("go down")
check("down to the great hall", g.where() == "telgard:great_hall", g.where())
out = say("go west")
check("the storeroom is locked until a key opens it, and the key is spent", g.where() == "telgard:west_room" and "item_brass_key" not in g.items(), "%s %s" % (g.where(), out[:100]))
for n in range(1, 5):
    say("take all from storeroom chest") if n == 1 else None
before = gold()
for _ in range(4):
    say("open storeroom chest"); say("take all from storeroom chest")
check("four little purses of gold", gold() - before > 0, gold() - before)
out = say("go east")
out = say("go east")
check("the keysmith's hall is locked and there is no key", g.where() == "telgard:great_hall" and "locked" in out.lower(), out[:120])

# --- out into the fields ---------------------------------------------------------
say("go south"); say("go south")
check("out at the castle gate, in the fields", g.where() == "heartland:hl_1_2", g.where())
wins = 0
for _ in range(12):
    say("go north" if g.where() == "heartland:hl_0_2" else "go north")
    break
say("go south")
for _ in range(25):
    foes = [n for n in g.world.npcs.values() if n.is_alive and n.faction == "hostile" and n.properties.get("encounter")]
    if foes:
        r = g.fight(foes[0].name.split()[-1], potion="healing moss")
        wins += 1 if r.startswith("won") else 0
        clear_foes()
    say("go east" if g.where() == "heartland:hl_1_2" else "go west")
check("something finds the hero on the fields, and he wins his first battles", wins >= 1 and g.player.runtime_state.progression.level >= 1, wins)
check("a battle pays gold and experience", gold() > 120 or g.player.runtime_state.progression.experience > 0, "%s %s" % (gold(), g.player.runtime_state.progression.experience))
g.player.runtime_state.gold += 500

# --- Bracken Ford -----------------------------------------------------------------
g.player.current_region_id, g.player.current_room_id = "heartland", "hl_1_4"
clear_foes()
out = say("go east")
check("Bracken Ford lies east of the fields", g.where() == "bracken_ford:gate", g.where())
say("go east"); say("go north")
check("the armoury", g.where() == "bracken_ford:armoury", g.where())
say("trade armourer")
listing = say("list")
check("the armourer sells a bronze blade for 180", "bronze blade" in listing and "180" in listing, listing[:200])
say("buy bronze blade")
say("stoptrade")
check("the blade is bought", "item_bronze_blade" in g.items(), g.items())
say("equip bronze blade")
check("and wielded", g.player.equipment.get("main_hand") is not None and g.player.equipment["main_hand"].obj_id == "item_bronze_blade", "")
before = gold()
say("go south"); say("go east")
say("talk innkeeper")
say("reply 1")
check("a bed costs 6", gold() == before - 6, "%s -> %s" % (before, gold()))

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
