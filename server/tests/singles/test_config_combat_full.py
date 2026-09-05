# tests/singles/test_config_combat_full.py
"""Coverage for engine/config/config_combat.py's configure_combat_elements():
the malformed (non-dict) elements.json branch, which no shipped content
set's data triggers since World.__init__ already exercises the
file-missing and valid-dict paths for every test in the suite."""

import json
import os
import shutil
import tempfile
import unittest

from engine.config import config_combat


class TestConfigureCombatElementsMalformedFile(unittest.TestCase):
    def test_non_dict_elements_json_falls_back_to_defaults(self):
        tmp_dir = tempfile.mkdtemp()
        try:
            combat_dir = os.path.join(tmp_dir, "combat")
            os.makedirs(combat_dir)
            with open(os.path.join(combat_dir, "elements.json"), "w") as f:
                json.dump(["not", "a", "dict"], f)

            original_damage_types = list(config_combat.VALID_DAMAGE_TYPES)
            config_combat.configure_combat_elements(tmp_dir)
            try:
                self.assertEqual(
                    config_combat._DEFAULT_ELEMENTAL_DATA["valid_damage_types"],
                    config_combat.VALID_DAMAGE_TYPES,
                )
            finally:
                config_combat.VALID_DAMAGE_TYPES[:] = original_damage_types
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
