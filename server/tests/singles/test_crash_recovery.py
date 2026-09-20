# tests/singles/test_crash_recovery.py
"""A process that died can be restarted onto exactly the state it left.

`test_save_write_is_durable.py` tests the defences at the moment of writing: the
temp file, the backup, and the refusal to clobber. This tests the other half --
what an operator or player actually does next, with a fresh process and a save
directory that a crash left in some half-state.

The ordinary restart is: process dies at some point, leaving whatever the last
successful `save` wrote; a new process starts and loads it. The interesting
restarts are the ones where the crash landed somewhere specific:

* mid-write, so a temp file is orphaned beside the last good save;
* mid-write on a full disk, so the save itself is corrupt and the backup is the
  only readable copy;
* before the first save ever completed, so there is nothing to recover.

Each is checked against a *new* SaveManager, because "did the last process leave
the disk in a recoverable state" is a question only a fresh reader can answer.
"""
import json
import os
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.save_format import SAVE_FORMAT_VERSION
from engine.world.save_manager import SaveManager


class CrashRecoveryTestBase(GameTestBase):
    """A save directory, plus a way to be a brand new process looking at it."""

    def setUp(self):
        super().setUp()
        self.save_file = "crash_recovery_test.json"
        self.save_path = os.path.join(self.world.save_directory, self.save_file)
        self.backup_path = self.save_path + ".bak"
        self.tmp_path = os.path.join(self.world.save_directory, ".save-orphan.tmp")
        os.makedirs(self.world.save_directory, exist_ok=True)

    def tearDown(self):
        for path in (self.save_path, self.backup_path, self.tmp_path):
            if os.path.exists(path):
                os.remove(path)
        super().tearDown()

    # -- acting as the dead process, then as the new one --------------------

    def _first_process_saves(self) -> str:
        """Save once and return the bytes, as the process that died had left them."""
        self.assertTrue(self.world.save_game(self.save_file))
        return self._read_save()

    def _restart(self) -> SaveManager:
        """A save manager with no memory of anything the last process did.

        `_loaded_save_path` and `_backed_up` are per-session state, which is what
        makes a fresh instance the honest stand-in for a new process.
        """
        return SaveManager(self.world)

    def _read_save(self) -> str:
        with open(self.save_path, "r", encoding="utf-8") as handle:
            return handle.read()

    def _write_corrupt_save(self) -> None:
        """Truncated mid-value, which is what a full disk or a kill leaves."""
        with open(self.save_path, "w", encoding="utf-8") as handle:
            handle.write('{"player": {"name": "Advent')

    def _leave_orphan_temp_file(self) -> None:
        """What a crash before `os.replace` leaves: a temp file with real content."""
        with open(self.tmp_path, "w", encoding="utf-8") as handle:
            handle.write('{"save_format_version": 4, "player": null}')


class TestRestartAfterASuccessfulSave(CrashRecoveryTestBase):
    def test_a_new_process_loads_what_the_last_one_saved(self):
        self._first_process_saves()
        loaded, _time, _weather = self._restart().load(self.save_file)
        self.assertTrue(loaded, "a save the last process completed must load in the next one")

    def test_the_restarted_save_names_its_own_format(self):
        """A save that cannot say what it is cannot be migrated later."""
        self._first_process_saves()
        payload = json.loads(self._read_save())
        self.assertEqual(SAVE_FORMAT_VERSION, payload.get("save_format_version"))

    def test_the_restarted_process_can_save_again(self):
        """Recovery is not read-only: the character keeps playing afterwards."""
        self._first_process_saves()
        manager = self._restart()
        manager.load(self.save_file)
        self.assertTrue(manager.save(self.save_file))
        loaded, _time, _weather = self._restart().load(self.save_file)
        self.assertTrue(loaded)


class TestRestartAfterACrashMidWrite(CrashRecoveryTestBase):
    def test_an_orphaned_temp_file_does_not_become_the_save(self):
        """The crash left a temp file. The next process must load the save, not it."""
        good = self._first_process_saves()
        self._leave_orphan_temp_file()

        loaded, _time, _weather = self._restart().load(self.save_file)
        self.assertTrue(loaded)
        self.assertEqual(good, self._read_save(), "the temp file must not be consulted")

    def test_an_orphaned_temp_file_does_not_block_the_next_save(self):
        self._first_process_saves()
        self._leave_orphan_temp_file()
        manager = self._restart()
        manager.load(self.save_file)
        self.assertTrue(manager.save(self.save_file))

    def test_the_last_good_save_survives_a_crash_during_the_next_write(self):
        """Crash while overwriting: the file on disk is still the last complete one."""
        good = self._first_process_saves()
        manager = self._restart()
        manager.load(self.save_file)
        with patch("engine.world.save_manager.json.dump", side_effect=RuntimeError("power loss")):
            self.assertFalse(manager.save(self.save_file))
        self.assertEqual(good, self._read_save())


class TestRestartWhenTheSaveIsUnreadable(CrashRecoveryTestBase):
    """The failure the backup exists for, checked from a new process."""

    def test_a_truncated_save_does_not_report_success(self):
        self._first_process_saves()
        self._write_corrupt_save()
        loaded, _time, _weather = self._restart().load(self.save_file)
        self.assertFalse(loaded, "a half-written save must never load as if it were whole")

    def test_the_backup_is_a_complete_save_from_before_the_crash(self):
        """The documented way out: the .bak is real, and says so."""
        first = self._first_process_saves()
        self.world.save_game(self.save_file)  # the second save takes the backup
        self.assertTrue(os.path.exists(self.backup_path))
        with open(self.backup_path, "r", encoding="utf-8") as handle:
            backup = json.load(handle)
        self.assertEqual(SAVE_FORMAT_VERSION, backup.get("save_format_version"))
        self.assertEqual(
            json.loads(first).get("player", {}).get("name"),
            backup.get("player", {}).get("name"),
        )

    def test_a_restarted_process_does_not_overwrite_the_wreckage(self):
        """Refusing is the recoverable choice: the operator still has the file."""
        self._first_process_saves()
        self._write_corrupt_save()
        manager = self._restart()
        manager.load(self.save_file)
        self.assertFalse(manager.save(self.save_file))
        self.assertEqual('{"player": {"name": "Advent', self._read_save())

    def test_a_restart_over_a_missing_save_starts_cleanly(self):
        """No file is not a crash: the common case must not be treated as damage."""
        self.assertFalse(os.path.exists(self.save_path))
        manager = self._restart()
        loaded, _time, _weather = manager.load(self.save_file)
        self.assertFalse(loaded, "there is nothing to load")
        self.assertTrue(manager.save(self.save_file), "and nothing to refuse either")


if __name__ == "__main__":
    unittest.main()
