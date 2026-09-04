# tests/singles/test_knowledge_highlighting.py
from tests.fixtures import GameTestBase

class TestKnowledgeHighlighting(GameTestBase):

    def test_topic_parsing_and_tagging(self):
        """Verify keywords in text are wrapped in [[CMD]] tags."""
        km = self.game.knowledge_manager
        
        # Define a topic
        km.topics["rumors"] = {
            "display_name": "Rumors",
            "keywords": ["gossip"]
        }
        
        # 1. Test basic highlight
        raw_text = "I heard some interesting rumors lately."
        # Note: formatting logic uses vocabulary check. Initial vocab contains 'rumors'.
        processed = km.parse_and_highlight(raw_text, self.player)
        
        self.assertIn("[[CMD:ask rumors]]", processed)
        self.assertIn("rumors", processed)
        self.assertIn("[[/CMD]]", processed)

    def test_keyword_alias_tagging(self):
        """Verify aliases (keywords) also trigger the primary topic command."""
        km = self.game.knowledge_manager
        km.topics["missing_supplies"] = {
            "display_name": "Missing Supplies",
            "keywords": ["caravan"]
        }
        
        raw_text = "The caravan never arrived."
        processed = km.parse_and_highlight(raw_text, self.player)
        
        # It should tag 'caravan' but point to 'ask caravan' (which resolves to the ID)
        self.assertIn("[[CMD:ask caravan]]", processed)
        self.assertIn("caravan", processed)