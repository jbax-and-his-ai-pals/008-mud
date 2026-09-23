"""The knowledge-condition constants are the words the reader compares against.

`KnowledgeManager._check_conditions` is a chain of string comparisons, and a
condition key or state it does not compare against is silently ignored -- the
response simply always (or never) applies. The constants beside it are what the
content validator and the editor's picker are built from, so they must name
exactly what the reader handles: a kind added to the reader but not the
constants is refused by the validator, and one in the constants but not the
reader is offered to authors and does nothing.
"""
import inspect
import re
import unittest

from engine.core.knowledge_manager import (
    CAMPAIGN_STATES,
    KNOWLEDGE_CONDITION_KINDS,
    KNOWLEDGE_STATES,
    QUEST_STATES,
    KnowledgeManager,
)


class TestKnowledgeConditionVocabulary(unittest.TestCase):
    def setUp(self):
        self.source = inspect.getsource(KnowledgeManager._check_conditions)

    def _block(self, key: str) -> str:
        """The source handling one condition key, up to the next key's branch."""
        start = self.source.index(f'if key == "{key}"')
        following = [m.start() for m in re.finditer(r'if key == "', self.source) if m.start() > start]
        return self.source[start:following[0] if following else len(self.source)]

    def test_the_kinds_are_exactly_the_keys_the_reader_compares(self):
        compared = set(re.findall(r'key == "([a-z_]+)"', self.source))
        self.assertEqual(set(KNOWLEDGE_CONDITION_KINDS), compared)

    def test_knowledge_states_match_the_reader(self):
        self.assertEqual(set(KNOWLEDGE_STATES), set(re.findall(r'state_req == "([a-z_]+)"', self._block("knowledge_state"))))

    def test_campaign_states_match_the_reader(self):
        self.assertEqual(set(CAMPAIGN_STATES), set(re.findall(r'state_req == "([a-z_]+)"', self._block("campaign_state"))))

    def test_quest_states_match_the_reader(self):
        self.assertEqual(set(QUEST_STATES), set(re.findall(r'req_state == "([a-z_]+)"', self._block("quest_state"))))


if __name__ == "__main__":
    unittest.main()
