import tempfile
import unittest
from pathlib import Path
from uniquechat.engine import read_turn


class Attachments(unittest.TestCase):
    def test_text_and_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "notes.txt"
            path.write_text("Local text", encoding="utf8")
            turn = read_turn("Summarize", [path], False)
            self.assertIn("Local text", turn["content"][0]["text"])
            self.assertEqual(turn["content"][1]["text"], "Summarize")

    def test_empty(self):
        with self.assertRaises(ValueError):
            read_turn("   ", [], False)

    def test_text_model_rejects_image(self):
        with self.assertRaises(ValueError):
            read_turn("Describe", ["a.png"], False)

    def test_image_input(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "red.png"
            Image.new("RGB", (24, 24), "red").save(path)
            turn = read_turn("Describe", [path], True)
            self.assertEqual(turn["content"][0]["image"].getpixel((0, 0)), (255, 0, 0))

    def test_file_limits(self):
        with self.assertRaises(ValueError):
            read_turn("read", ["a"] * 4, True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "long.txt"
            path.write_bytes(b"a" * 32769)
            with self.assertRaises(ValueError):
                read_turn("read", [path], True)
