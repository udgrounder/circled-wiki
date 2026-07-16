import tempfile
import unittest
from pathlib import Path

from knowledge_os.core.frontmatter import FrontmatterError, parse_markdown, render_markdown


class FrontmatterTests(unittest.TestCase):
    def test_round_trip_preserves_frontmatter_and_body(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "document.md"
            path.write_text(render_markdown({"type": "guide", "title": "안내"}, "# Body\n"), encoding="utf-8")

            document = parse_markdown(path)

        self.assertEqual(document.frontmatter["type"], "guide")
        self.assertEqual(document.frontmatter["title"], "안내")
        self.assertEqual(document.body, "# Body\n")

    def test_rejects_markdown_without_frontmatter(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            path = Path(temp_directory) / "document.md"
            path.write_text("# Body\n", encoding="utf-8")
            with self.assertRaises(FrontmatterError):
                parse_markdown(path)

