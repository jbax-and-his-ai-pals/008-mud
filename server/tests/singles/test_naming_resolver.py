# tests/singles/test_naming_resolver.py
"""The shared name resolver.

P3 replaces five ad-hoc matchers that disagreed with each other. The behaviour
that matters to a player is that typing what they *see* works, and that an
ambiguous word produces a question rather than an arbitrary choice.
"""

import unittest

from engine.naming import (
    SCORE_EXACT_ALIAS,
    SCORE_EXACT_ID,
    SCORE_EXACT_NAME,
    SCORE_NAME_PREFIX,
    SCORE_NAME_SUBSTRING,
    SCORE_NAME_WORD,
    SCORE_NAME_WORD_PREFIX,
    ambiguity_message,
    candidate_score,
    normalize,
    resolve_all,
    resolve_best,
    resolve_one,
)


class _Thing:
    def __init__(self, name, obj_id="", aliases=None):
        self.name = name
        self.obj_id = obj_id
        if aliases:
            self.properties = {"aliases": list(aliases)}


class TestNormalize(unittest.TestCase):
    def test_ids_and_prose_compare_equal(self):
        self.assertEqual(normalize("tie_wildflower_posy"), "tie wildflower posy")
        self.assertEqual(normalize("Tie Wildflower Posy"), "tie wildflower posy")
        self.assertEqual(normalize("Tie-Wildflower  Posy"), "tie wildflower posy")

    def test_empty_and_whitespace(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize("   "), "")
        self.assertEqual(normalize(None), "")


class TestScoring(unittest.TestCase):
    def test_exact_id_beats_exact_name(self):
        by_id, _ = candidate_score("item_iron_sword", obj_id="item_iron_sword", name="Iron Sword")
        by_name, _ = candidate_score("Iron Sword", obj_id="item_iron_sword", name="Iron Sword")
        self.assertEqual(by_id, SCORE_EXACT_ID)
        self.assertEqual(by_name, SCORE_EXACT_NAME)
        self.assertGreater(by_id, by_name)

    def test_alias_scores_between_id_and_name(self):
        score, how = candidate_score("posy", name="Tie Wildflower Posy", aliases=["posy"])
        self.assertEqual(score, SCORE_EXACT_ALIAS)
        self.assertEqual(how, "alias")

    def test_prefix_beats_word_beats_substring(self):
        prefix, _ = candidate_score("wildflower", name="Wildflower Posy")
        word, _ = candidate_score("posy", name="Wildflower Posy")
        substring, _ = candidate_score("ower", name="Wildflower Posy")
        self.assertEqual(prefix, SCORE_NAME_PREFIX)
        self.assertEqual(word, SCORE_NAME_WORD)
        self.assertEqual(substring, SCORE_NAME_SUBSTRING)
        self.assertGreater(prefix, word)
        self.assertGreater(word, substring)

    def test_multi_word_query_matches_a_word_run(self):
        score, how = candidate_score("wildflower posy", name="Tie Wildflower Posy")
        self.assertEqual(score, SCORE_NAME_WORD)
        self.assertEqual(how, "words")

    def test_multi_word_query_matches_partial_words(self):
        """`river clay token` should find `Press River-Clay Token`."""
        score, how = candidate_score("river clay token", name="Press River-Clay Token")
        self.assertIn(score, (SCORE_NAME_WORD, SCORE_NAME_WORD_PREFIX))
        self.assertGreater(score, 0)

    def test_whole_query_is_used_not_first_token(self):
        """The original bug: `craft wildflower posy` searched for 'wildflower'."""
        good, _ = candidate_score("wildflower posy", name="Tie Wildflower Posy")
        self.assertGreater(good, 0)

    def test_omitted_letters_do_not_match(self):
        """There is no subsequence matching, by design.

        An earlier revision forgave typos by accepting a query whose letters
        appeared in order anywhere in the name. That resolved `chest` to
        "Kaelan the Alchemist" -- c-h-e-s-t really do appear in order across
        that name -- so looking into a chest found an alchemist. Word-boundary
        matching gives the useful forgiveness without that failure mode.
        """
        for query, name in (
            ("iron swd", "Iron Sword"),
            ("chest", "Kaelan the Alchemist"),
            ("dragon", "Iron Sword"),
        ):
            with self.subTest(query=query, name=name):
                score, _ = candidate_score(query, name=name)
                self.assertEqual(score, 0, "%r wrongly matched %r" % (query, name))

    def test_word_prefix_still_forgives_abbreviation(self):
        """Dropping fuzzy matching must not cost useful abbreviation."""
        self.assertGreater(candidate_score("elder", name="Elder Thorne")[0], 0)
        self.assertGreater(candidate_score("talia", name="Talia the Merchant")[0], 0)

    def test_no_match_returns_zero(self):
        score, how = candidate_score("dragon", name="Iron Sword")
        self.assertEqual(score, 0)
        self.assertEqual(how, "")

    def test_no_match_scores_zero(self):
        score, how = candidate_score("dragon", name="Iron Sword")
        self.assertEqual(score, 0)
        self.assertEqual(how, "")

    def test_single_character_does_not_match_everything(self):
        """A one-letter query must not resolve to every name containing it."""
        for name in ("Iron Sword", "Rat Tail", "Wildflower Posy"):
            score, _ = candidate_score("r", name=name)
            self.assertEqual(score, 0, "single-char query matched %r" % name)

    def test_empty_query_matches_nothing(self):
        self.assertEqual(candidate_score("", name="Iron Sword"), (0, ""))


