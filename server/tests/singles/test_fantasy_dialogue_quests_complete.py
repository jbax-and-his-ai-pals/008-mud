"""Every quest a fantasy_frontier character offers in conversation can be taken
and finished the way a player would.

Most of the mid- and late-game quests (Frostpeak, Sunscorch, Aurelia, Tidewell)
are offered in dialogue, and none of them was played by any test. This finds
every `start_quest` in the set's dialogue, walks to the character who offers
it, follows the conversation to the offer (after first finishing any quest the
offer waits on), does the objective -- walks to the room a scouting task names,
or defeats the creature a hunt names -- and hands it in with the command the
journal gives. The runner is raised to level 15 with ample health: this checks
that each quest can be completed, not how hard it is.

Found on the way: accepting a quest in conversation announced its raw id
("[Quest Accepted] quest_frostpeak_deep_sounding"), not its title.
"""

import collections
import json
import re
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
DATA = FANTASY_FRONTIER / "data"


def _dialogues() -> dict:
    graphs = {}
    for path in sorted((DATA / "dialogue").glob("*.json")):
        graph = json.loads(path.read_text(encoding="utf-8"))
        graphs[graph["id"]] = graph
    return graphs


def _offer(graph: dict, quest_id: str):
    """(aliases to reply, quests the route waits on) from the root to the
    choice that starts `quest_id`, breadth first."""
    queue = collections.deque([(graph["root"], [], set())])
    seen = {graph["root"]}
    while queue:
        node_id, aliases, needs = queue.popleft()
        for choice in graph["nodes"][node_id].get("choices", []):
            alias = (choice.get("aliases") or [choice.get("text")])[0]
            waits = needs | set(re.findall(r'"kind": "quest_completed", "quest_id": "([a-z0-9_]+)"', json.dumps(choice.get("condition") or {})))
            if (choice.get("effects") or {}).get("start_quest") == quest_id:
                return aliases + [alias], waits
            target = choice.get("next_node")
            if target and target not in seen:
                seen.add(target)
                queue.append((target, aliases + [alias], waits))
    return None, set()


class TestDialogueQuestsComplete(unittest.TestCase):
    def setUp(self):
        self.quests = json.loads((DATA / "quests" / "quests.json").read_text(encoding="utf-8"))
        self.graphs = _dialogues()
        self.offers = {}
        for graph_id, graph in self.graphs.items():
            for quest_id in sorted(set(re.findall(r'"start_quest": "([a-z0-9_]+)"', json.dumps(graph)))):
                aliases, waits = _offer(graph, quest_id)
                self.offers[quest_id] = (graph_id, aliases, waits)

    def test_the_set_offers_quests_in_conversation(self):
        self.assertGreaterEqual(len(self.offers), 7, sorted(self.offers))
        for quest_id, (_graph, aliases, _waits) in self.offers.items():
            self.assertIsNotNone(aliases, f"no conversation route reaches the offer of {quest_id}")

    def test_every_offered_quest_can_be_finished(self):
        for quest_id in sorted(self.offers):
            with self.subTest(quest=quest_id):
                runner = _Runner(self)
                for step in self._chain(quest_id):
                    runner.take(step, *self.offers[step][:2])
                    runner.finish(step, self.quests[step])

    def _chain(self, quest_id: str) -> list:
        order, pending = [], [quest_id]
        while pending:
            current = pending.pop()
            if current in order:
                continue
            order.insert(0, current)
            pending.extend(sorted(self.offers.get(current, (None, None, set()))[2]))
        return order


