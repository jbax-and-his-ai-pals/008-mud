"""Play ff4_slice from the throne room to the summoner child, recording what worked.

Run from anywhere: .venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_ff4.py [--verbose]"""
import os
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


def say(g, cmd, n=500, show=False):
    out = clean(g.run(cmd))
    if show:
        print("> %s%s%s%s" % (cmd, NL, out[:n], NL))
    return out


def flat(s, n=200):
    return s.replace(NL, " | ")[:n]


g = Game("ff4_slice")
V = "--verbose" in sys.argv


def quest_states():
    return {q.get("title"): q.get("state") for q in g.player.runtime_state.quests.active.values()}


def equipped_ids():
    return [getattr(i, "obj_id", "") for i in g.player.equipment.values() if i]


def wait(seconds):
    """Scenes are told over time: let the clock run (the transports do this every tick)."""
    for _ in range(seconds):
        g.world.clock.advance(1.0)
        g.tick()


def sky_alive():
    return [n for n in g.world.npcs.values() if n.template_id in ("storm_wyvern", "thunderhawk") and n.is_alive]


def beat_the_sky():
    for _ in range(80):
        alive = sky_alive()
        if not alive:
            return True
        say(g, "attack " + alive[0].name)
        wait(3)
    return False


# --- Ilmara: the crystal ------------------------------------------------------
check("starts in the Ilmaran crystal chamber", g.where() == "ilmara:crystal_chamber", g.where())
check("starting kit, blade and armour worn", "item_commander_seal" in g.items() and "item_dark_blade" in equipped_ids() and "item_dark_armor" in equipped_ids(), str(equipped_ids()))
wait(60)
check("the acolytes are gone and the elder is left", not [n for n in g.world.npcs.values() if n.template_id == "ilmaran_acolyte"]
      and [n for n in g.world.npcs.values() if n.template_id == "elder_of_ilmara"], "")
out = say(g, "talk elder", show=V, n=400)
out = say(g, "take crystal", show=V, n=400)
wait(40)
check("the crystal carries you to the airship", g.where() == "airship:deck", g.where())
check("the first wave rises out of the cloud", len(sky_alive()) == 2, str(len(sky_alive())))
check("beat the first wave", beat_the_sky(), "")
wait(25)
check("a short while later a second wave comes", len(sky_alive()) == 3, str(len(sky_alive())))
check("beat the second wave", beat_the_sky(), "")
wait(45)
check("landed, and walked to the king by the chancellor", g.where() == "varenholt:throne_room", g.where())

# --- the throne room ---------------------------------------------------------
out = say(g, "talk king", show=V, n=800)
check("the king asks for the crystal and the crystal is his", "item_ilmaran_crystal" not in g.items(), str(g.items()))
out = say(g, "reply 2", show=V, n=600)
check("questioning the king takes the seal", "item_commander_seal" not in g.items(), str(g.items()))
check("the campaign starts", any("Package" in str(q.get("title")) for q in g.player.runtime_state.quests.active.values()), quest_states())
check("a courier package is handed over", any("package" in i for i in g.items()), str(g.items()))
print("    flags:", {k: v for k, v in g.player.flags.items() if not k.startswith("_")})
check("the choice is remembered as a flag", g.player.flags.get("questioned_king") is True, g.player.flags)
check("the guards march you out to the courtyard (a teleport)", g.where() == "varenholt:courtyard", g.where())
out = say(g, "go north", show=V, n=300)
check("the guards keep a dismissed courier out of the throne room", g.where() == "varenholt:courtyard" and "guards" in out, out[:200])

# --- Kessa, the night, and dawn ------------------------------------------------
say(g, "go east")
check("at the barracks", g.where() == "varenholt:barracks", g.where())
out = say(g, "talk kessa", show=V, n=600)
out = say(g, "reply 1", show=V, n=600)
check("Kessa tells you to rest and meets you at dawn", g.player.flags.get("kessa_briefed") is True, "")
say(g, "go west"); say(g, "go south")
out = say(g, "go south", show=V, n=300)
check("the gate is shut to a captain without Kessa", g.where() == "varenholt:castle_gate" and "Not alone" in out, out[:200])
say(g, "go north"); say(g, "go east"); say(g, "go north")
check("in your quarters", g.where() == "varenholt:quarters", g.where())
wait(30)
check("the night passes: morning, rested, Kessa at the gate",
      g.player.flags.get("rested_at_castle") is True and g.server.time_manager.hour == 6, "")
say(g, "go south"); say(g, "go west"); say(g, "go south")
check("at the castle gate", g.where() == "varenholt:castle_gate", g.where())
out = say(g, "talk kessa", show=V, n=600)
out = say(g, "reply 1", show=V, n=400)
kessa = [n for n in g.world.npcs.values() if n.template_id == "captain_kessa"][0]
check("Kessa goes with you", bool(kessa.properties.get("companion")), str(kessa.properties.get("companion")))
say(g, "go north")

# --- chapel, stores ----------------------------------------------------------
say(g, "go west")
check("at the chapel", g.where() == "varenholt:chapel", g.where())
g.player.health = 30
g.tick(80)
check("Rosalind heals the wounded hero", g.player.health > 30, "hp %s" % g.player.health)
print("    hp after Rosalind: %s / %s" % (g.player.health, g.player.max_health))
say(g, "go east"); say(g, "go south"); say(g, "go east")
check("at the stores", g.where() == "varenholt:stores", g.where())
say(g, "go west")

