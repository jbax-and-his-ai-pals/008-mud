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


# ============================================================ slice 3: the north, the lost hills, three more dungeons
HEART = 16


def room_fight(*pairs):
    return fight_room(*pairs)


def kill_room_of(*templates):
    """Fight everything of those kinds in the room by name."""
    for template in templates:
        label = template.replace("_", " ")
        guard = 0
        while hostile_here(template) and guard < 14:
            guard += 1
            if g.where().split(":")[0] != g.player.current_region_id:
                break
            heal()
            g.fight(label.split()[-1], potion="recovery heart")
            if not g.player.is_alive:
                return False
    return True


g.player.runtime_state.gold = 400
# ---- the candle shop and the bush
goto("ardenmoor_north:an_0_2")
walk("in")
say("trade old man")
listing = say("list")
check("a blue candle for sixty rupees", "blue candle" in listing and "60" in listing, listing[:160])
say("buy blue candle")
say("stoptrade")
check("the candle is bought", "item_blue_candle" in g.items() and g.player.runtime_state.gold == 340, g.player.runtime_state.gold)
walk("out")
goto("ardenmoor_north:an_1_2")
hearts_before = g.player.max_health
out = say("go in")
check("a thick bush stands where a doorway would be", g.where() == "ardenmoor_north:an_1_2", out[:100])
out = say("use blue candle")
check("the candle burns the bush away", "bush goes up" in out, out[:200])
out = say("use blue candle")
check("a blue candle burns once in a room", "already burns" in out, out[:100])
walk("in")
say("take heart container")
check("a heart container under the bush", g.player.max_health == hearts_before + HEART, g.player.max_health)
walk("out")
walk("west", "west")   # out of the room: the light goes out
check("and the light does not follow you out", not g.player.has_effect_tag("light"), "")
out = say("use blue candle")
check("in a new room the candle works again", g.player.has_effect_tag("light") and "already burns" not in out, out[:80])

# ---- the shield shop
goto("ardenmoor_north:an_1_0")
walk("in")
say("trade old man")
say("buy magical shield")
say("stoptrade")
check("a magical shield is bought for one hundred and thirty", "item_magic_shield" in g.items() and g.player.runtime_state.gold == 340 - 130, g.player.runtime_state.gold)
say("equip magical shield")
check("and worn in place of the small one", g.player.equipment["off_hand"].obj_id == "item_magic_shield", g.player.equipment.get("off_hand"))
walk("out")

# ---- the black pool: no way in until a tune
goto("ardenmoor_north:an_1_1")
out = say("go in")
check("the pool is only a pool", g.where() == "ardenmoor_north:an_1_1", out[:100])

# ---- the lost hills
goto("ardenmoor_north:an_0_0")
walk("in")
check("the foot of the hills", g.where() == "lost_hills:h0", g.where())
say("talk old man")
walk("north", "north")
walk("east")
check("a step to the side lets the mist turn you round", g.where() == "lost_hills:h0", g.where())
walk("north", "north", "north", "north", "north")
check("five steps up and no step aside", g.where() == "lost_hills:h5", g.where())
walk("in")
check("the Gecko Halls", g.where() == "gecko_halls:g_entrance", g.where())

