# tests/singles/test_save_write_is_durable.py
"""The save write cannot destroy the only copy of a character.

Three facts composed into one reachable failure, each reasonable alone:

1. `save_manager.save` wrote with `open(path, 'w')` — truncating the file before
   writing over it, with no backup anywhere in the repo (`os.replace`, `mkstemp`,
   `fsync`, `.bak`: zero hits).
2. A failed `load` catches everything and calls `initialize_new_world()`, so the
   player becomes a new character.
3. `load_handler` reassigns `game.current_save_file` only on success, and
   `save_handler` defaults to it.

So: load a corrupt save, type `save`, and the unreadable file is overwritten by a
fresh adventurer. The recovery path ran backwards.

These tests are about the three defences — atomic write, backup, and refusing to
clobber something we could not read — not about the save format itself.
"""
import json
import os
import stat
import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.save_manager import SaveManager


def _cleanup(*paths):
    for path in paths:
        if not os.path.exists(path):
            continue
        for _ in range(3):
            try:
                os.chmod(path, stat.S_IWRITE)
                os.remove(path)
                break
            except PermissionError:
                time.sleep(0.1)


class SaveWriteTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = SaveManager(self.world)
        self.save_file = "durable_save_test.json"
        self.save_path = os.path.join(self.world.save_directory, self.save_file)
        self.backup_path = self.save_path + ".bak"
        os.makedirs(self.world.save_directory, exist_ok=True)

    def tearDown(self):
        _cleanup(self.save_path, self.backup_path)
        super().tearDown()

    def _write_corrupt(self) -> str:
        with open(self.save_path, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")
        return self.save_path

    def _read(self) -> str:
        with open(self.save_path, "r", encoding="utf-8") as handle:
            return handle.read()


class TestAFailedWriteLeavesTheOldSave(SaveWriteTestBase):
    def test_a_crash_mid_write_does_not_touch_the_existing_file(self):
        """The whole point of writing to a temp file and replacing.

        Before this, `open(path, 'w')` truncated the destination immediately, so
        a crash during `json.dump` destroyed the save it was trying to write.
        """
        self.assertTrue(self.manager.save(self.save_file))
        original = self._read()

        # Fail partway through the dump, as a crash or a full disk would.
        with patch("engine.world.save_manager.json.dump", side_effect=RuntimeError("disk full")):
            self.assertFalse(self.manager.save(self.save_file))

        self.assertEqual(original, self._read(), "the previous save must survive a failed write")

    def test_a_failed_write_leaves_no_temporary_file_behind(self):
        """A stray .tmp in the save directory is a file the next reader may trust."""
        with patch("engine.world.save_manager.json.dump", side_effect=RuntimeError("disk full")):
            self.manager.save(self.save_file)
        leftovers = [n for n in os.listdir(self.world.save_directory) if n.endswith(".tmp")]
        self.assertEqual([], leftovers)

    def test_a_successful_save_is_readable_json(self):
        self.assertTrue(self.manager.save(self.save_file))
        payload = json.loads(self._read())
        self.assertIn("save_format_version", payload)


class TestTheBackupIsTakenOnce(SaveWriteTestBase):
    def test_the_first_overwrite_keeps_a_backup(self):
        self.assertTrue(self.manager.save(self.save_file))
        first = self._read()
        self.assertTrue(self.manager.save(self.save_file))
        self.assertTrue(os.path.exists(self.backup_path))
        with open(self.backup_path, "r", encoding="utf-8") as handle:
            self.assertEqual(first, handle.read())

    def test_the_backup_is_not_rewritten_on_every_save(self):
        """One recovery point per session, not one file-copy per save."""
        self.manager.save(self.save_file)
        self.manager.save(self.save_file)
        with open(self.backup_path, "r", encoding="utf-8") as handle:
            first_backup = handle.read()
        self.manager.save(self.save_file)
        with open(self.backup_path, "r", encoding="utf-8") as handle:
            self.assertEqual(first_backup, handle.read())


class TestRefusingToClobberAnUnreadableSave(SaveWriteTestBase):
    def test_saving_over_a_corrupt_save_is_refused(self):
        self._write_corrupt()
        self.assertFalse(
            self.manager.save(self.save_file),
            "a save we never loaded and cannot read must not be overwritten",
        )
        self.assertEqual("{ this is not json", self._read())

    def test_the_refusal_survives_a_failed_load_of_the_same_file(self):
        """The exact composed failure, end to end.

        `load` swallows the error and gives the player a new world. The save that
        follows must not take the old file with it.
        """
        self._write_corrupt()
        loaded, _time, _weather = self.manager.load(self.save_file)
        self.assertFalse(loaded, "a corrupt save must not report success")
        self.assertFalse(self.manager.save(self.save_file))
        self.assertEqual("{ this is not json", self._read())

    def test_a_save_we_did_load_may_be_overwritten(self):
        """The guard is about files we have never seen, not about caution."""
        self.assertTrue(self.manager.save(self.save_file))

        reloader = SaveManager(self.world)
        loaded, _time, _weather = reloader.load(self.save_file)
        self.assertTrue(loaded)
        self.assertTrue(reloader.save(self.save_file), "a loaded save is ours to overwrite")

    def test_writing_a_new_name_is_never_refused(self):
        self.assertFalse(os.path.exists(self.save_path))
        self.assertTrue(self.manager.save(self.save_file))

    def test_the_refusal_does_not_trigger_on_a_missing_file(self):
        """Absence is not unreadability: nothing to destroy, nothing to refuse."""
        absent = os.path.join(self.world.save_directory, "never_written.json")
        self.assertFalse(os.path.exists(absent))
        self.assertTrue(self.manager.save("never_written.json"))
        _cleanup(absent, absent + ".bak")


if __name__ == "__main__":
    unittest.main()
