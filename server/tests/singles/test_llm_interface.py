# tests/singles/test_llm_interface.py
"""Coverage for engine/ai/llm_interface.py: constructor/prompt-loading
(including the load-failure fallback), and generate()'s full branch matrix
(no pipeline, unknown prompt key, successful generation, None output,
unexpected output shape, and exceptions during generation) -- previously
entirely untested. _load_model()'s actual model-loading body is dead code
(an unconditional `return` disables it), so it's intentionally not tested."""

import unittest
from unittest.mock import patch, MagicMock

from engine.ai.llm_interface import LLMInterface


class TestLLMInterfaceConstruction(unittest.TestCase):
    def test_pipe_stays_none_since_load_model_is_disabled(self):
        llm = LLMInterface()
        self.assertIsNone(llm.pipe)

    def test_real_prompts_json_is_loaded(self):
        llm = LLMInterface()
        self.assertIn("generate_room_description", llm.prompts)

    def test_load_prompts_failure_returns_empty_dict(self):
        with patch("builtins.open", side_effect=OSError("boom")):
            llm = LLMInterface()
        self.assertEqual({}, llm.prompts)


class TestLLMInterfaceGenerate(unittest.TestCase):
    def setUp(self):
        self.llm = LLMInterface()

    def test_no_pipeline_returns_error(self):
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertIn("pipeline is not available", result)

    def test_unknown_prompt_key_returns_error(self):
        self.llm.pipe = MagicMock()
        result = self.llm.generate("not_a_real_prompt_key", {})
        self.assertIn("not found", result)

    def test_successful_generation_returns_stripped_text(self):
        self.llm.pipe = MagicMock(return_value=[{"generated_text": "  A dark and misty cave.  "}])
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertEqual("A dark and misty cave.", result)

    def test_none_output_returns_error(self):
        self.llm.pipe = MagicMock(return_value=None)
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertIn("no output", result)

    def test_unexpected_output_shape_returns_error(self):
        self.llm.pipe = MagicMock(return_value=[{"not_generated_text": "oops"}])
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertIn("expected output format", result.lower())

    def test_empty_output_list_returns_error(self):
        self.llm.pipe = MagicMock(return_value=[])
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertIn("expected output format", result.lower())

    def test_exception_during_generation_is_caught(self):
        self.llm.pipe = MagicMock(side_effect=RuntimeError("model exploded"))
        result = self.llm.generate("generate_room_description", {"keywords": "dark cave"})
        self.assertIn("unexpected error", result.lower())
        self.assertIn("model exploded", result)

    def test_missing_replacement_key_is_caught_as_exception(self):
        self.llm.pipe = MagicMock()
        result = self.llm.generate("generate_room_description", {})  # missing {keywords}
        self.assertIn("unexpected error", result.lower())


if __name__ == "__main__":
    unittest.main()
