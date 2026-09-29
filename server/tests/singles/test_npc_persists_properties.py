# tests/singles/test_npc_persists_properties.py
"""An NPC that is saved comes back as itself.

`NPC.to_dict` kept a creature's health and stats but not its `properties`, its
behaviour or its home, so a saved NPC reloaded as an ordinary creature of its
template: a placement's authored `respawn_cooldown`, a stationary boss that had been
told to stand still, and the room a friend calls home were all forgotten (and a
recruited companion would have come back ownerless). The template stays the source of
truth for everything the placement did not change; only the difference is saved.
"""

from engine.npcs.npc_factory import NPCFactory
from tests.fixtures import GameTestBase


class TestNpcPersistsProperties(GameTestBase):
    def _made(self, **overrides):
        region = self.player.current_region_id
        room = self.player.current_room_id
        return NPCFactory.create_npc_from_template(
            "giant_rat", self.world, "rat_probe",
            current_region_id=region, current_room_id=room,
            home_region_id=region, home_room_id=room, **overrides,
        )

    def _reload(self, state):
        overrides = dict(state)
        template_id = overrides.pop("template_id")
        return NPCFactory.create_npc_from_template(template_id, self.world, "rat_probe", **overrides)

    def test_what_a_placement_changed_is_saved_and_the_template_is_not(self):
        npc = self._made(properties_override={"respawn_cooldown": 42, "is_escort_target": True})
        state = npc.to_dict()
        self.assertEqual({"respawn_cooldown": 42, "is_escort_target": True}, state["properties_override"])

    def test_a_reloaded_npc_has_the_properties_it_was_saved_with(self):
        npc = self._made(properties_override={"respawn_cooldown": 42, "is_escort_target": True})
        reloaded = self._reload(npc.to_dict())
        self.assertEqual(npc.properties, reloaded.properties)

    def test_a_reloaded_npc_keeps_its_behaviour_and_its_home(self):
        npc = self._made(behavior_type="stationary")
        npc.home_room_id = "somewhere_it_was_sent_home_to"
        reloaded = self._reload(npc.to_dict())
        self.assertEqual("stationary", reloaded.behavior_type)
        self.assertEqual(("somewhere_it_was_sent_home_to", npc.home_region_id), (reloaded.home_room_id, reloaded.home_region_id))

    def test_an_npc_no_placement_touched_saves_no_property_overrides(self):
        state = self._made().to_dict()
        self.assertEqual({}, state["properties_override"])
