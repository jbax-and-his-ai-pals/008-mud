# tests/singles/test_region_generator_full.py
"""Coverage for engine/world/region_generator.py's load_themes() error
handling (missing file / malformed JSON).

Note: generate_region()'s "no free direction found" failure branches
(the inner direction-search loop exhausting without a match, the outer
frontier-search loop exhausting without a match, and the room-count loop
breaking early as a result) are left untested as practically unreachable:
the algorithm grows outward on an *unbounded* 3D lattice and every newly
connected room joins the frontier without ever being removed from it, so
there is always some frontier member with a free neighboring direction.
Empirically, requesting even 500 rooms from a real theme completes every
single room without ever exhausting a search -- forcing a genuine failure
would require literally surrounding every frontier member in 3D space,
which no realistic (or even stress-test-scale) room count reaches."""

import json
import unittest

from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator


class TestLoadThemesErrorHandling(GameTestBase):
    def test_missing_theme_file_is_handled_gracefully(self):
        original_content_root = self.world.content_root
        self.world.content_root = "/totally/bogus/missing/data/root"
        try:
            generator = RegionGenerator(self.world)
        finally:
            self.world.content_root = original_content_root
        self.assertEqual({}, generator.themes)

    def test_malformed_theme_file_is_handled_gracefully(self):
        import tempfile
        import os

        tmp_dir = tempfile.mkdtemp()
        regions_dir = os.path.join(tmp_dir, "regions")
        os.makedirs(regions_dir)
        with open(os.path.join(regions_dir, "dynamic_themes.json"), "w") as f:
            f.write("{not valid json")

        original_content_root = self.world.content_root
        self.world.content_root = tmp_dir
        try:
            generator = RegionGenerator(self.world)
        finally:
            self.world.content_root = original_content_root
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)
        self.assertEqual({}, generator.themes)


if __name__ == "__main__":
    unittest.main()