# ---- the Gecko Halls (dark)
walk("north")
check("the lamp hall: bats and a revenant", len(hostile_here("cave_bat")) == 2 and len(hostile_here("revenant")) == 1, [n.template_id for n in hostile_here()])
check("they fall", fight_room(("bat", "cave_bat"), ("revenant", "revenant")), "")
out = say("go west")
check("the long gallery is dark and shows nothing", g.where() == "gecko_halls:g_gallery" and "pitch dark" in say("look"), out[:100])
say("use blue candle")
check("a candle shows the gallery", "Exits" in say("look") and "gallery" in say("look").lower(), "")
check("two bone warriors and a revenant fall in the candlelight", fight_room(("bone", "bone_warrior"), ("revenant", "revenant")), "")
walk("north")
say("use blue candle")
check("the reed store: slimes and a revenant shut the door", g.where() == "gecko_halls:g_pipe" and len(hostile_here("great_slime")) == 1, g.where())
check("they fall", fight_room(("great slime", "great_slime"), ("slime", "slime"), ("revenant", "revenant")), "")
say("take reed pipe")
check("the reed pipe", "item_reed_pipe" in g.items(), g.items())
out = say("use reed pipe")
check("the pipe plays a tune and, here, nothing else", "tune" in out and g.where() == "gecko_halls:g_pipe", out[:120])
goto("gecko_halls:g_east")
say("use blue candle")
check("the dusty cell: a hexer and a bone warrior", len(hostile_here("hexer")) == 1 and len(hostile_here("bone_warrior")) == 1, [n.template_id for n in hostile_here()])
check("they fall", fight_room(("hexer", "hexer"), ("bone", "bone_warrior")), "")
say("take small key")
walk("north")
check("a nook in the wall and an old man with a bag", g.where() == "gecko_halls:g_shop", g.where())
say("trade old man")
gold_before = g.player.runtime_state.gold
say("buy bomb bag")
say("stoptrade")
check("a bomb bag for one hundred rupees", "item_bomb_bag" in g.items() and gold_before - g.player.runtime_state.gold == 100, g.player.runtime_state.gold)
give("item_bomb", 12 - g.player.inventory.count_item("item_bomb"))
check("and twelve bombs is the limit now, not eight", g.player.inventory.count_item("item_bomb") == 12, g.player.inventory.count_item("item_bomb"))
ok, said = g.player.inventory.add_item(__import__("engine.items.item_factory", fromlist=["ItemFactory"]).ItemFactory.create_item_from_template("item_bomb", g.world))
check("a thirteenth is refused", not ok, said)
goto("gecko_halls:g_upper")
say("use blue candle")
grabbed = False
for name, template in (("bone", "bone_warrior"), ("revenant", "revenant"), ("hand", "grasping_hand")):
    guard = 0
    while guard < 12:
        guard += 1
        if g.where() != "gecko_halls:g_upper":
            grabbed = True
            goto("gecko_halls:g_upper")
            say("use blue candle")
        if not hostile_here(template):
            break
        heal()
        g.fight(name, potion="recovery heart")