class _Runner:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        test.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="quest_runner")
        self.run("char create Questrunner")
        self.player = self.server.get_player_for_session(self.session.session_id)
        for _ in range(14):
            self.player.level_up()
        self.player.max_health = self.player.health = 100_000
        # Bare hands against an armoured late-game guardian deal nothing.
        self.player.stats["strength"] = 500

    def run(self, command: str) -> str:
        lines = []
        for event in self.server.execute_command(self.session.session_id, command) or []:
            if isinstance(event, dict) and event.get("type") == "text":
                payload = event.get("payload")
                lines.append(str(payload.get("text", "") if isinstance(payload, dict) else payload))
        return "\n".join(lines)

    def walk_to(self, region: str, room: str) -> None:
        path = self.server.world.find_path(self.player.current_region_id, self.player.current_room_id, region, room)
        self.test.assertIsNotNone(path, f"no walking route to {region}:{room}")
        for direction in path:
            self.run(direction)
        self.test.assertEqual((region, room), (self.player.current_region_id, self.player.current_room_id))

    def npc(self, predicate):
        found = next((npc for npc in self.server.world.npcs.values() if npc.is_alive and predicate(npc)), None)
        self.test.assertIsNotNone(found)
        return found

    def take(self, quest_id: str, graph_id: str, aliases: list) -> None:
        giver = self.npc(lambda npc: npc.properties.get("dialogue") == graph_id)
        self.walk_to(giver.current_region_id, giver.current_room_id)
        self.run(f"talk {giver.name}")
        reply = ""
        for alias in aliases:
            reply = self.run(f"reply {alias}")
        self.test.assertTrue(any(key.startswith(quest_id + "_") for key in self.player.runtime_state.quests.active), f"{giver.name} did not give {quest_id}: {reply[-200:]}")
        self.test.assertNotIn(quest_id, reply, "the acceptance names the quest by its title, not its id")

    def finish(self, quest_id: str, quest: dict) -> None:
        stages = quest.get("stages", [])
        for index, stage in enumerate(stages):
            spawn = stage.get("spawn_on_entry")
            if spawn:
                # The stage puts its quarry in a room when the player arrives there.
                self.walk_to(spawn["region_id"], spawn["room_id"])
            self.meet(quest_id, stage.get("objective", {}))
            journal = self.run("journal")
            hand_in = re.search(r"Ready to turn in! \((?:\[\[/\]\])?(talk [^\[\)]+)", journal)
            self.test.assertIsNotNone(hand_in, f"{quest_id} stage {index} is not ready to hand in: {journal[:900]}")
            receiver = self.npc(lambda npc: npc.template_id == stage["turn_in_id"])
            self.walk_to(receiver.current_region_id, receiver.current_room_id)
            said = self.run(hand_in.group(1).strip())
            if index == len(stages) - 1:
                self.test.assertIn("Quest Complete", said)

    def meet(self, quest_id: str, objective: dict) -> None:
        kind = objective.get("type")
        if kind == "scout":
            self.walk_to(objective["target_region"], objective["target_room_id"])
        elif kind == "kill":
            target = self.npc(lambda npc: npc.template_id == objective["target_template_id"])
            for _ in range(20):
                if not target.is_alive:
                    break
                # A wounded creature may flee; follow it.
                self.walk_to(target.current_region_id, target.current_room_id)
                self.run(f"attack {target.name}")
                for _tick in range(25):
                    self.server.tick(self.session.session_id)
            self.test.assertFalse(target.is_alive, f"{target.name} did not fall")
        elif kind == "fetch":
            if self.player.inventory.count_item(objective["item_id"]) >= int(objective.get("required_quantity", 1)):
                return
            region, room, item = self.placed(lambda item: item.obj_id == objective["item_id"])
            self.walk_to(region, room)
            self.test.assertIn("pick up", self.run(f"get {item.name}").lower())
        elif kind == "gather_types":
            for resource in objective["required_item_ids"]:
                region, room, node = self.placed(lambda item: item.get_property("resource_item_id") == resource)
                self.carry_tool(node.get_property("tool_required"))
                self.walk_to(region, room)
                self.test.assertIn("You gather", self.run(f"gather {node.name}"))
        else:
            self.test.fail(f"{quest_id}: no scripted route for a {kind} objective")

    def placed(self, predicate):
        """(region, room, item) for the first room item the predicate accepts."""
        for region_id, region in sorted(self.server.world.regions.items()):
            for room_id in sorted(region.rooms):
                for item in self.server.world.get_items_in_room(region_id, room_id):
                    if predicate(item):
                        return region_id, room_id, item
        self.test.fail("nothing placed in the world matches")

    def carry_tool(self, tool_type) -> None:
        """A tool a player could buy or carry: any item template of that tool type."""
        if not tool_type:
            return
        world = self.server.world
        template_id = next(
            template_id for template_id, template in sorted(world.item_templates.items())
            if isinstance(template, dict) and template.get("properties", {}).get("tool_type") == tool_type
        )
        if not self.player.inventory.count_item(template_id):
            from engine.items.item_factory import ItemFactory
            self.player.inventory.add_item(ItemFactory.create_item_from_template(template_id, world))


if __name__ == "__main__":
    unittest.main()
