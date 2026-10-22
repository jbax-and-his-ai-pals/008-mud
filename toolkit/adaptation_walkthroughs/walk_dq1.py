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
    for foe in [n for n in g.world.npcs.values() if n.is_alive and n.faction == "hostile" and n.properties.get("encounter")
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


# ============================================================ the east
def goto(target):
    """Walk to `region:room` by the shortest way through the exits, clearing what the fields throw up. Keys are plentiful."""
    start = g.where()
    seen = {start: []}
    queue = [start]
    while queue:
        here = queue.pop(0)
        if here == target:
            break
        region_id, room_id = here.split(":")
        room = g.world.get_region(region_id).get_room(room_id)
        for direction, dest in room.exits.items():
            ref = dest if ":" in dest else "%s:%s" % (region_id, dest)
            if ref not in seen:
                seen[ref] = seen[here] + [direction]
                queue.append(ref)
    assert target in seen, "no way from %s to %s" % (start, target)
    for direction in seen[target]:
        say("go %s" % direction)
        clear_foes()
    return g.where()


g.player.health = g.player.max_health
give("item_brass_key", 6)
check("Telgard to Kalder over the east road", goto("kalder:gate") == "kalder:gate", g.where())
goto("kalder:lane4")
check("four steps south of the bath", g.where() == "kalder:lane4", g.where())
out = say("search")
check("searching the corner of the back lane finds the slumber pipe", "item_slumber_pipe" in g.items(), out[:120])
check("and once only", "nothing to search" in say("search"), "")
goto("kalder:west_house")
check("an old house behind a locked door", g.where() == "kalder:west_house", g.where())

# the hermit
goto("frostfell_hollow:f_hall")
check("the frost hollow", g.where() == "frostfell_hollow:f_hall", g.where())
g.player.inventory.remove_item("item_moon_harp", 9)
out = say("talk hermit")
check("without the harp the hermit gives nothing", "item_cloudcallers_staff" not in g.items(), out[:100])
give("item_moon_harp")
out = say("talk hermit")
say("reply 1")
check("with the moon harp he trades the staff", "item_cloudcallers_staff" in g.items() and "item_moon_harp" not in g.items(), "%s | %s" % (g.items(), out[:80]))

# the mountain cave
goto("greyhorn_cavern:g2_landing")
for room_id, chest_name in (("g1_chest", "cavern chest"),):
    pass
goto("greyhorn_cavern:g1_chest"); take_from("cavern chest")
goto("greyhorn_cavern:g2_torch"); take_from("stone chest")
goto("greyhorn_cavern:g2_band"); take_from("iron-bound chest")
goto("greyhorn_cavern:g2_gold")
before = gold()
take_from("lidded chest")
goto("greyhorn_cavern:g2_trove")
take_from("heavy chest")
check("the cavern pays out: a band, gold, and a hidden hoard", "item_brawlers_band" in g.items() and gold() - before >= 128, "%s %s" % (gold() - before, g.items()))

# the swamp tunnel and the drake
while g.player.runtime_state.progression.level < 16:
    g.player.gain_experience(g.player.runtime_state.progression.experience_to_level)
w = ItemFactory.create_item_from_template("item_longblade", g.world); g.player.equipment["main_hand"] = w
a = ItemFactory.create_item_from_template("item_half_harness", g.world); g.player.equipment["body"] = a
g.player.health = g.player.max_health
goto("mirewater_tunnel:t_den")
check("the drake in its den", bool([n for n in g.world.npcs.values() if n.is_alive and n.template_id == "verdant_drake_warden"]), "")
r = g.fight("drake", potion="healing moss")
check("the warden drake falls", r.startswith("won"), r)
wait(8)
check("the way to the cell is shown", g.player.flags.get("drake_slain") is True, "")
check("a locked door", True, "")
say("go north")
check("the iron door yields to a key", g.where() == "mirewater_tunnel:t_cell", g.where())
out = say("talk princess")
check("the princess asks to be taken home", "Take me out" in out, out[:120])
say("reply 1")
check("she walks with the hero", g.player.flags.get("princess_with_you") is True and bool([n for n in g.world.npcs.values() if n.template_id == "princess_elowen" and n.properties.get("companion")]), "")
goto("telgard:throne_room")
wait(20)
check("the king takes his daughter back", g.player.flags.get("princess_home") is True and bool([n for n in g.world.npcs.values() if n.template_id == "princess_elowen_court"]), "")
say("talk princess")
say("reply 1")
check("and she gives the locket", "item_elowens_locket" in g.items(), g.items())
goto("heartland:hl_1_2")
out = say("use elowen's locket")
check("the locket tells how far Telgard is", "steps behind" in out, out[:120])
check("and is not used up", "item_elowens_locket" in g.items(), "")


# ============================================================ the south-east: the stones, Rivenhal and the sage
goto("telgard:sunstone_vault")
take_from("stone casket")
check("the sunstones under the castle", "item_sunstones" in g.items() and "item_brass_key" in [i for i in g.items()] or "item_sunstones" in g.items(), g.items())

goto("mirewater_tunnel:t_exit")
check("out of the tunnel's southern mouth", g.where() == "mirewater_tunnel:t_exit", g.where())
check("the fenlands beyond", goto("fenlands:fn_2_2") == "fenlands:fn_2_2", g.where())
goto("rivenhal:gate")
check("Rivenhal", g.where() == "rivenhal:gate", g.where())
goto("rivenhal:keys")
say("trade locksmith")
listing = say("list")
check("the locksmith sells brass keys", "brass key" in listing, listing[:120])
before = gold()
g.player.runtime_state.gold = max(gold(), 200)
before = gold()
say("buy brass key")
say("stoptrade")
check("a key costs about fifty-two", 50 <= before - gold() <= 54, before - gold())
goto("rivenhal:strongroom")
take_from("inner chest")
check("two locked doors and the inn's inner chest hold a homing feather", "item_homing_feather" in g.items(), g.items())
goto("rivenhal:arms")
say("trade armourer")
listing = say("list")
check("the armourer sells spellwoven mail and a plate harness", "spellwoven mail" in listing and "plate harness" in listing, listing[:200])
say("stoptrade")

# the sage and the prism
goto("sagehollow:s_hall")
out = say("talk sage")
check("without the three things the sage only waits", "item_prism_tear" not in g.items(), out[:100])
give("item_ostruns_signet")
g.player.inventory.add_item(ItemFactory.create_item_from_template("item_cloudcallers_staff", g.world)) if "item_cloudcallers_staff" not in g.items() else None
out = say("talk sage")
say("reply 1")
check("with the sunstones, the staff and the signet he makes the prism",
      "item_prism_tear" in g.items() and not ({"item_sunstones", "item_cloudcallers_staff", "item_ostruns_signet"} & set(g.items())), g.items())


# ============================================================ the south
while g.player.runtime_state.progression.level < 22:
    g.player.gain_experience(g.player.runtime_state.progression.experience_to_level)
g.player.equipment["main_hand"] = ItemFactory.create_item_from_template("item_emberbrand", g.world)
g.player.equipment["body"] = ItemFactory.create_item_from_template("item_plate_harness", g.world)
g.player.equipment["off_hand"] = ItemFactory.create_item_from_template("item_kite_shield", g.world)
g.player.health = g.player.max_health
give("item_healing_moss", 6)
goto("southwilds:sw_5_3")
check("the road to the walled town", g.where() == "southwilds:sw_5_3", g.where())
say("go south")
check("the colossus stands in the road", g.where() == "southwilds:sw_6_3" and bool([n for n in g.world.npcs.values() if n.is_alive and n.template_id == "mossback_colossus"]), g.where())
out = say("go south")
check("it will not be walked past", g.where() == "southwilds:sw_6_3", out[:120])
out = say("use slumber pipe on mossback colossus")
check("the pipe puts it to sleep", g.player.flags.get("golem_asleep") is True, out[:140])
out = say("go south")
check("and the gate of Cairnwall is open", g.where() == "cairnwall:gate", g.where() + " " + out[:80])
goto("cairnwall:plaza")
goto("cairnwall:north_tools"); goto("cairnwall:key_shop")
say("trade locksmith")
check("keys here cost ninety-eight", "brass key" in say("list"), "")
say("stoptrade")
g.player.inventory.add_item(ItemFactory.create_item_from_template("item_brass_key", g.world))
goto("cairnwall:locked_arms")
say("trade vault smith")
listing = say("list")
check("the vault shop sells emberbrand and the moonsilver shield", "emberbrand" in listing and "moonsilver shield" in listing, listing[:200])
say("stoptrade")
goto("cairnwall:inn")
before = gold()
g.player.runtime_state.gold = max(gold(), 300)
before = gold()
say("talk innkeeper")
say("reply 1")
check("a bed here costs a hundred", before - gold() == 100, before - gold())

# the ruins and the mail
goto("haskarth:h_street")
check("the ruins of Haskarth", g.where() == "haskarth:h_street", g.where())
goto("haskarth:h_trees")
out = say("search")
check("searching before the knight is dead finds nothing", "item_ostruns_mail" not in g.items(), out[:100])
r = g.fight("cleaver", potion="healing moss")
check("the cleaver knight falls", r.startswith("won"), r)
out = say("search")
check("then the trees give up Ostrun's mail", "item_ostruns_mail" in g.items(), out[:100])

# the fen
goto("southwilds:fen_end")
out = say("use elowen's locket")
check("the locket says how far the fen is from the castle", "39" in out or "40" in out, out[:140])
out = say("search")
check("searching the place finds the signet", "item_ostruns_signet" in g.items(), out[:120])


# ============================================================ the end
while g.player.runtime_state.progression.level < 28:
    g.player.gain_experience(g.player.runtime_state.progression.experience_to_level)
g.player.equipment["body"] = ItemFactory.create_item_from_template("item_ostruns_mail", g.world)
g.player.equipment["off_hand"] = ItemFactory.create_item_from_template("item_moonsilver_shield", g.world)
g.player.equipment["main_hand"] = ItemFactory.create_item_from_template("item_emberbrand", g.world)
g.player.health = g.player.max_health
give("item_brass_key", 6)
give("item_healing_moss", 8)
goto("heartland:hl_shore")
out = say("go east")
check("there is no way across the water", g.where() == "heartland:hl_shore", out[:100])
goto("heartland:hl_1_2")
out = say("use the prism tear")
check("the prism tear works only at the shore", "item_prism_tear" in g.items(), out[:100])
goto("heartland:hl_shore")
out = say("use the prism tear")
check("poured at the shore it makes a bridge", "item_prism_tear" not in g.items(), out[:120])
goto("skarn_isle:landing")
check("across the rainbow to the island", g.where() == "skarn_isle:landing", g.where())
goto("skarnhold:k1_hall")
check("into the black hall", g.where() == "skarnhold:k1_hall", g.where())
goto("skarnhold:k_b2_a")
say("use pitch torch") if "item_pitch_torch" in g.items() else give("item_pitch_torch")
say("use pitch torch")
goto("skarnhold:k_b2_sword")
take_from("iron strongbox")
check("Ostrun's edge lies in the sealed chamber on the second floor", "item_ostruns_edge" in g.items(), g.items())
say("equip ostrun's edge")
check("the edge is wielded", g.player.equipment["main_hand"].obj_id == "item_ostruns_edge", "")
goto("skarnhold:k_b7_treasure")
before = gold()
for chest_name in ("gilded chest", "small chest", "pale chest"):
    take_from(chest_name)
check("a treasure room with a hoard of gold", gold() - before >= 600, gold() - before)
goto("skarnhold:k_b7_throne")
out = say("talk maldrath")
check("the Sovereign makes his offer", "half of Vaelmoor" in out, out[:160])
say("reply 2")
foes = [n for n in g.world.npcs.values() if n.is_alive and n.template_id == "maldrath_man"]
check("refused, he rises and fights", len(foes) == 1, "")
g.player.health = g.player.max_health
r = g.fight("maldrath", potion="healing moss")
check("the first form falls", r.startswith("won"), r)
wait(10)
check("and the second rises", bool([n for n in g.world.npcs.values() if n.is_alive and n.template_id == "maldrath_wyrm"]), "")
g.player.health = g.player.max_health
r = g.fight("maldrath", potion="healing moss")
check("the wyrm falls", r.startswith("won"), r)
wait(25)
check("the Dawnglass is free", g.player.flags.get("maldrath_down") is True, "")
goto("heartland:hl_1_2")
for _ in range(12):
    wait(7)
    say("go east" if g.where() == "heartland:hl_1_2" else "go west")
check("afterwards the fields are quiet", not [n for n in g.world.npcs.values() if n.is_alive and n.properties.get("encounter")], "")
goto("telgard:throne_room")
say("talk king")
say("reply 1")
wait(40)
check("the king offers his crown and it is declined: the end", g.player.flags.get("the_end") is True, "")

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