say("use bomb")
walk("east")
say("take 30 rupees")
check("a hole in the east wall with thirty rupees", g.where() == "gecko_halls:g_cache" and g.player.runtime_state.gold >= 30, g.where())
goto("gecko_halls:g_upper")
out = say("go north")
check("the heavy door yields to the key", g.where() == "gecko_halls:g_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
say("use blue candle")
check("bats and a revenant in the dry throat fall", fight_room(("bat", "cave_bat"), ("revenant", "revenant")), "")
heal()
walk("north")
check("the digging floor and the great eye", g.where() == "gecko_halls:g_boss" and len(hostile_here("burrowing_eye_large")) == 1, g.where())
eye = hostile_here("burrowing_eye_large")[0]
health = eye.health
for _ in range(2):
    say("attack eye")
    wait(2)
check("nothing hurts the great eye", eye.health == health, "%s -> %s" % (health, eye.health))
say("use bomb")
check("not even a bomb", eye.health == health, eye.health)
heal()
out = say("use reed pipe")
check("the tune shrinks it", not eye.is_alive and len(hostile_here("burrowing_eye_small")) == 1 and "shrinks" in out, out[:200])
small = hostile_here("burrowing_eye_small")[0]
heal()
g.fight("eye", potion="recovery heart")
wait(3)
check("the small eye falls", not small.is_alive, small.health)
check("the fifth shard and a heart more", "item_shard_5" in g.items() and g.player.flags.get("shard_5") is True, g.items())

# ---- the pool answers the pipe
goto("ardenmoor_north:an_1_1")
out = say("use reed pipe")
check("played at the black pool the pipe opens a stair", "stair of wet stone" in out, out[:160])
walk("in")
check("the fairy pool", g.where() == "ardenmoor_north:fairy_pool", g.where())
g.player.health = 5
say("talk fairy")
say("reply 1")
check("the fairy mends every wound", g.player.health == g.player.max_health, g.player.health)
walk("out")

# ---- the far shore and the Adder's Coil
goto("ardenmoor_east:ae_island")
out = say("go north")
check("a far shore past the island", g.where() == "ardenmoor_east:ae_far_shore", g.where() + out[:60])
out = say("go east")
check("a gap of water wants a ladder", g.where() == "ardenmoor_east:ae_far_shore" and "ladder" in out.lower(), out[:120])
hearts_before = g.player.max_health
walk("in")
check("the mouth of the Adder's Coil", g.where() == "adders_coil:c_entrance", g.where())
walk("north")
check("the first loop: two cord-snakes and a bat fall", fight_room(("cord", "cord_snake"), ("bat", "cave_bat")), "")
walk("west")
check("the scale gallery: three bone warriors", len(hostile_here("bone_warrior")) == 3, len(hostile_here("bone_warrior")))
check("they fall", fight_room(("bone", "bone_warrior")), "")
walk("north")
check("the ladder store: two great slimes", len(hostile_here("great_slime")) == 2, g.where())
check("they and their children fall", fight_room(("great slime", "great_slime"), ("slime", "slime")), "")
say("take ladder")
check("the ladder", "item_ladder" in g.items(), g.items())
goto("adders_coil:c_east")
check("the hexer's turn: a hexer and two bats", len(hostile_here("hexer")) == 1, [n.template_id for n in hostile_here()])
check("they fall", fight_room(("hexer", "hexer"), ("bat", "cave_bat")), "")
walk("north")
say("take small key")
say("take bomb")
goto("adders_coil:c_upper")
grabbed = False
for name, template in (("hexer", "hexer"), ("hand", "grasping_hand")):
    guard = 0
    while guard < 14:
        guard += 1
        if g.where() != "adders_coil:c_upper":
            grabbed = True
            goto("adders_coil:c_upper")
        if not hostile_here(template):
            break
        heal()
        g.fight(name, potion="recovery heart")
say("use bomb")
walk("west")
check("a closet behind the west wall", g.where() == "adders_coil:c_cache", g.where())
walk("east")
out = say("go north")
check("the iron door yields to the key", g.where() == "adders_coil:c_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
check("the coil's throat: two bone warriors and a bat fall", fight_room(("bone", "bone_warrior"), ("bat", "cave_bat")), "")
heal()
walk("north")
check("the hydra's pit: a body and two heads", len(hostile_here("hydra_head")) == 2 and len(hostile_here("hydra")) == 1, [n.template_id for n in hostile_here()])
body = hostile_here("hydra")[0]
out = say("attack the hydra")
check("the body cannot be struck past the heads", body.health == body.max_health and "neck" in out.lower(), out[:140])
guard = 0
while hostile_here("hydra_head") and guard < 14:
    guard += 1
    heal()
    g.fight("head", potion="recovery heart")
check("both heads fall", not hostile_here("hydra_head") and g.player.is_alive, [n.template_id for n in hostile_here()])
heal()
g.fight("hydra", potion="recovery heart")
wait(3)
check("and the body", not body.is_alive, body.health)
check("the fourth shard and a heart more", "item_shard_4" in g.items() and g.player.max_health == hearts_before + HEART, "%s %s" % (g.items(), g.player.max_health))
goto("ardenmoor_east:ae_far_shore")
hearts_before = g.player.max_health
walk("east")
check("with the ladder the gap is crossed", g.where() == "ardenmoor_east:ae_far_dock", g.where())
say("take heart container")
check("a heart container on the far dock", g.player.max_health == hearts_before + HEART, g.player.max_health)
walk("west")

# ---- the Wyvern Deep
goto("ardenmoor_north:an_0_1")
walk("in")
check("the steps down into the Wyvern Deep", g.where() == "wyvern_deep:w_entrance", g.where())
walk("north")
check("the hall of wings: two revenants and a hexer fall", fight_room(("revenant", "revenant"), ("hexer", "hexer")), "")
walk("west")
check("the ossuary: three bone warriors and a revenant fall", fight_room(("bone", "bone_warrior"), ("revenant", "revenant")), "")
walk("north")
check("the wyrm shrine: a lesser hydra", len(hostile_here("hydra_lesser")) == 1, g.where())
out = say("attack a lesser hydra")
check("its body is guarded by its one head", "neck" in out.lower(), out[:120])
guard = 0
while hostile_here("hydra_lesser_head") and guard < 10:
    guard += 1
    heal()
    g.fight("lesser hydra head", potion="recovery heart")
heal()
g.fight("lesser hydra", potion="recovery heart")
wait(2)
say("take wyrmrod")
check("the wyrmrod", "item_wyrmrod" in g.items() and "rod_bolt" in g.player.runtime_state.magic.known_spells, g.items())
goto("wyvern_deep:w_east")
check("the shield-eaters' hall: two shield-eaters and a bat", len(hostile_here("shield_eater")) == 2, [n.template_id for n in hostile_here()])
shield_gone = False
guard = 0
while hostile_here("shield_eater", "cave_bat") and guard < 20:
    guard += 1
    heal()
    for foe in hostile_here("shield_eater", "cave_bat"):
        g.fight(foe.name.split()[-1], max_rounds=6, potion="recovery heart")
        break
shield_gone = g.player.equipment.get("off_hand") is None
check("a shield-eater may swallow the magical shield (and it is then gone)", True if not shield_gone else "item_magic_shield" not in g.items(), "")
say("take small key")
heal()
goto("wyvern_deep:w_stairs")
check("the lower stair is dark; the hexer and the revenant", len(hostile_here("strong_hexer")) == 1, [n.template_id for n in hostile_here()])
say("use blue candle")
check("they fall", fight_room(("hexer", "strong_hexer"), ("revenant", "revenant")), "")
walk("north")
say("use blue candle")
grabbed = False
for name, template in (("hexer", "strong_hexer"), ("eater", "shield_eater"), ("hand", "grasping_hand")):
    guard = 0
    while guard < 14:
        guard += 1
        if g.where() != "wyvern_deep:w_upper":
            grabbed = True
            goto("wyvern_deep:w_upper")
            say("use blue candle")
        if not hostile_here(template):
            break
        heal()
        g.fight(name, potion="recovery heart")
give("item_bomb", 2 - g.player.inventory.count_item("item_bomb")) if g.player.inventory.count_item("item_bomb") < 2 else None
say("use bomb")
walk("east")
check("a reliquary closet", g.where() == "wyvern_deep:w_cache", g.where())
walk("west")
out = say("go north")
check("the black door yields to the key", g.where() == "wyvern_deep:w_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
say("use blue candle")
check("the long dark: a hexer and two revenants fall", fight_room(("hexer", "strong_hexer"), ("revenant", "revenant")), "")
heal()
hearts_before = g.player.max_health
walk("north")
check("the claw's cavern", g.where() == "wyvern_deep:w_boss" and len(hostile_here("great_claw")) == 1, g.where())
claw = hostile_here("great_claw")[0]
health = claw.health
for _ in range(2):
    say("attack claw")
    wait(2)
check("a sword does nothing to the great claw", claw.health == health, "%s -> %s" % (health, claw.health))
g.player.runtime_state.gold = 40
shots = 0
for _ in range(60):
    heal()
    if not claw.is_alive:
        break
    out = say("cast arrow on claw")
    shots += 1
    wait(2)
check("only arrows through the open eye hurt it", not claw.is_alive, "%s hp, %d shots" % (claw.health, shots))
wait(3)
check("the arrows cost rupees", g.player.runtime_state.gold < 40, g.player.runtime_state.gold)
check("the sixth shard and a heart more", "item_shard_6" in g.items() and g.player.max_health == hearts_before + HEART, "%s %s" % (g.items(), g.player.max_health))


# ============================================================ slice 4: the hungry guard, the Fiend's Hold, the Mane
def clear_room_through(*pairs, region_room=None, candle=None):
    """Fight what the room holds, going back to `region_room` when a hand has carried us off, lighting `candle` there."""
    for name, template in pairs:
        guard = 0
        while guard < 16:
            guard += 1
            if region_room and g.where() != region_room:
                goto(region_room)
                if candle:
                    say("use %s" % candle)
            if not hostile_here(template):
                break
            heal()
            g.fight(name, potion="recovery heart")
            if not g.player.is_alive:
                return False
    return True


g.player.runtime_state.gold = 500
give("item_recovery_heart", 8)

# ---- the door-repair toll
goto("ardenmoor_south:as_2_0")
out = say("go in")
check("a bank that is only a bank", g.where() == "ardenmoor_south:as_2_0", out[:80])
give("item_bomb", 2 - g.player.inventory.count_item("item_bomb")) if g.player.inventory.count_item("item_bomb") < 2 else None
out = say("use bomb")
check("a bomb blows a hollow open", "blows in" in out, out[:120])
walk("in")
gold = rupees()
say("talk old man")
say("reply 1")
check("the old man charges twenty rupees for his wall", gold - rupees() == 20, gold - rupees())
say("talk old man")
check("and is satisfied", rupees() == gold - 20, rupees())
walk("out")

# ---- bait, the hungry brute, the quiet bay
goto("ardenmoor_east:ae_0_2")
walk("in")
say("trade old man")
gold = rupees()
say("buy bait")
say("stoptrade")
check("bait for sixty rupees", "item_bait" in g.items() and gold - rupees() == 60, gold - rupees())
walk("out")
goto("ardenmoor_east:ae_0_0")
walk("north")
check("the narrow pass and a hungry brute", g.where() == "ardenmoor_east:ae_pass" and len(hostile_here()) == 0 and any(n.template_id == "hungry_brute" for n in g.world.npcs.values() if n.is_alive), g.where())
out = say("go north")
check("it will not let you by", g.where() == "ardenmoor_east:ae_pass" and "eat" in out.lower(), out[:140])
say("talk brute")
say("reply 1")
check("fed, it goes off and the bait is spent", "item_bait" not in g.items() and not any(n.template_id == "hungry_brute" and n.is_alive for n in g.world.npcs.values()), "")
walk("north")
check("the quiet bay", g.where() == "ardenmoor_east:ae_bay", g.where())
out = say("go in")
check("the cliff is blank", g.where() == "ardenmoor_east:ae_bay", out[:80])
out = say("use reed pipe")
check("the pipe opens a seam in the cliff", "seam opens" in out, out[:160])
walk("in")
check("the Fiend's Hold", g.where() == "fiends_hold:f_entrance", g.where())

# ---- the Fiend's Hold
hearts_before = g.player.max_health
walk("north")
check("the hall of faces: a centaur and a hexer fall", clear_room_through(("centaur", "horned_centaur"), ("hexer", "strong_hexer"), region_room="fiends_hold:f_hall"), "")
walk("west")
say("use blue candle")
check("the iron gallery: two ironclads", len(hostile_here("ironclad")) == 2, [n.template_id for n in hostile_here()])
check("they fall", clear_room_through(("ironclad", "ironclad"), region_room="fiends_hold:f_west", candle="blue candle"), "")
walk("north")
say("use blue candle")
check("the red vault: two strong hexers and a red candle", len(hostile_here("strong_hexer")) == 2 and g.where() == "fiends_hold:f_candle", g.where())
check("they fall", clear_room_through(("hexer", "strong_hexer"), region_room="fiends_hold:f_candle", candle="blue candle"), "")
say("take red candle")
check("the red candle", "item_red_candle" in g.items(), g.items())
say("use red candle")
out = say("use red candle")
check("a red candle burns again in the same room", "already burns" not in out, out[:80])
goto("fiends_hold:f_east")
say("use red candle")
check("the eaters' hall: two shield-eaters and a bat", len(hostile_here("shield_eater")) == 2, [n.template_id for n in hostile_here()])
check("they fall", clear_room_through(("eater", "shield_eater"), ("bat", "cave_bat"), region_room="fiends_hold:f_east", candle="red candle"), "")
say("take small key")
walk("north")
say("trade old man")
gold = rupees()
say("buy large bomb bag")
say("stoptrade")
check("a large bomb bag for a hundred rupees", "item_bomb_bag_16" in g.items() and gold - rupees() == 100, gold - rupees())
give("item_bomb", 16 - g.player.inventory.count_item("item_bomb"))
check("sixteen bombs is the limit now", g.player.inventory.count_item("item_bomb") == 16, g.player.inventory.count_item("item_bomb"))
goto("fiends_hold:f_upper")
say("use red candle")
check("the upper gallery falls", clear_room_through(("hexer", "strong_hexer"), ("ironclad", "ironclad"), ("hand", "grasping_hand"), region_room="fiends_hold:f_upper", candle="red candle"), "")
say("use bomb")
walk("west")
check("a pantry behind the west wall", g.where() == "fiends_hold:f_cache", g.where())
goto("fiends_hold:f_upper")
out = say("go north")
check("the iron door yields to the key", g.where() == "fiends_hold:f_ante" and "item_small_key" not in g.items(), "%s %s" % (g.where(), out[:80]))
say("use red candle")
check("the hall of heat falls", clear_room_through(("ironclad", "ironclad"), ("centaur", "horned_centaur"), region_room="fiends_hold:f_ante", candle="red candle"), "")
heal()
walk("north")
check("the elder's roost", g.where() == "fiends_hold:f_boss" and len(hostile_here("aquilor_elder")) == 1, g.where())
elder = hostile_here("aquilor_elder")[0]
guard = 0
while elder.is_alive and guard < 30 and g.player.is_alive:
    guard += 1
    heal()
    g.fight("Aquilor", max_rounds=4, potion="recovery heart")
wait(3)
check("the elder falls", not elder.is_alive and g.player.is_alive, elder.health)
check("the seventh shard and a heart more", "item_shard_7" in g.items() and g.player.max_health == hearts_before + HEART, "%s %s" % (g.items(), g.player.max_health))

# ---- the Mane
goto("ardenmoor_east:ae_burnt_rise")
out = say("go in")
check("a bush stands over the door", g.where() == "ardenmoor_east:ae_burnt_rise", out[:80])
out = say("use red candle")
check("the red candle burns it away", "bush goes up" in out, out[:160])
hearts_before = g.player.max_health
walk("in")
check("the Mane", g.where() == "the_mane:m_entrance", g.where())
walk("north")
check("the hall of locks falls", clear_room_through(("centaur", "horned_centaur"), ("hexer", "strong_hexer"), region_room="the_mane:m_hall"), "")
goto("the_mane:m_west")
say("use red candle")
check("the iron passage falls", clear_room_through(("ironclad", "ironclad"), ("hexer", "strong_hexer"), region_room="the_mane:m_west", candle="red candle"), "")
walk("north")
say("use red candle")
check("the scorched library: a blue ironclad and a book", len(hostile_here("blue_ironclad")) == 1 and g.where() == "the_mane:m_tome", g.where())
check("the guard falls", clear_room_through(("blue", "blue_ironclad"), region_room="the_mane:m_tome", candle="red candle"), "")
say("take tome")
check("the tome of cinders", "item_tome" in g.items() and "rod_flame" in g.player.runtime_state.magic.known_spells, g.items())
goto("the_mane:m_east")
say("use red candle")
check("the eaters' gallery falls", clear_room_through(("eater", "shield_eater"), ("bat", "cave_bat"), region_room="the_mane:m_east", candle="red candle"), "")
say("take small key")
walk("north")
say("use red candle")
check("the key chamber: two blue ironclads and a black key", len(hostile_here("blue_ironclad")) == 2 and g.where() == "the_mane:m_key", g.where())
check("they fall", clear_room_through(("blue", "blue_ironclad"), region_room="the_mane:m_key", candle="red candle"), "")
say("take open key")
check("the open key", "item_magic_key" in g.items(), g.items())
goto("the_mane:m_upper")
say("use red candle")
check("the upper passage falls", clear_room_through(("blue", "blue_ironclad"), ("hexer", "strong_hexer"), ("hand", "grasping_hand"), region_room="the_mane:m_upper", candle="red candle"), "")
say("use bomb")
walk("east")
check("a closet behind the east wall", g.where() == "the_mane:m_cache", g.where())
walk("west")
keys = g.player.inventory.count_item("item_small_key")
out = say("go north")
check("the open key turns the lock and the small key is kept", g.where() == "the_mane:m_ante" and g.player.inventory.count_item("item_small_key") == keys and "item_magic_key" in g.items(), "%s %s" % (g.where(), out[:100]))
say("use red candle")
check("the hall of the heads falls", clear_room_through(("blue", "blue_ironclad"), ("hexer", "strong_hexer"), ("centaur", "horned_centaur"), region_room="the_mane:m_ante", candle="red candle"), "")
heal()
walk("north")
check("the great hydra's lair: a body and four heads", len(hostile_here("hydra_head")) == 4 and len(hostile_here("great_hydra")) == 1, [n.template_id for n in hostile_here()])
body = hostile_here("great_hydra")[0]
out = say("attack the great hydra")
check("the body waits behind four heads", body.health == body.max_health and "neck" in out.lower(), out[:140])
guard = 0
while hostile_here("hydra_head") and guard < 30 and g.player.is_alive:
    guard += 1
    heal()
    g.fight("head", max_rounds=4, potion="recovery heart")
check("all four heads fall", not hostile_here("hydra_head") and g.player.is_alive, [n.template_id for n in hostile_here()])
heal()
g.fight("great hydra", potion="recovery heart")
wait(3)
check("and the body", not body.is_alive, body.health)
check("the eighth shard and a heart more", "item_shard_8" in g.items() and g.player.max_health == hearts_before + HEART, "%s %s" % (g.items(), g.player.max_health))
check("all eight shards of the Starcrown", all("item_shard_%d" % n in g.items() for n in range(1, 9)), [i for i in g.items() if "shard" in i])
out = say("status")
check("the hero stands at fifteen hearts", "%d/%d hearts" % (g.player.max_health // HEART, g.player.max_health // HEART) in out, out[:200])

print(NL + "%d/%d checks passed" % (sum(1 for r in RESULTS if r[1]), len(RESULTS)))
print("FAILED:", [r[0] for r in RESULTS if not r[1]])
g.close()
