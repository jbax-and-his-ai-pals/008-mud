# tests/singles/test_ui_manager.py
from tests.fixtures import GameTestBase
from engine.ui.ui_element import UIPanel

class TestUIManager(GameTestBase):

    def test_panel_registry_and_docking(self):
        """Verify panels can be registered and moved between docks."""
        mgr = self.game.ui_manager
        
        # 1. Create a dummy panel
        def mock_render(surf, ctx, zones): pass
        panel = UIPanel("test_p", 100, "Test Panel", mock_render)
        
        # 2. Register
        mgr.register_panel(panel)
        self.assertIn("test_p", mgr.all_panels_registry)
        
        # 3. Add to Left Dock
        mgr.add_panel_to_dock("test_p", "left")
        self.assertIn(panel, mgr.left_dock)
        
        # 4. Remove
        mgr.remove_panel("test_p")
        self.assertNotIn(panel, mgr.left_dock)
        self.assertNotIn(panel, mgr.right_dock)

    def test_dock_add_duplicate_prevention(self):
        """Verify a panel cannot be added to a dock twice."""
        mgr = self.game.ui_manager
        def mock_render(surf, ctx, zones): pass
        panel = UIPanel("dup_p", 100, "Dup", mock_render)
        
        mgr.register_panel(panel)
        mgr.add_panel_to_dock("dup_p", "left")
        
        # Attempt to add again
        success = mgr.add_panel_to_dock("dup_p", "left")
        self.assertFalse(success)
        self.assertEqual(mgr.left_dock.count(panel), 1)