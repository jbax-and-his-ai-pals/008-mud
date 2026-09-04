# tests/singles/test_knowledge_overlap.py
from tests.fixtures import GameTestBase

class TestKnowledgeOverlap(GameTestBase):

    def test_longest_match_priority(self):
        """Verify 'magic missile' is tagged instead of just 'magic'."""
        km = self.game.knowledge_manager
        
        # 1. Define two overlapping topics
        km.topics["magic"] = {"display_name": "Magic", "keywords": []}
        km.topics["magic_missile"] = {"display_name": "Magic Missile", "keywords": []}
        
        # 2. Test text containing both
        raw_text = "I love the magic missile spell."
        processed = km.parse_and_highlight(raw_text, self.player)
        
        # 3. Assertions
        # Should contain the tag for the longer phrase
        self.assertIn("[[CMD:ask magic missile]]", processed)
        # Should NOT contain a double-tagging or a tag for just 'magic' that breaks the other
        self.assertNotIn("[[CMD:ask magic]] missile", processed)

    def test_case_insensitive_match(self):
        """Verify keywords are found regardless of case."""
        km = self.game.knowledge_manager
        km.topics["test_topic"] = {"display_name": "Testing", "keywords": ["Specific Word"]}
        
        raw_text = "Let's talk about a specific word."
        processed = km.parse_and_highlight(raw_text, self.player)
        
        self.assertIn("[[CMD:ask specific word]]", processed)