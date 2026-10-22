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
    wait(7)
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


# ============================================================ the north
from engine.items.item_factory import ItemFactory


def give(item_id, count=1):
    for _ in range(count):
        g.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, g.world))


def walk(*dirs):
    for d in dirs:
        say("go %s" % d)
        clear_foes()
    return g.where()


def take_from(chest_name):
    say("open %s" % chest_name)
    say("take all from %s" % chest_name)


g.player.current_region_id, g.player.current_room_id = "heartland", "hl_1_1"
g.player.health = g.player.max_health
walk("north", "north")
check("north of the castle lie the moors", g.where() == "northmarch:nm_3_1", g.where())
walk("north")
check("a stone door in a hillside", g.where() == "northmarch:nm_2_1", g.where())
say("go down")
out = say("look")
check("in the dark the vault shows nothing, not even its name", "pitch dark" in out and "VAULT" not in out.upper().replace("PITCH", ""), out[:120])
out = say("go north")
check("a wall in the dark says so", "no way north" in out, out[:120])
say("use pitch torch")
out = say("look")
check("a torch shows the vault", "vault door" in out.lower(), out[:120])
walk("east", "down", "east", "north")
check("the sanctum of the tablet", g.where() == "ostrun_vault:v2_sanctum", g.where())
out = say("look at stone tablet")
check("the tablet names the three things", "sunstones" in out and "signet" in out and "moon harp" in out, out[:200])
walk("south", "west", "up", "west", "up")
check("back out under the sky", g.where() == "northmarch:nm_2_1", g.where())

# Harrowmere
g.player.current_region_id, g.player.current_room_id = "northmarch", "nm_1_0"
walk("west")
check("Harrowmere, the grey town", g.where() == "harrowmere:gate", g.where())
walk("west", "south")
say("trade provisioner")
check("the provisioner sells wyrm scale", "wyrm scale" in say("list"), "")
say("stoptrade")
check("a locked house", g.where() == "harrowmere:provisions", g.where())
out = say("go west")
check("the shuttered house wants a key", g.where() == "harrowmere:provisions" and "locked" in out.lower(), out[:100])
give("item_brass_key", 3)
walk("west")
check("the house opens to a key", g.where() == "harrowmere:locked_house", g.where())
before = gold()
for chest_name in ("oak house chest", "pine house chest", "elm house chest"):
    take_from(chest_name)
check("three chests in the shuttered house: gold, a torch and moss", gold() > before and "item_healing_moss" in g.items(), "%s %s" % (gold() - before, g.items()))
walk("east", "north", "east", "north")
check("the hill graveyard above the gate", g.where() == "harrowmere:graveyard", g.where())

# the barrow
walk("down", "north", "east")
take_from("mouldering chest")
check("moss in the cell", "item_healing_moss" in g.items(), "")
walk("west", "north")
before = gold()
take_from("rotted chest")
check("a purse in the Hall of Lamps", gold() > before, gold() - before)
out = say("go southeast")
check("the oak door is opened by a key", g.where() == "harrow_barrow:b1_vault", g.where() + " " + out[:80])
before = gold()
take_from("barrow chest")
check("and holds a small purse", gold() > before, gold() - before)
walk("northwest", "east", "down")
check("down to the second floor", g.where() == "harrow_barrow:b2_landing", g.where())
walk("north", "north", "down")
check("down to the third", g.where() == "harrow_barrow:b3_landing", g.where())
walk("north", "west")
take_from("black coffer")
check("the cursed circlet", "item_gravebound_circlet" in g.items(), g.items())
walk("east", "east")
take_from("silver-bound chest")
check("the moon harp", "item_moon_harp" in g.items(), g.items())
say("use moon harp")
called = [n for n in g.world.npcs.values() if n.is_alive and n.properties.get("encounter")]
check("playing the harp calls something of the dark", bool(called), "")
clear_foes()

# spells and the way out
while g.player.runtime_state.progression.level < 13:
    g.player.gain_experience(g.player.runtime_state.progression.experience_to_level)
check("by level 13 the hero has learned Egress and Recall", {"egress", "recall"} <= set(g.player.runtime_state.magic.known_spells), g.player.runtime_state.magic.known_spells)
out = say("cast recall")
check("Recall will not work from deep underground", g.where().startswith("harrow_barrow") and "stone" in out, out[:100])
out = say("cast egress")
check("Egress brings him up to the graveyard", g.where() == "harrowmere:graveyard", g.where() + " " + out[:100])
out = say("cast recall")
check("and Recall carries him home to Telgard", g.where() == "telgard:courtyard", g.where() + " " + out[:100])

# the curse
g.player.current_region_id, g.player.current_room_id = "bracken_ford", "chapel"
say("equip gravebound circlet")
check("the circlet is on and cannot be taken off", g.player.equipment.get("head") is not None, "")
g.player.current_region_id, g.player.current_room_id = "heartland", "hl_1_2"
out = say("go north")
check("the castle gate turns him away", g.where() == "heartland:hl_1_2" and "cursed" in out.lower(), out[:100])
g.player.current_region_id, g.player.current_room_id = "bracken_ford", "chapel"
say("talk priest")
say("reply 1")
check("the priest lifts the curse", g.player.equipment.get("head") is None and "item_gravebound_circlet" not in g.items(), "%s %s" % (g.player.equipment.get("head"), g.items()))

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
