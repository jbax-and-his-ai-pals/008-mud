# tests/singles/test_save_format.py
"""A save says what it is, and a reader that cannot read it says so.

`save_format_version` was written and never read: every load was a per-key
`.get(default)` walk, so a file from a future build produced a half-restored
character rather than a refusal, and a file from an old build had no way to say
what it needed. These tests pin the rules that make the stamp mean something, and
the two persistence defects it was hiding -- an aspect a save could dereference
while it was None, and a summon list that could never have been restored.
"""
import json
import os
import stat
import time
import unittest

from tests.fixtures import GameTestBase
from engine.player.aspects import MagicState, PlayerGameAspects
from engine.world.save_format import (
    MIGRATIONS,
    SAVE_FORMAT_VERSION,
    STALE_SUMMONS_KEY,
    UNVERSIONED,
    UnsupportedSaveVersion,
    declared_version,
    migrate,
    take_stale_summons_flag,
)


class TestTheStampItself(unittest.TestCase):
    def test_a_save_with_no_stamp_is_the_oldest_format(self):
        self.assertEqual(UNVERSIONED, declared_version({"player": {}}))

    def test_a_stamp_that_is_not_a_number_is_not_evidence(self):
        self.assertEqual(UNVERSIONED, declared_version({"save_format_version": "three"}))
        self.assertEqual(UNVERSIONED, declared_version({"save_format_version": True}))
        self.assertEqual(UNVERSIONED, declared_version({"save_format_version": None}))

    def test_a_whole_float_stamp_is_read(self):
        """Content is not the only place a JSON writer with one number type bites."""
        self.assertEqual(3, declared_version({"save_format_version": 3.0}))

    def test_version_gaps_are_all_recorded(self):
        steps = sorted(MIGRATIONS)
        self.assertEqual(
            [(version, version + 1) for version in range(1, SAVE_FORMAT_VERSION)],
            steps,
            "every step up to the current version needs an entry, even a no-op one, "
            "so the next person can see why the bump was safe",
        )


class TestMigration(unittest.TestCase):
    def test_a_future_save_is_refused_rather_than_half_read(self):
        with self.assertRaises(UnsupportedSaveVersion) as raised:
            migrate({"save_format_version": SAVE_FORMAT_VERSION + 1})
        self.assertEqual(SAVE_FORMAT_VERSION + 1, raised.exception.version)
        self.assertIn("newer version of the game", str(raised.exception))

    def test_a_current_save_is_passed_through_untouched(self):
        save = {"save_format_version": SAVE_FORMAT_VERSION, "player": {"name": "A"}}
        migrated, applied = migrate(save)
        self.assertEqual([], applied)
        self.assertEqual({"name": "A"}, migrated["player"])

    def test_an_unstamped_save_passes_every_migration(self):
        _migrated, applied = migrate({"player": {"name": "A"}})
        # There is no step from 0 to 1: an unstamped save is not a format, it is
        # a file written before there were formats, and its state *is* version 1.
        # The gap is reported rather than invented.
        self.assertEqual("no migration recorded from 0 to 1", applied[0])
        self.assertEqual(
            [step.__name__ for _pair, step in sorted(MIGRATIONS.items())],
            applied[1:],
        )

    def test_a_version_three_save_is_told_its_summon_list_is_stale(self):
        migrated, _applied = migrate({"save_format_version": 3, "player": {"name": "A"}})
        self.assertTrue(migrated["player"][STALE_SUMMONS_KEY])

    def test_the_stale_flag_is_consumed_and_never_reaches_a_re_save(self):
        player = {"name": "A", STALE_SUMMONS_KEY: True}
        self.assertTrue(take_stale_summons_flag(player))
        self.assertNotIn(STALE_SUMMONS_KEY, player)
        self.assertFalse(take_stale_summons_flag(player))

    def test_a_non_object_save_is_refused(self):
        with self.assertRaises(UnsupportedSaveVersion):
            migrate([1, 2, 3])


