# tests/singles/test_instance_quest_authored_fields.py
"""An instance template's authored fields reach the instance it builds.

The instance-manager tests hand-build a quest using the keys
`instantiate_quest_region` reads. The real path is different: the generator
stores its data in `meta_instance_data`, and accepting a quest flattens that
onto the quest. The generator used to spell two keys differently
(`layout_config`, `giver_template_id`), so through the real path the authored
giver never appeared and `target_count` fell back to the default -- and the
authored `region_description` was replaced by "A place.". This drives the
real path end to end.
"""
from tests.fixtures import GameTestBase


TEMPLATE_ID = "instance_probe"


class TestInstanceQuestAuthoredFields(GameTestBase):
    def setUp(self):
        super().setUp()
        self.quest_manager = self.world.quest_manager
        self.region_id = self.world.content_set.start_region_id
        self.quest_manager.quest_templates = {TEMPLATE_ID: {
            "type": "instance",
            "level": 1,
            "giver_npc_template_id": "worried_homeowner",
            "possible_entry_regions": [self.region_id],
            "objective": {
                "type": "clear_region",
                "possible_target_template_ids": ["giant_rat"],
                "completion_npc_template_id": "relieved_homeowner",
            },
            "layout_generation_config": {
                "min_rooms": 4, "max_rooms": 4,
                "region_name": "Probe House",
                "region_description": "A probe house that smells of damp plaster.",
                "possible_room_names": ["Probe Room"],
                "target_count": [1, 1],
            },
        }}

    def _accept(self):
        quest = self.quest_manager.generator.generate_instance_quest(1)
        self.assertIsNotNone(quest, "the instance template produced a quest")
        # The same flattening `commands/quest.py` performs on accept.
        quest.update(quest["meta_instance_data"])
        success, message, giver_id = self.world.instantiate_quest_region(quest, requesting_player=self.player)
        self.assertTrue(success, message)
        return quest, giver_id

    def test_the_authored_giver_is_spawned(self):
        _quest, giver_id = self._accept()
        self.assertIsNotNone(giver_id)
        self.assertEqual("worried_homeowner", self.world.get_npc(giver_id).template_id)

    def test_the_authored_target_count_is_used(self):
        quest, _giver_id = self._accept()
        region_id = quest["instance_region_id"]
        rats = [npc for npc in self.world.npcs.values()
                if npc.current_region_id == region_id and npc.template_id == "giant_rat"]
        self.assertEqual(1, len(rats), "the default range is [2, 4], so 1 can only come from the template")

    def test_the_authored_region_description_is_used(self):
        quest, _giver_id = self._accept()
        region = self.world.get_region(quest["instance_region_id"])
        self.assertEqual("A probe house that smells of damp plaster.", region.description)
