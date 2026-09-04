import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.core.knowledge_manager import KnowledgeManager
import engine.core.knowledge_manager as knowledge_manager_module


class _DummyWorld:
    def __init__(self, data_root: Path) -> None:
        self.data_root = str(data_root)


class TestKnowledgeManagerWarnings(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._tmp_dir = repo_root / "server" / "tests" / "_tmp" / f"knowledge_topics_test_{uuid.uuid4().hex}"
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self._tmp_dir, ignore_errors=True))
        self.world = _DummyWorld(self._tmp_dir)

    def test_missing_topics_emits_structured_warning(self) -> None:
        warnings = []

        def sink(code: str, message: str, source: str) -> None:
            warnings.append({"code": code, "message": message, "source": source})

        KnowledgeManager(self.world, warning_sink=sink)
        self.assertTrue(any(w["code"] == "content.topics.missing" for w in warnings))

    def test_invalid_topics_json_emits_load_error_warning(self) -> None:
        warnings = []

        def sink(code: str, message: str, source: str) -> None:
            warnings.append({"code": code, "message": message, "source": source})

        knowledge_dir = self._tmp_dir / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        (knowledge_dir / "topics.json").write_text("{bad json", encoding="utf-8")

        KnowledgeManager(self.world, warning_sink=sink)
        self.assertTrue(any(w["code"] == "content.topics.load_error" for w in warnings))

    def test_valid_topics_json_loads_without_warning(self) -> None:
        warnings = []

        def sink(code: str, message: str, source: str) -> None:
            warnings.append({"code": code, "message": message, "source": source})

        knowledge_dir = self._tmp_dir / "knowledge"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        (knowledge_dir / "topics.json").write_text(
            json.dumps({"job": {"display_name": "Job", "keywords": [], "responses": []}}),
            encoding="utf-8",
        )

        km = KnowledgeManager(self.world, warning_sink=sink)
        self.assertIn("job", km.topics)
        self.assertEqual([], warnings)


if __name__ == "__main__":
    unittest.main()