# --- the road and the cave -----------------------------------------------------
say(g, "go south")
check("on the castle road", g.where() == "road:castle_road", g.where())
r = g.fight("goblin", potion="potion"); check("beat the goblin scout", r.startswith("won"), r); print("   ", r)
say(g, "go east")
r = g.fight("wolf", potion="potion"); check("beat the road wolf", r.startswith("won"), r); print("   ", r)
say(g, "go east"); say(g, "go north"); say(g, "go in")
check("entered the cave", g.where() == "fogreach:entry", g.where())
say(g, "go east")
for i in range(2):
    r = g.fight("bat", potion="potion"); check("beat bat %d" % (i + 1), r.startswith("won"), r)
say(g, "go east")
check("at the crystal pool", g.where() == "fogreach:crystal_pool", g.where())
out = say(g, "open iron chest", show=V)
out = say(g, "look iron chest", show=V)
for _ in range(3):
    say(g, "get potion from iron chest")
potions = sum(slot.quantity for slot in g.player.inventory.slots if slot.item and slot.item.obj_id == "item_potion")
check("the chest held three potions (and Aldric has no use for an ether)", potions >= 5, str(potions))
say(g, "go south")
r = g.fight("imp", potion="potion"); check("beat the cave imp", r.startswith("won"), r); print("   ", r)
say(g, "go south"); say(g, "go down")
check("down in Hazevale", g.where() == "hazevale:valley_path", g.where())
say(g, "go south")
check("in the village square", g.where() == "hazevale:village_square", g.where())
out = say(g, "look", show=V, n=700)
check("Kessa is waiting in the square", "Kessa" in out, out[:200])

# --- the package and the drake ---------------------------------------------------
out = say(g, "give sealed package to mayor", show=V, n=600)
for _ in range(20):   # the drake takes a few told moments to arrive
    g.world.clock.advance(1.0)
    g.tick()
print("    quests:", quest_states())
check("delivering the package finishes that quest and advances the campaign", "The Fog Drake" in quest_states(), quest_states())
drake = [n for n in g.world.npcs.values() if n.template_id == "fog_drake" and n.is_alive]
check("the Fog Drake appears when its stage begins", bool(drake), [(n.template_id, n.current_room_id) for n in g.world.npcs.values() if n.template_id == "fog_drake"])
out = say(g, "look", show=V, n=500)
check("the drake is in the square with the hero", "Fog Drake" in out, out[:200])

def fight_with_spell(target, spell, max_rounds=120):
    """Aldric's Gloom Wave costs an eighth of his health and no mana: cast while he can afford it,
    drink a potion when he is low, and use the sword while the ability cools down."""
    swings = 0
    casts = 0
    for _ in range(max_rounds):
        if not g._alive(target):
            return "won in %d rounds, %d casts (hp %d/%d)" % (swings, casts, g.player.health, g.player.max_health)
        pl = g.player
        if pl.health < 0.45 * pl.max_health and any("potion" in i for i in g.items()):
            g.run("use potion")
        said = g.run("cast %s on %s" % (spell, target)) if pl.health > 0.3 * pl.max_health else ""
        if "looses a wave" in said or "wave of shadow" in said:
            casts += 1
        else:
            g.run("attack %s" % target)
        swings += 1
        if os.environ.get("WALK_DEBUG"):
            print("      round %d: hp %d/%d, %s hp %s, casts %d" % (swings, g.player.health, g.player.max_health, target, [int(n.health) for n in g._alive(target)], casts))
        g.tick(21)
        if not g.player.is_alive:
            return "player died after %d rounds" % swings
    return "no result after %d rounds" % swings


print("    hp before drake: %s / %s" % (g.player.health, g.player.max_health))
g.player.health = g.player.max_health
sword_only = None
r = fight_with_spell("drake", "gloom wave"); check("beat the Fog Drake", r.startswith("won"), r); print("   ", r)
print("    quests:", quest_states())

# --- Ryn, the summon and the title ------------------------------------------------
say(g, "go south")
check("at the shrine", g.where() == "hazevale:shrine", g.where())
out = say(g, "talk ryn complete", show=V, n=500)
print("    quests:", quest_states(), "| completed:", list(getattr(g.player.runtime_state.quests, "completed", {}) or []))
out = say(g, "talk ryn", show=V, n=600)
out = say(g, "reply 1", show=V, n=500)
out = say(g, "reply 1", show=V, n=400)
check("Ryn teaches the calling", "call_colossus" in str(getattr(g.player.runtime_state.magic, "known_spells", "")), str(getattr(g.player.runtime_state.magic, "known_spells", "")))
g.player.health = g.player.max_health   # the calling costs a quarter of his life
from engine.npcs.npc_factory import NPCFactory
foe = NPCFactory.create_npc_from_template("goblin_scout", g.world, instance_id="colossus_target")
foe.current_region_id, foe.current_room_id = "hazevale", "shrine"
foe.health = foe.max_health = 500
g.world.add_npc(foe)
out = say(g, "cast call colossus", show=V, n=300)
colossus = [n for n in g.world.npcs.values() if n.template_id == "colossus_minion" and n.is_alive]
check("the Colossus is summoned", bool(colossus), out[:150])
check("its quake hits the enemy", foe.health < 500, foe.health)
for _ in range(12):
    g.world.clock.advance(1.0)
    g.tick()
check("the Colossus is gone again soon after", not [n for n in g.world.npcs.values() if n.template_id == "colossus_minion" and n.is_alive])
out = say(g, "titles", show=V, n=400)
out = say(g, "title lightsworn", show=V, n=400)
print("    title:", flat(out, 200))
check("a class-change stand-in: the Lightsworn title can be claimed", "lightsworn" in out.lower() and ("claim" in out.lower() or "now" in out.lower() or "are" in out.lower()), out[:150])
print("    journal:", flat(say(g, "journal"), 300))

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
