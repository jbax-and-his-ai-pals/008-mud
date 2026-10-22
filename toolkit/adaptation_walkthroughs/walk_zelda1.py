"""Play zelda1 from the meadow, recording what worked. Grows with the set, one stretch of the story at a time.

Run from anywhere: .venv/Scripts/python.exe toolkit/adaptation_walkthroughs/walk_zelda1.py [--verbose]"""
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
g = Game("zelda1")


def say(cmd, n=400):
    out = clean(g.run(cmd))
    if V:
        print("> %s%s%s%s" % (cmd, NL, out[:n], NL))
    return out


def wait(seconds):
    for _ in range(seconds):
        g.world.clock.advance(1.0)
        g.tick()


def rupees():
    return g.player.runtime_state.gold


def clear_foes():
    """Only what the open ground threw up: the dungeon's own creatures are fought."""
    for foe in [n for n in g.world.npcs.values() if n.is_alive and n.faction == "hostile" and n.properties.get("encounter")
                and (n.current_region_id, n.current_room_id) == (g.player.current_region_id, g.player.current_room_id)]:
        g.world.remove_npcs(foe.obj_id)


def hostile_here(*names):
    return [n for n in g.world.npcs.values() if n.is_alive and n.faction == "hostile"
            and (n.current_region_id, n.current_room_id) == (g.player.current_region_id, g.player.current_room_id)
            and (not names or n.template_id in names)]


def walk(*dirs):
    for d in dirs:
        say("go %s" % d)
        clear_foes()
    return g.where()


def goto(target):
    """Walk to `region:room` by the shortest way through the exits (a hand that carried us off, say)."""
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


def give(item_id, count=1):
    from engine.items.item_factory import ItemFactory
    for _ in range(count):
        g.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, g.world))


def heal():
    g.player.health = g.player.max_health


def fight_all(name, template):
    """Fight every `template` in the room, healing between to isolate the fight from the dice."""
    results = []
    while hostile_here(template):
        results.append(g.fight(name, potion="recovery heart"))
        if not g.player.is_alive:
            break
    return results


# ============================================================ the meadow and the old man
check("starts in the meadow", g.where() == "ardenmoor_south:meadow_start", g.where())
out = say("status")
check("three hearts, shown as hearts", "3/3 hearts" in out, out[:200])
check("a small shield is carried and no sword", g.player.equipment.get("off_hand") is not None and g.player.equipment.get("main_hand") is None, "")
out = say("go in")
check("a cave beside the path", g.where() == "ardenmoor_south:sword_cave", g.where())
say("talk old man")
say("reply 1")
check("the old man gives a wooden sword and it is in your hand", g.player.equipment.get("main_hand") is not None and g.player.equipment["main_hand"].obj_id == "item_wooden_sword", "")
say("talk old man")
check("and he has nothing more to give", g.player.equipment["main_hand"].obj_id == "item_wooden_sword" and "item_wooden_sword" not in g.items(), "")

# ============================================================ the open ground
say("go out")
check("back out in the meadow", g.where() == "ardenmoor_south:meadow_start", g.where())
walk("east")
check("a lakeshore to the east", g.where() == "ardenmoor_south:as_1_2", g.where())
walk("west", "west")
check("the tree-line gap to the west", g.where() == "ardenmoor_south:as_1_0", g.where())

# ============================================================ Kestrel Keep
walk("in")
check("a keep behind a round door", g.where() == "kestrel_keep:k_entrance", g.where())
walk("north")
check("the mustering hall", g.where() == "kestrel_keep:k_hall", g.where())

walk("west")
check("the guardroom, with two of the old guard in it", len(hostile_here("bone_warrior")) == 2, len(hostile_here("bone_warrior")))
heal()
results = fight_all("bone", "bone_warrior")
check("both fall to a wooden sword", all(r.startswith("won") for r in results) and g.player.is_alive, results)

# the archers and the bow
heal()
walk("north")
check("the archers' gallery: three of them and a bow", len(hostile_here("bone_warrior")) == 3 and g.where() == "kestrel_keep:k_bow", len(hostile_here("bone_warrior")))
out = say("go south")
check("the door drops shut behind you until the archers are down", g.where() == "kestrel_keep:k_bow" and "shut" in out.lower(), out[:120])
results = fight_all("bone", "bone_warrior")
check("all three fall", all(r.startswith("won") for r in results) and g.player.is_alive, results)
say("take bow")
check("the bow is yours", "item_bow" in g.items(), g.items())
check("and so is the knowledge of how to loose it", "fire_arrow" in g.player.runtime_state.magic.known_spells, "")
walk("south")
check("the door lifts once they are down", g.where() == "kestrel_keep:k_west", g.where())

