"""P6 repeatable-board tasks: explicit policy, hidden delay, saved state."""

from engine.commands.quest import accept_quest_handler, look_board_handler
from engine.core.clock import SimulatedClock
from engine.player.core import Player
from tests.fixtures import GameTestBase


class TestRepeatableBoardQuests(GameTestBase):
    TEMPLATE_ID = "quest_wildflower_commission"
    NOTICE = "Elder Thorne has taken down today's notice; the board is picked over for now."

    def setUp(self):
        super().setUp()
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.world.clock = SimulatedClock(start=10_000.0)
        self.qm = self.world.quest_manager
        self.qm.config["authored_board_templates"] = [{
            "template_id": self.TEMPLATE_ID,
            "giver_template_id": "village_elder",
            "repeatable": {"delay_seconds": 900, "unavailable_text": self.NOTICE},
        }]
        self.world.quest_board = []

    def _accept_posted_task(self):
        self.qm.ensure_initial_quests(self.player)
        posted = next(q for q in self.world.quest_board if q.get("template_id") == self.TEMPLATE_ID)
        result = accept_quest_handler([str(self.world.quest_board.index(posted) + 1)], {
            "world": self.world,
            "player": self.player,
            "game": self.game,
        })
        self.assertIn("Quest Accepted", result)
        instance_id = next(
            quest_id for quest_id, quest in self.player.runtime_state.quests.active.items()
            if quest.get("template_id") == self.TEMPLATE_ID
        )
        return instance_id

    def test_accepting_a_notice_never_posts_a_duplicate_while_active(self):
        self._accept_posted_task()

        self.assertFalse(any(
            quest.get("template_id") == self.TEMPLATE_ID
            for quest in self.world.quest_board
        ))
        board = look_board_handler([], {"world": self.world, "player": self.player})
        self.assertIn(self.NOTICE, board)
        self.assertNotIn("900", board)
        self.assertNotIn("cooldown", board.lower())

    def test_completed_task_reposts_after_its_hidden_authored_delay(self):
        instance_id = self._accept_posted_task()
        self.qm.complete_quest(self.player, instance_id)

        self.assertEqual(
            10_900.0,
            self.player.runtime_state.quests.repeatable_available_at[self.TEMPLATE_ID],
        )
        self.assertFalse(any(
            quest.get("template_id") == self.TEMPLATE_ID
            for quest in self.world.quest_board
        ))

        before = look_board_handler([], {"world": self.world, "player": self.player})
        self.assertIn(self.NOTICE, before)
        self.assertNotIn("900", before)

        self.world.clock.advance(900)
        after = look_board_handler([], {"world": self.world, "player": self.player})
        reposted = [q for q in self.world.quest_board if q.get("template_id") == self.TEMPLATE_ID]
        self.assertEqual(1, len(reposted))
        self.assertIn("A Posy for Riverside", after)
        self.assertNotIn(self.NOTICE, after)

    def test_nonrepeatable_board_task_is_not_reposted_after_completion(self):
        self.qm.config["authored_board_templates"][0].pop("repeatable")
        self.player.runtime_state.quests.completed["old_posy"] = {"template_id": self.TEMPLATE_ID}

        self.qm.ensure_initial_quests(self.player)

        self.assertFalse(any(
            quest.get("template_id") == self.TEMPLATE_ID
            for quest in self.world.quest_board
        ))

    def test_repeatable_availability_is_preserved_in_a_player_save(self):
        self.player.runtime_state.quests.repeatable_available_at[self.TEMPLATE_ID] = 12_345.5

        restored = Player.from_dict(self.player.to_dict(self.world), self.world)

        self.assertIsNotNone(restored)
        self.assertEqual(
            12_345.5,
            restored.runtime_state.quests.repeatable_available_at[self.TEMPLATE_ID],
        )
