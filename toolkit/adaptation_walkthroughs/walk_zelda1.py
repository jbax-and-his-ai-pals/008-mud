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


# ============================================================ slice 2: the east
def fight_room(*pairs):
    """Fight every named creature of the room in turn, mending between, and say whether the hero is alive."""
    for name, template in pairs:
        guard = 0
        while hostile_here(template) and guard < 12:
            guard += 1
            heal()
            g.fight(name, potion="recovery heart")
            if not g.player.is_alive:
                return False
    return True


goto("ardenmoor_east:ae_1_1")
check("the old dock on Lake Sorrel", g.where() == "ardenmoor_east:ae_1_1", g.where())
out = say("go east")
check("the water past the dock needs a raft", g.where() == "ardenmoor_east:ae_1_1" and "raft" in out.lower(), out[:120])

# the lantern shop
goto("ardenmoor_east:ae_0_2")
walk("in")
check("a lantern-lit cave and a shopkeeper", g.where() == "ardenmoor_east:shop_cave", g.where())
say("trade old man")
listing = say("list")
check("bombs for twenty rupees and hearts for ten", "bomb" in listing and "20" in listing and "recovery heart" in listing and "10" in listing, listing[:200])
g.player.runtime_state.gold = 100
before = g.player.inventory.count_item("item_bomb")
say("buy bomb")
check("a bomb is bought for twenty", g.player.runtime_state.gold == 80 and g.player.inventory.count_item("item_bomb") == before + 1, g.player.runtime_state.gold)
give("item_bomb", 8 - g.player.inventory.count_item("item_bomb"))
gold = g.player.runtime_state.gold
out = say("buy bomb")
check("a full pack refuses a ninth and keeps the money", g.player.runtime_state.gold == gold and g.player.inventory.count_item("item_bomb") == 8 and "cannot carry" in out, out[:100])
say("stoptrade")
walk("out")

# the white sword's gate
goto("ardenmoor_east:ae_0_1")
walk("in")
check("a cave behind the waterfall", g.where() == "ardenmoor_east:waterfall_cave", g.where())
out = say("talk old man")
check("with four hearts he gives nothing", "item_pale_blade" not in g.items() and g.player.equipment["main_hand"].obj_id == "item_wooden_sword", out[:100])
walk("out")

# the stone-jaw's hint
goto("ardenmoor_east:ae_2_0")
walk("in")
out = say("talk old man")
check("a hint about smoke and thunder", "smoke" in out.lower(), out[:120])
walk("out")

# ---- the Crescent Vault
goto("ardenmoor_east:ae_3_2")
walk("in")
check("the stair down to the Crescent Vault", g.where() == "crescent_vault:v_entrance", g.where())
walk("north")
check("the Hall of Horns: three cord-snakes", len(hostile_here("cord_snake")) == 3, len(hostile_here("cord_snake")))
check("they fall", fight_room(("cord", "cord_snake")), "")
walk("west")
check("the dry cistern: two great slimes", len(hostile_here("great_slime")) == 2, len(hostile_here("great_slime")))
heal()
g.fight("great slime", potion="recovery heart")
check("a great slime bursts into two slimes", len(hostile_here("slime")) >= 2, [n.template_id for n in hostile_here()])
check("all of them fall", fight_room(("great slime", "great_slime"), ("slime", "slime")), "")
walk("north")
check("the powder store, through the lifted door", g.where() == "crescent_vault:v_powder", g.where())
while g.player.inventory.count_item("item_bomb") > 0:
    g.player.inventory.remove_item("item_bomb", 1)
for _ in range(3):
    say("take bomb")