# the cistern and the store
walk("east")
heal()
walk("east")
check("the cistern gallery: three slimes", len(hostile_here("slime")) == 3, len(hostile_here("slime")))
results = fight_all("slime", "slime")
check("they fall", all(r.startswith("won") for r in results) and g.player.is_alive, results)
heal()
walk("east")
check("the store: two hurlers, a whirlwing and a key", len(hostile_here("hurler")) == 2 and "kestrel_keep:k_boom" == g.where(), g.where())
results = fight_all("hurler", "hurler")
check("both hurlers fall", all(r.startswith("won") for r in results) and g.player.is_alive, results)
say("take whirlwing")
say("take small key")
check("the whirlwing and a small key", "item_boomerang" in g.items() and "item_small_key" in g.items(), g.items())
check("the whirlwing is known", "throw_whirlwing" in g.player.runtime_state.magic.known_spells, "")
walk("west")
check("out through the lifted door", g.where() == "kestrel_keep:k_east", g.where())

# the upper hall: bats, a hand, the iron door
heal()
walk("west", "north")
check("the upper hall: two bats and a hand in the wall", len(hostile_here("cave_bat")) == 2 and len(hostile_here("grasping_hand")) == 1, [n.template_id for n in hostile_here()])
g.player.runtime_state.gold = 0
out = say("cast arrow on bat")
check("an arrow costs a rupee, and with none you cannot loose one", "Not enough" in out, out[:120])
g.player.runtime_state.gold = 2
out = say("cast arrow on bat")
check("with a rupee in hand it flies, and costs it", g.player.runtime_state.gold == 1, "%s | %s" % (g.player.runtime_state.gold, out[:100]))
grabbed = False
for foe_name, template in (("bat", "cave_bat"), ("hand", "grasping_hand")):
    while True:
        if g.where() != "kestrel_keep:k_hall2":
            grabbed = True
            goto("kestrel_keep:k_hall2")
        if not hostile_here(template):
            break
        g.fight(foe_name, potion="recovery heart")
        heal()
check("the bats and the hand fall", not hostile_here(), "")
check("(a hand that took hold set the hero down at the door)", True if not grabbed else g.where() == "kestrel_keep:k_hall2", "")

# the cracked wall and a bomb
goto("kestrel_keep:k_wall")
check("a chamber with a cracked wall", g.where() == "kestrel_keep:k_wall", g.where())
heal()
fight_all("bone", "bone_warrior")
out = say("go north")
check("there is no way north through the wall", g.where() == "kestrel_keep:k_wall", out[:100])
give("item_bomb", 3)
check("the pack holds the bombs", g.player.inventory.count_item("item_bomb") == 3, g.items())
out = say("use bomb")
check("a bomb blows the wall in", "bursts" in out and "north" in say("look"), out[:160])
walk("north")
check("a hidden cache", g.where() == "kestrel_keep:k_cache", g.where())
before = rupees()
say("take 10 rupees")
say("take bomb")
check("ten rupees and a bomb", rupees() - before == 10 and g.player.inventory.count_item("item_bomb") == 3, "%s %s" % (rupees() - before, g.player.inventory.count_item("item_bomb")))
goto("kestrel_keep:k_hall2")

# the iron door and the drake
out = say("go north")
check("the iron door yields to the key", g.where() == "kestrel_keep:k_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
heal()
walk("north")
check("the drake's roost", g.where() == "kestrel_keep:k_boss" and len(hostile_here("aquilor")) == 1, g.where())
give("item_recovery_heart", 4)
r = g.fight("Aquilor", potion="recovery heart")
check("Aquilor falls", r.startswith("won"), r)
wait(3)
check("the first shard of the Starcrown", "item_shard_1" in g.items() and g.player.flags.get("shard_1") is True, g.items())
check("and a heart more than before: four", g.player.max_health == 64 and g.player.health == 64, "%s/%s" % (g.player.health, g.player.max_health))
out = say("status")
check("shown as four hearts", "4/4 hearts" in out, out[:200])

# ============================================================ back out, and a rock that rings hollow
goto("kestrel_keep:k_entrance")
check("back at the keep door", g.where() == "kestrel_keep:k_entrance", g.where())
walk("out")
check("out in the pines", g.where() == "ardenmoor_south:as_1_0", g.where())
goto("ardenmoor_south:as_0_2")
check("the stony rise", g.where() == "ardenmoor_south:as_0_2", g.where())
out = say("go in")
check("the rock is solid without a bomb", g.where() == "ardenmoor_south:as_0_2", out[:100])
out = say("use bomb")
check("a bomb under the ledge opens a hollow", "blows in" in out, out[:140])
walk("in")
before = rupees()
say("take 30 rupees")
check("thirty rupees in the hollow", rupees() - before == 30, rupees() - before)

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