class TestPersistenceSurvivesASaveWithNoAspects(GameTestBase):
    """A save can be written by a build that had an aspect the reader does not."""

    TEST_SAVE_FILE = "format_no_aspects.json"

    def tearDown(self):
        self._remove_save()
        super().tearDown()

    def _remove_save(self):
        path = os.path.join(self.world.save_directory, self.TEST_SAVE_FILE)
        for _ in range(3):
            try:
                if os.path.exists(path):
                    os.chmod(path, stat.S_IWRITE)
                    os.remove(path)
                return
            except PermissionError:
                time.sleep(0.1)

    def _write_save(self, payload: dict) -> None:
        path = os.path.join(self.world.save_directory, self.TEST_SAVE_FILE)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        self.addCleanup(self._remove_save)

    def _save_of_current_player(self) -> dict:
        self.assertTrue(self.world.save_game(self.TEST_SAVE_FILE), "save failed")
        with open(os.path.join(self.world.save_directory, self.TEST_SAVE_FILE), encoding="utf-8") as handle:
            return json.load(handle)

    def test_a_game_without_abilities_loads_and_leaves_magic_none(self):
        """`normalize` sets `magic` to None, and the reader used to dereference it."""
        save = self._save_of_current_player()
        self._remove_save()
        save["player"]["gameplay"]["magic"] = {
            "mana": 5, "max_mana": 5, "known_spells": ["probe"], "cooldowns": {},
        }
        self._write_save(save)
        # The state a content set with no abilities produces.
        self.world.player_aspects = PlayerGameAspects(abilities=False)
        loaded, _time, _weather = self.world.load_save_game(self.TEST_SAVE_FILE)
        self.assertTrue(loaded, "a save from a game with abilities must still load")
        self.assertIsNone(self.world.player.runtime_state.magic)

    def test_a_save_with_no_magic_object_at_all_still_loads(self):
        save = self._save_of_current_player()
        self._remove_save()
        del save["player"]["gameplay"]["magic"]
        self._write_save(save)
        loaded, _time, _weather = self.world.load_save_game(self.TEST_SAVE_FILE)
        self.assertTrue(loaded)
        self.assertIsNotNone(self.world.player)

    def test_the_aspects_the_world_wants_are_applied_before_the_save_is_read(self):
        """The reader normalizes first, so a save cannot leave an aspect half-applied."""
        save = self._save_of_current_player()
        self._remove_save()
        save["player"]["gameplay"]["progression"] = {
            "player_class": "Salvager", "level": 4, "experience": 10,
            "experience_to_level": 100, "skills": {},
        }
        self._write_save(save)
        self.world.player_aspects = PlayerGameAspects(progression=False)
        loaded, _time, _weather = self.world.load_save_game(self.TEST_SAVE_FILE)
        self.assertTrue(loaded)
        # `normalize` runs once up front and once at the end, so the world's
        # setting is what a caller sees either way.
        self.assertIsNone(self.world.player.runtime_state.progression)


class TestSummonsAcrossASave(GameTestBase):
    """A summon cannot survive a save, and the ledger must not pretend it did."""

    def setUp(self):
        super().setUp()
        self.minion = self.world.spawn_monster("giant_rat", self.player.current_room_id) \
            if hasattr(self.world, "spawn_monster") else None

    def test_a_current_save_records_the_summon_ledger(self):
        from engine.npcs.npc_factory import NPCFactory

        summon = NPCFactory.create_npc_from_template("giant_rat", self.world, "sum_ab12", owner_id=self.player.obj_id)
        self.assertIsNotNone(summon)
        if summon is None:
            return
        self.world.add_npc(summon)
        self.player.runtime_state.magic.summons = {"summon_rat": [summon.obj_id]}
        self.assertIn("summon_rat", self.world.player.to_dict(self.world)["gameplay"]["magic"]["summons"])

    def test_a_ledger_with_nothing_in_it_is_not_written(self):
        self.player.runtime_state.magic.summons = {}
        self.assertNotIn("summons", self.world.player.to_dict(self.world)["gameplay"]["magic"])

    def test_an_entry_naming_an_instance_that_does_not_exist_is_dropped(self):
        """The only load-time fact that matters: is the instance actually there?"""
        payload = self.world.player.to_dict(self.world)
        payload["gameplay"]["magic"]["summons"] = {"summon_rat": ["sum_gone"]}
        from engine.player.core import Player

        loaded = Player.from_dict(payload, self.world)
        self.assertIsNotNone(loaded)
        loaded.settle_pending_summons()
        self.assertEqual({}, loaded.runtime_state.magic.summons)

    def test_an_entry_naming_a_live_instance_is_adopted(self):
        from engine.npcs.npc_factory import NPCFactory
        from engine.player.core import Player

        summon = NPCFactory.create_npc_from_template("giant_rat", self.world, "sum_live", owner_id=self.player.obj_id)
        if summon is None:
            self.skipTest("giant_rat is not a template in this content set")
        self.world.add_npc(summon)
        payload = self.world.player.to_dict(self.world)
        payload["gameplay"]["magic"]["summons"] = {"summon_rat": ["sum_live", "sum_gone"]}
        loaded = Player.from_dict(payload, self.world)
        loaded.settle_pending_summons()
        self.assertEqual({"summon_rat": ["sum_live"]}, loaded.runtime_state.magic.summons)

    def test_a_version_three_save_starts_with_no_summons(self):
        from engine.player.core import Player

        payload = self.world.player.to_dict(self.world)
        payload["gameplay"]["magic"]["summons"] = {"summon_rat": ["sum_whatever"]}
        payload[STALE_SUMMONS_KEY] = True
        loaded = Player.from_dict(payload, self.world)
        self.assertEqual({}, loaded.runtime_state.magic.summons)
        loaded.settle_pending_summons()
        self.assertEqual({}, loaded.runtime_state.magic.summons)

    def test_a_settled_player_does_not_keep_the_pending_ledger(self):
        from engine.player.core import Player

        payload = self.world.player.to_dict(self.world)
        payload["gameplay"]["magic"]["summons"] = {"summon_rat": ["sum_gone"]}
        loaded = Player.from_dict(payload, self.world)
        loaded.settle_pending_summons()
        self.assertIsNone(getattr(loaded, "_pending_summons", None))
        # And it is not written back into the next save.
        self.assertNotIn(STALE_SUMMONS_KEY, json.dumps(loaded.to_dict(self.world)))


if __name__ == "__main__":
    unittest.main()
