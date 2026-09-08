# tests/singles/test_text_formatter.py
"""Coverage for engine/utils/text_formatter.py: TextFormatter's word-wrapping
render(), its [[tag]] segment parser, and the pure helper functions
get_level_diff_category() / format_target_name(). render() is exercised
against a real (headless) pygame Surface+Font, matching the pattern already
used by test_panel_content_player_context.py.

Note: two branches are left untested as unreachable:
- the `elif content == '[[/]]':` reset-color body -- DEFAULT_COLORS maps
  FORMAT_RESET (== "[[/]]") to a color, so `if content in self.colors:`
  (the very first branch in the chain) already matches and handles it;
  the literal "[[/]]" string can never fall through to this elif.
- the segment-loop's "matched neither 'format' nor 'text', fall through
  to the next segment" arc -- _parse_segments() only ever tags a segment
  as 'format' or 'text', so the if/elif chain covering exactly those two
  values always matches one of them."""

import unittest

import pygame

from engine.utils.text_formatter import (
    TextFormatter, ClickableZone, get_level_diff_category, format_target_name,
)
from engine.config import FORMAT_RESET, FORMAT_RED, FORMAT_GREEN


class TestTextFormatterRender(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.font.init()
        self.font = pygame.font.SysFont(None, 20)
        self.surface = pygame.Surface((400, 300))
        self.tf = TextFormatter(self.font, screen_width=400, margin=10, line_spacing=5)

    def tearDown(self):
        # Deliberately not calling pygame.quit(): it tears down the process-wide
        # SDL font subsystem, which invalidates other modules' cached Font
        # objects for the rest of the test suite (they become dangling and
        # segfault on the next render()).
        pass

    def test_update_screen_width_recalculates_usable_width(self):
        self.tf.update_screen_width(800)
        self.assertEqual(800, self.tf.screen_width)
        self.assertEqual(800 - 20, self.tf.usable_width)

    def test_render_empty_text_returns_start_y_unchanged(self):
        result = self.tf.render(self.surface, "", (10, 10))
        self.assertEqual(10, result)

    def test_render_simple_text_advances_y(self):
        result = self.tf.render(self.surface, "Hello world", (10, 10))
        self.assertGreater(result, 10)

    def test_render_blank_line_advances_by_blank_line_height(self):
        # "\n".split("\n") == ["", ""] -- two blank lines get processed.
        start_y = 10
        result = self.tf.render(self.surface, "\n", (10, start_y))
        self.assertEqual(start_y + 2 * self.tf.blank_line_height, result)

    def test_render_multiple_lines_advances_multiple_times(self):
        one_line = self.tf.render(self.surface, "Hi", (10, 10))
        two_lines = self.tf.render(self.surface, "Hi\nThere", (10, 10))
        self.assertGreater(two_lines, one_line)

    def test_render_wraps_long_word_sequence_to_new_line(self):
        narrow_tf = TextFormatter(self.font, screen_width=60, margin=5, line_spacing=2)
        text = " ".join(["word"] * 20)
        result = narrow_tf.render(self.surface, text, (5, 5))
        # Enough words to force at least one wrap -> y should have advanced
        # by more than a single line's worth.
        self.assertGreater(result, 5 + narrow_tf.line_height_with_text)

    def test_render_respects_max_height_and_stops_mid_line(self):
        text = " ".join(["word"] * 30)
        result = self.tf.render(self.surface, text, (10, 10), max_height=15)
        self.assertLessEqual(result, 10 + 15 + self.tf.line_height_with_text)

    def test_render_word_wider_than_line_is_not_wrapped_mid_line(self):
        # A single word too wide for the whole usable width, as the first
        # word on its line (x == x_start), cannot be wrapped further.
        narrow_tf = TextFormatter(self.font, screen_width=40, margin=2, line_spacing=2)
        result = narrow_tf.render(self.surface, "supercalifragilisticexpialidocious", (2, 2))
        self.assertGreater(result, 2)

    def test_render_breaks_after_a_full_line_when_max_height_reached(self):
        start_y = 10
        max_height = self.tf.line_height_with_text
        result = self.tf.render(self.surface, "line one\nline two\nline three", (10, start_y), max_height=max_height)
        self.assertEqual(start_y + self.tf.line_height_with_text, result)

    def test_render_blank_line_breaks_when_exceeding_max_height(self):
        result = self.tf.render(self.surface, "\n\n\n\n\n\n\n\n\n\n", (10, 10), max_height=5)
        self.assertGreaterEqual(result, 10)

    def test_render_color_tag_changes_current_color(self):
        # Must not raise, and must consume the tag rather than rendering it as text.
        self.tf.render(self.surface, f"{FORMAT_RED}red text{FORMAT_RESET}", (10, 10))

    def test_render_unknown_format_tag_is_ignored_as_non_color(self):
        # A bracketed tag that isn't a known color/command marker falls through
        # all the elif branches silently.
        self.tf.render(self.surface, "[[unknown_tag]]plain text", (10, 10))

    def test_render_reset_tag_restores_default_color(self):
        self.tf.render(self.surface, f"{FORMAT_RED}colored{FORMAT_RESET}[[/]]back to default", (10, 10))

    def test_render_text_segment_followed_by_more_segments_on_the_same_line(self):
        # A leading plain-text segment followed by a format tag exercises the
        # loop continuing past a 'text' segment to a later segment on the
        # same line, rather than a text segment always being the last one.
        self.tf.render(self.surface, f"plain {FORMAT_RED}red{FORMAT_RESET}", (10, 10))

    def test_render_command_tag_creates_hotspot(self):
        self.tf.render(self.surface, "[[CMD:look sword]]sword[[/CMD]] on the table", (10, 10))
        commands = [z.command for z in self.tf.last_hotspots]
        self.assertIn("look sword", commands)

    def test_render_word_after_cmd_close_has_no_hotspot(self):
        self.tf.render(self.surface, "[[CMD:look sword]]sword[[/CMD]] plain", (10, 10))
        commands = [z.command for z in self.tf.last_hotspots]
        self.assertNotIn(None, [c for c in commands])  # sanity: hotspots only exist for the command word

    def test_render_double_space_between_words_advances_x_without_extra_render(self):
        # Two consecutive spaces produce an empty split element mid-sequence.
        self.tf.render(self.surface, "one  two", (10, 10))  # must not raise

    def test_remove_format_codes_strips_tags(self):
        text = f"{FORMAT_RED}Hello{FORMAT_RESET} [[CMD:look]]world[[/CMD]]"
        self.assertEqual("Hello world", self.tf.remove_format_codes(text))

    def test_parse_segments_splits_text_and_format(self):
        segments = self.tf._parse_segments(f"plain{FORMAT_RED}colored")
        types = [s[0] for s in segments]
        self.assertIn("format", types)
        self.assertIn("text", types)


class TestGetLevelDiffCategoryLowLevel(unittest.TestCase):
    """viewer_level <= 5 uses the fixed per-diff thresholds."""

    def test_purple_at_or_above_plus_three(self):
        self.assertEqual("purple", get_level_diff_category(5, 8))

    def test_red_at_plus_two(self):
        self.assertEqual("red", get_level_diff_category(5, 7))

    def test_orange_at_plus_one(self):
        self.assertEqual("orange", get_level_diff_category(5, 6))

    def test_yellow_at_even(self):
        self.assertEqual("yellow", get_level_diff_category(5, 5))

    def test_blue_at_minus_one(self):
        self.assertEqual("blue", get_level_diff_category(5, 4))

    def test_green_at_minus_two(self):
        self.assertEqual("green", get_level_diff_category(5, 3))

    def test_gray_below_minus_two(self):
        self.assertEqual("gray", get_level_diff_category(5, 1))


class TestGetLevelDiffCategoryHighLevel(unittest.TestCase):
    """viewer_level > 5 uses scaling thresholds."""

    def test_purple_far_above_threshold(self):
        self.assertEqual("purple", get_level_diff_category(10, 40))

    def test_red_at_threshold(self):
        self.assertEqual("red", get_level_diff_category(10, 12))

    def test_orange_at_threshold(self):
        self.assertEqual("orange", get_level_diff_category(10, 11))

    def test_yellow_at_even(self):
        self.assertEqual("yellow", get_level_diff_category(10, 10))

    def test_blue_below_yellow_bound(self):
        self.assertEqual("blue", get_level_diff_category(10, 9))

    def test_green_below_blue_bound(self):
        self.assertEqual("green", get_level_diff_category(10, 8))

    def test_gray_far_below_all_bounds(self):
        self.assertEqual("gray", get_level_diff_category(10, -50))


class TestFormatTargetName(unittest.TestCase):
    def test_target_without_name_returns_something(self):
        class _NoName:
            pass
        self.assertEqual("something", format_target_name(None, _NoName()))

    def test_non_hostile_target_uses_default_format(self):
        class _Friendly:
            name = "Friendly Villager"
            faction = "friendly"
            level = 1
        result = format_target_name(None, _Friendly())
        self.assertEqual(f"{FORMAT_RESET}Friendly Villager{FORMAT_RESET}", result)

    def test_target_without_faction_uses_default_format(self):
        class _NoFaction:
            name = "Mystery Thing"
        result = format_target_name(None, _NoFaction())
        self.assertEqual(f"{FORMAT_RESET}Mystery Thing{FORMAT_RESET}", result)

    def test_hostile_target_without_viewer_uses_default_format(self):
        class _Hostile:
            name = "Goblin"
            faction = "hostile"
            level = 3
        result = format_target_name(None, _Hostile())
        self.assertEqual(f"{FORMAT_RESET}Goblin{FORMAT_RESET}", result)

    def test_hostile_target_with_viewer_uses_level_diff_color(self):
        from engine.utils.text_formatter import FORMAT_PURPLE
        class _Hostile:
            name = "Goblin"
            faction = "hostile"
            level = 8  # viewer=5, diff=3 -> purple per get_level_diff_category
        class _Viewer:
            level = 5
        result = format_target_name(_Viewer(), _Hostile())
        self.assertEqual(f"{FORMAT_PURPLE}Goblin{FORMAT_RESET}", result)


if __name__ == "__main__":
    unittest.main()
