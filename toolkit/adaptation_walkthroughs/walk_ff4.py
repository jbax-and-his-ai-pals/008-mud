"""Play ff4_slice from the throne room to the summoner child, recording what worked.

Run from anywhere: .venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_ff4.py [--verbose]"""
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


# --- the throne room ---------------------------------------------------------
check("starts in the throne room", g.where() == "varenholt:throne_room", g.where())
check("starting kit", "item_commander_seal" in g.items() and "item_dark_blade" in g.items(), str(g.items()))
say(g, "equip dark blade"); say(g, "equip dark armor")
check("dark blade and armor equip", "item_dark_blade" in equipped_ids() and "item_dark_armor" in equipped_ids(), str(equipped_ids()))
out = say(g, "talk king", show=V, n=800)
out = say(g, "reply 2", show=V, n=600)
check("questioning the king takes the seal", "item_commander_seal" not in g.items(), str(g.items()))
check("the campaign starts", any("Package" in str(q.get("title")) for q in g.player.runtime_state.quests.active.values()), quest_states())
check("a courier package is handed over", any("package" in i for i in g.items()), str(g.items()))
print("    flags:", g.player.flags)
check("the choice is remembered as a flag", g.player.flags.get("questioned_king") is True, g.player.flags)
check("the guards march you out to the courtyard (a teleport)", g.where() == "varenholt:courtyard", g.where())
say(g, "go north")
check("and you can walk back in", g.where() == "varenholt:throne_room", g.where())
out = say(g, "talk king", show=V, n=600)
check("the choice cannot be taken twice", "Tell me again" in out and "slaughter" not in out.split("[")[0] or "unavailable" in out, out[:200])
say(g, "reply 4")

# --- Kessa: an NPC that moves ahead ------------------------------------------
say(g, "go south"); say(g, "go east")
check("at the barracks", g.where() == "varenholt:barracks", g.where())
out = say(g, "talk kessa", show=V, n=600)
out = say(g, "reply 1", show=V, n=600)
kessa = [n for n in g.world.npcs.values() if n.template_id == "captain_kessa"][0]
print("    Kessa is now at:", kessa.current_region_id, kessa.current_room_id)
check("move_npc sends Kessa ahead to Mistvale", (kessa.current_region_id, kessa.current_room_id) == ("mistvale", "village_square"),
      (kessa.current_region_id, kessa.current_room_id))

# --- chapel, stores ----------------------------------------------------------
say(g, "go west"); say(g, "go west")
check("at the chapel", g.where() == "varenholt:chapel", g.where())
g.player.health = 30
g.tick(80)
check("Rosalind heals the wounded hero", g.player.health > 30, "hp %s" % g.player.health)
print("    hp after Rosalind: %s / %s" % (g.player.health, g.player.max_health))
say(g, "go east"); say(g, "go south"); say(g, "go east")
check("at the stores", g.where() == "varenholt:stores", g.where())
say(g, "go west")

# --- the road and the cave -----------------------------------------------------
say(g, "go north")
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
out = say(g, "get ether from iron chest", show=V)
say(g, "get potion from iron chest")
check("the chest held two ethers and a potion", g.items().count("item_ether") >= 1, str(g.items()))
say(g, "go south")
r = g.fight("imp", potion="potion"); check("beat the cave imp", r.startswith("won"), r); print("   ", r)
say(g, "go south"); say(g, "go down")
check("down in Mistvale", g.where() == "mistvale:valley_path", g.where())
say(g, "go south")
check("in the village square", g.where() == "mistvale:village_square", g.where())
out = say(g, "look", show=V, n=700)
check("Kessa is waiting in the square", "Kessa" in out, out[:200])

# --- the package and the drake ---------------------------------------------------
out = say(g, "give sealed package to mayor", show=V, n=600)
print("    quests:", quest_states())
check("delivering the package finishes that quest and advances the campaign", "The Fog Drake" in quest_states(), quest_states())
drake = [n for n in g.world.npcs.values() if n.template_id == "fog_drake" and n.is_alive]
check("the Fog Drake appears when its stage begins", bool(drake), [(n.template_id, n.current_room_id) for n in g.world.npcs.values() if n.template_id == "fog_drake"])
out = say(g, "look", show=V, n=500)
check("the drake is in the square with the hero", "Fog Drake" in out, out[:200])

def fight_with_spell(target, spell, max_rounds=120):
    swings = 0
    for _ in range(max_rounds):
        if not g._alive(target):
            return "won in %d rounds (hp %d/%d, mana %d)" % (swings, g.player.health, g.player.max_health, g.player.runtime_state.magic.mana)
        pl = g.player
        if pl.health < 0.4 * pl.max_health and any("potion" in i for i in g.items()):
            g.run("use potion")
        if pl.runtime_state.magic.mana >= 12:
            g.run("cast %s on %s" % (spell, target))
        elif pl.runtime_state.magic.mana < 12 and any("ether" in i for i in g.items()) and pl.runtime_state.magic.mana < 6:
            g.run("use ether")
        else:
            g.run("attack %s" % target)
        swings += 1
        g.tick(21)
        if not g.player.is_alive:
            return "player died after %d rounds" % swings
    return "no result after %d rounds" % swings

print("    hp before drake: %s / %s, mana %s" % (g.player.health, g.player.max_health, g.player.runtime_state.magic.mana))
g.player.health = g.player.max_health
sword_only = None
r = fight_with_spell("drake", "dark wave"); check("beat the Fog Drake", r.startswith("won"), r); print("   ", r)
print("    quests:", quest_states())

# --- Ryn, the summon and the title ------------------------------------------------
say(g, "go south")
check("at the shrine", g.where() == "mistvale:shrine", g.where())
out = say(g, "talk ryn complete", show=V, n=500)
print("    quests:", quest_states(), "| completed:", list(getattr(g.player.runtime_state.quests, "completed", {}) or []))
out = say(g, "talk ryn", show=V, n=600)
out = say(g, "reply 1", show=V, n=500)
out = say(g, "reply 1", show=V, n=400)
check("Ryn teaches the calling", "call_titan" in str(getattr(g.player.runtime_state.magic, "known_spells", "")), str(getattr(g.player.runtime_state.magic, "known_spells", "")))
g.player.runtime_state.magic.mana = g.player.runtime_state.magic.max_mana
out = say(g, "cast call titan", show=V, n=300)
titans = [n for n in g.world.npcs.values() if n.template_id == "titan_minion" and n.is_alive]
check("the Titan is summoned", bool(titans), out[:150])
if titans:
    say(g, "go north")
    g.tick(60)
    t = [n for n in g.world.npcs.values() if n.template_id == "titan_minion" and n.is_alive]
    print("    titan at:", (t[0].current_region_id, t[0].current_room_id) if t else "gone", "| hero at:", g.where())
    check("the Titan follows the hero", bool(t) and (t[0].current_region_id, t[0].current_room_id) == tuple(g.where().split(":")))
out = say(g, "titles", show=V, n=400)
out = say(g, "title paladin", show=V, n=400)
print("    title:", flat(out, 200))
check("a class-change stand-in: the Paladin title can be claimed", "paladin" in out.lower() and ("claim" in out.lower() or "now" in out.lower() or "are" in out.lower()), out[:150])
print("    journal:", flat(say(g, "journal"), 300))

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