check("three bombs on the shelf", g.player.inventory.count_item("item_bomb") == 3, g.player.inventory.count_item("item_bomb"))
goto("crescent_vault:v_worm")
check("the worm's den", g.where() == "crescent_vault:v_worm", g.where())
check("the great worm falls", fight_room(("worm", "great_worm")), "")
say("take stormwing")
say("take small key")
check("the stormwing and a key", "item_stormwing" in g.items() and "item_small_key" in g.items(), g.items())
check("the stormwing is known", "throw_stormwing" in g.player.runtime_state.magic.known_spells, "")
goto("crescent_vault:v_upper")
check("the upper hall: two bone warriors", len(hostile_here("bone_warrior")) == 2, len(hostile_here("bone_warrior")))
check("they fall", fight_room(("bone", "bone_warrior")), "")
before = rupees()
say("use bomb")
walk("east")
check("a bomb opens the cracked wall to a closet", g.where() == "crescent_vault:v_cache", g.where())
say("take 30 rupees")
check("thirty rupees in the closet", rupees() - before == 30, rupees() - before)
goto("crescent_vault:v_upper")
out = say("go north")
check("the black door yields to the key", g.where() == "crescent_vault:v_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
check("two cord-snakes in the antechamber fall", fight_room(("cord", "cord_snake")), "")
heal()
walk("north")
check("the jaw's lair", g.where() == "crescent_vault:v_boss" and len(hostile_here("stone_jaw")) == 1, g.where())
jaw = hostile_here("stone_jaw")[0]
health = jaw.health
heal()
for _ in range(3):
    say("attack stone")
    wait(2)
check("a sword does nothing to the stone-jaw", jaw.health == health, "%s -> %s" % (health, jaw.health))
give("item_bomb", 2 - g.player.inventory.count_item("item_bomb")) if g.player.inventory.count_item("item_bomb") < 2 else None
heal()
say("use bomb")
check("a bomb hurts it", jaw.health < health, "%s -> %s" % (health, jaw.health))
heal()
say("use bomb")
wait(3)
check("and two bombs finish it", not jaw.is_alive, jaw.health)
check("the second shard of the Starcrown", "item_shard_2" in g.items() and g.player.flags.get("shard_2") is True, g.items())
check("and a fifth heart", g.player.max_health == 80, g.player.max_health)

# ---- the white sword
goto("ardenmoor_east:ae_0_1")
walk("in")
say("talk old man")
say("reply 1")
check("with five hearts the old man gives the pale blade, and it is wielded", g.player.equipment["main_hand"].obj_id == "item_pale_blade", g.player.equipment["main_hand"].obj_id)
check("it cuts twice as deep: sixteen against the wooden sword's eight", g.player.get_attack_power() in range(15, 20), g.player.get_attack_power())
say("talk old man")
walk("out")

# ---- the Pinwheel
goto("ardenmoor_east:ae_1_0")
walk("in")
check("the pinwheel door", g.where() == "pinwheel:l_entrance", g.where())
walk("north")
check("the wheel hall: a great slime and two bats", len(hostile_here("great_slime")) == 1 and len(hostile_here("cave_bat")) == 2, [n.template_id for n in hostile_here()])
check("they fall", fight_room(("great slime", "great_slime"), ("slime", "slime"), ("bat", "cave_bat")), "")
walk("west")
check("the weir gallery: three bone warriors", len(hostile_here("bone_warrior")) == 3, len(hostile_here("bone_warrior")))
check("they fall", fight_room(("bone", "bone_warrior")), "")
walk("north")
check("the boat store: two great slimes shut the door behind", g.where() == "pinwheel:l_raft" and len(hostile_here("great_slime")) == 2, g.where())
out = say("go south")
check("the door stays shut while they heave", g.where() == "pinwheel:l_raft", out[:100])
check("they and their children fall", fight_room(("great slime", "great_slime"), ("slime", "slime")), "")
say("take raft")
check("the raft", "item_raft" in g.items(), g.items())
goto("pinwheel:l_east")
check("the spoke of teeth", g.where() == "pinwheel:l_east", g.where())
check("its guards fall", fight_room(("bone", "bone_warrior"), ("bat", "cave_bat")), "")
say("take small key")
goto("pinwheel:l_upper")
check("the upper wheel", g.where() == "pinwheel:l_upper", g.where())
heal()
grabbed = False
for name, template in (("bat", "cave_bat"), ("hand", "grasping_hand")):
    guard = 0
    while guard < 12:
        guard += 1
        if g.where() != "pinwheel:l_upper":
            grabbed = True
            goto("pinwheel:l_upper")
        if not hostile_here(template):
            break
        heal()
        g.fight(name, potion="recovery heart")
give("item_bomb", 2 - g.player.inventory.count_item("item_bomb")) if g.player.inventory.count_item("item_bomb") < 2 else None
before = rupees()
say("use bomb")
walk("west")
check("a closet behind the west wall", g.where() == "pinwheel:l_cache", g.where())
say("take 10 rupees")
check("ten rupees", rupees() - before == 10, rupees() - before)
walk("east")
out = say("go north")
check("the black door yields to the key", g.where() == "pinwheel:l_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
check("the hall of stalks: two bone warriors fall", fight_room(("bone", "bone_warrior")), "")
heal()
walk("north")
check("the bloom chamber: the flower and four mouths", len(hostile_here("snapjaw_mouth")) == 4 and len(hostile_here("snapjaw_bloom")) == 1, [n.template_id for n in hostile_here()])
bloom = hostile_here("snapjaw_bloom")[0]
out = say("attack bloom")
check("the flower cannot be reached past its mouths", bloom.health == bloom.max_health and "mouths" in out.lower(), out[:140])
guard = 0
while hostile_here("snapjaw_mouth") and guard < 12:
    guard += 1
    heal()
    g.fight("mouth", potion="recovery heart")
check("the four mouths fall", not hostile_here("snapjaw_mouth") and g.player.is_alive, [n.template_id for n in hostile_here()])
heal()
g.fight("bloom", potion="recovery heart")
wait(3)
check("and then the flower", not bloom.is_alive, bloom.health)
check("the third shard and a sixth heart", "item_shard_3" in g.items() and g.player.max_health == 96, "%s %s" % (g.items(), g.player.max_health))

# ---- the raft, and the island
goto("ardenmoor_east:ae_1_1")
out = say("go east")
check("with the raft the dock reaches an island", g.where() == "ardenmoor_east:ae_island", g.where() + " " + out[:80])
check("and the raft is not used up", "item_raft" in g.items(), g.items())
say("take heart container")
check("a heart container in the roots: seven hearts", g.player.max_health == 112 and "item_heart_container" not in g.items(), "%s %s" % (g.player.max_health, g.items()))
out = say("status")
check("shown as seven hearts", "7/7 hearts" in out, out[:200])
walk("west")

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
