# tests/singles/test_commands_init_full.py
"""Coverage for engine/commands/__init__.py's directory-scan loop: a
standard .py module that fails to import, a subdirectory without an
__init__.py (skipped as not a package), and a subpackage that fails to
import. All three are simulated via mocked os.listdir/os.path.* calls and
a reload of the already-imported engine.commands package, since real
command modules all import cleanly in this codebase."""

import importlib
import os
import unittest
from unittest.mock import patch

import engine.commands as commands_pkg

_REAL_LISTDIR = os.listdir
_REAL_ISFILE = os.path.isfile
_REAL_ISDIR = os.path.isdir
_REAL_EXISTS = os.path.exists
_REAL_IMPORT_MODULE = importlib.import_module


class TestCommandsInitErrorHandling(unittest.TestCase):
    def tearDown(self):
        # Restore the package to its normal, fully-loaded state for any
        # tests that run after this one in the same process.
        importlib.reload(commands_pkg)

    def _reload_with(self, fake_entries, missing_init_for=None, broken_module=None):
        def fake_listdir(path):
            if os.path.normpath(path) == os.path.normpath(commands_pkg.package_dir):
                return fake_entries
            return _REAL_LISTDIR(path)

        def fake_isfile(path):
            basename = os.path.basename(path)
            if basename in fake_entries:
                return basename.endswith(".py")
            return _REAL_ISFILE(path)

        def fake_isdir(path):
            basename = os.path.basename(path)
            if basename in fake_entries:
                return not basename.endswith(".py")
            return _REAL_ISDIR(path)

        def fake_exists(path):
            if missing_init_for and missing_init_for in path and path.endswith("__init__.py"):
                return False
            if broken_module and f"{broken_module}{os.sep}__init__.py" in path:
                return True
            return _REAL_EXISTS(path)

        def fake_import_module(name, package=None):
            if broken_module and name == f".{broken_module}":
                raise ImportError("simulated failure")
            return _REAL_IMPORT_MODULE(name, package)

        with patch("os.listdir", side_effect=fake_listdir), \
             patch("os.path.isfile", side_effect=fake_isfile), \
             patch("os.path.isdir", side_effect=fake_isdir), \
             patch("os.path.exists", side_effect=fake_exists), \
             patch("importlib.import_module", side_effect=fake_import_module):
            importlib.reload(commands_pkg)

    def test_broken_module_import_error_is_logged_and_swallowed(self):
        self._reload_with(["broken_module_xyz.py"], broken_module="broken_module_xyz")

    def test_subdirectory_without_init_is_skipped(self):
        self._reload_with(["fake_subpkg_no_init"], missing_init_for="fake_subpkg_no_init")

    def test_broken_subpackage_import_error_is_logged_and_swallowed(self):
        self._reload_with(["fake_broken_subpkg"], broken_module="fake_broken_subpkg")


if __name__ == "__main__":
    unittest.main()