class TestResolution(unittest.TestCase):
    def setUp(self):
        self.sword = _Thing("Iron Sword", "item_iron_sword")
        self.dagger = _Thing("Iron Dagger", "item_iron_dagger")
        self.tail = _Thing("Rat Tail", "item_rat_tail")
        self.posy = _Thing("Tie Wildflower Posy", "tie_wildflower_posy", aliases=["posy", "flowers"])
        self.pool = [self.sword, self.dagger, self.tail, self.posy]

    def test_resolve_all_is_best_first(self):
        matches = resolve_all("iron", self.pool)
        self.assertTrue(matches)
        self.assertGreaterEqual(matches[0].score, matches[-1].score)

    def test_specific_query_beats_generic_one(self):
        matches = resolve_all("iron sword", self.pool)
        self.assertIs(matches[0].obj, self.sword)

    def test_exact_name_wins_over_substring(self):
        matches = resolve_all("rat tail", self.pool)
        self.assertIs(matches[0].obj, self.tail)

    def test_alias_resolves(self):
        self.assertIs(resolve_one("posy", self.pool), self.posy)
        self.assertIs(resolve_one("flowers", self.pool), self.posy)

    def test_id_resolves(self):
        self.assertIs(resolve_one("item_rat_tail", self.pool), self.tail)

    def test_ambiguous_query_returns_none_from_resolve_one(self):
        """`iron` matches two things equally; do not pick one silently."""
        matches = resolve_all("iron", self.pool)
        self.assertEqual(matches[0].score, matches[1].score)
        self.assertIsNone(resolve_one("iron", self.pool))

    def test_resolve_best_still_returns_something_when_tied(self):
        self.assertIsNotNone(resolve_best("iron", self.pool))

    def test_ambiguity_message_is_a_question(self):
        matches = resolve_all("iron", self.pool)
        message = ambiguity_message("iron", matches)
        self.assertTrue(message.endswith("?"))
        self.assertIn("Iron Sword", message)
        self.assertIn("Iron Dagger", message)

    def test_no_match_returns_none_and_no_message(self):
        self.assertEqual(resolve_all("dragon", self.pool), [])
        self.assertIsNone(resolve_one("dragon", self.pool))
        self.assertIsNone(resolve_best("dragon", self.pool))

    def test_none_candidates_are_skipped(self):
        self.assertIs(resolve_one("rat tail", [None, self.tail]), self.tail)

    def test_custom_accessors(self):
        rows = [{"label": "A Rusty Key", "key": "k1"}, {"label": "A Brass Key", "key": "k2"}]
        found = resolve_one(
            "brass key",
            rows,
            name_of=lambda r: r["label"],
            id_of=lambda r: r["key"],
            aliases_of=lambda r: (),
        )
        self.assertEqual(found["key"], "k2")

    def test_deterministic_ordering_on_a_tie(self):
        """Equal scores must order predictably, not by insertion luck."""
        a = _Thing("Iron Sword", "id_b")
        b = _Thing("Iron Sword", "id_a")
        first = [m.obj.obj_id for m in resolve_all("iron sword", [a, b])]
        second = [m.obj.obj_id for m in resolve_all("iron sword", [b, a])]
        self.assertEqual(first, second)

    def test_dict_candidates_are_matched_by_default(self):
        """Mappings are a normal candidate shape, not a silent no-match.

        The default accessors read `getattr(obj, "name")`, so a caller who
        passed dicts got zero matches and *no error* -- `reply <words>` in a
        conversation matched nothing at all before this was fixed.
        """
        rows = [{"name": "What are you working on?", "obj_id": "work"},
                {"name": "Goodbye.", "obj_id": "bye"}]
        self.assertEqual("work", resolve_one("what are you working on", rows)["obj_id"])
        self.assertEqual("bye", resolve_best("goodbye", rows)["obj_id"])

    def test_dict_candidates_honour_display_name_and_aliases(self):
        rows = [
            {"display_name": "Talia the Merchant", "id": "merchant"},
            {"name": "A Posy for Riverside", "id": "posy", "aliases": ["flowers", "bouquet"]},
        ]
        self.assertEqual("merchant", resolve_one("talia", rows)["id"])
        self.assertEqual("posy", resolve_one("bouquet", rows)["id"])


if __name__ == "__main__":
    unittest.main()
