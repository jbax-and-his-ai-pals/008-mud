import json
import shutil
import unittest
from pathlib import Path
import uuid

from engine.magic import spell_registry


class TestSpellRegistryLoad(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._tmp_dir = repo_root / "server" / "tests" / "_tmp" / f"spell_registry_test_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self._tmp_dir, ignore_errors=True))
    def tearDown(self) -> None:
        spell_registry.SPELL_REGISTRY.clear()

    def _write_magic_file(self, filename: str, payload: dict) -> None:
        magic_dir = self._tmp_dir / "magic"
        magic_dir.mkdir(parents=True, exist_ok=True)
        (magic_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    def test_load_spells_is_idempotent_across_repeated_loads(self) -> None:
        self._write_magic_file(
            "base.json",
            {
                "spell_a": {"name": "Spell A", "mana_cost": 1, "description": "a", "effects": [{"type": "damage", "value": 1}]},
                "spell_b": {"name": "Spell B", "mana_cost": 2, "description": "b", "effects": [{"type": "damage", "value": 2}]},
            },
        )
        first = spell_registry.load_spells_from_json(str(self._tmp_dir))
        second = spell_registry.load_spells_from_json(str(self._tmp_dir))

        self.assertEqual(2, len(spell_registry.SPELL_REGISTRY))
        self.assertEqual(0, first["overwrites"])
        self.assertEqual(0, second["overwrites"])
        self.assertEqual(first["spells_loaded"], second["spells_loaded"])

    def test_load_spells_reports_duplicate_ids_within_data(self) -> None:
        self._write_magic_file(
            "one.json",
            {
                "spell_dup": {"name": "Spell One", "mana_cost": 1, "description": "one", "effects": [{"type": "damage", "value": 1}]},
            },
        )
        self._write_magic_file(
            "two.json",
            {
                "spell_dup": {"name": "Spell Two", "mana_cost": 2, "description": "two", "effects": [{"type": "damage", "value": 2}]},
            },
        )
        stats = spell_registry.load_spells_from_json(str(self._tmp_dir))

        self.assertEqual(1, stats["overwrites"])
        self.assertEqual(1, len(spell_registry.SPELL_REGISTRY))


if __name__ == "__main__":
    unittest.main()
