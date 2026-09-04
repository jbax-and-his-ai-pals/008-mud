import unittest

from engine.server.realtime_assets import RealtimeAssetService


def _event_builder(event_type: str, session_id: str, payload):
    return {"type": event_type, "session_id": session_id, "payload": payload}


class TestSvg1BitEnforcement(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RealtimeAssetService(_event_builder)

    def tearDown(self) -> None:
        self.service.close()

    def test_accepts_black_and_white_palette(self) -> None:
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'>"
            "<rect width='8' height='8' fill='white'/>"
            "<rect x='1' y='1' width='6' height='6' stroke='#000' fill='none'/>"
            "</svg>"
        )
        sanitized = self.service.sanitize_svg(svg)
        self.assertEqual(svg, sanitized)

    def test_rejects_non_1bit_color_attribute(self) -> None:
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'>"
            "<rect width='8' height='8' fill='#00ff00'/>"
            "</svg>"
        )
        with self.assertRaisesRegex(ValueError, "non-1-bit colors"):
            self.service.sanitize_svg(svg)

    def test_rejects_non_1bit_style_color(self) -> None:
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'>"
            "<rect width='8' height='8' style='fill: white; stroke: red'/>"
            "</svg>"
        )
        with self.assertRaisesRegex(ValueError, "non-1-bit colors"):
            self.service.sanitize_svg(svg)

    def test_rejects_blocked_script_content(self) -> None:
        svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='8' height='8'>"
            "<script>alert('x')</script>"
            "<rect width='8' height='8' fill='white'/>"
            "</svg>"
        )
        with self.assertRaisesRegex(ValueError, "blocked content"):
            self.service.sanitize_svg(svg)


if __name__ == "__main__":
    unittest.main()
