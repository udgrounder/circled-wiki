import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from circled_wiki.core.frontmatter import markdown_read_session, parse_markdown, render_markdown
from circled_wiki.core.validator import validate_repository


class MarkdownReadSessionTests(unittest.TestCase):
    def test_reuses_parses_without_sharing_mutable_documents(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_text(render_markdown({"title": "before", "nested": {"value": 1}}))

            @markdown_read_session
            def read_twice():
                first = parse_markdown(path)
                first.frontmatter["nested"]["value"] = 99
                return parse_markdown(path)

            with patch("circled_wiki.core.frontmatter.yaml.safe_load", wraps=yaml.safe_load) as load:
                self.assertEqual(read_twice().frontmatter["nested"]["value"], 1)
                self.assertEqual(load.call_count, 1)
                read_twice()
                self.assertEqual(load.call_count, 2)

    def test_write_replace_delete_and_exception_do_not_leave_stale_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.md"
            path.write_text(render_markdown({"title": "before"}))

            @markdown_read_session
            def change():
                self.assertEqual(parse_markdown(path).frontmatter["title"], "before")
                path.write_text(render_markdown({"title": "after!"}))
                self.assertEqual(parse_markdown(path).frontmatter["title"], "after!")
                replacement = path.with_suffix(".new")
                replacement.write_text(render_markdown({"title": "replaced"}))
                replacement.replace(path)
                self.assertEqual(parse_markdown(path).frontmatter["title"], "replaced")
                path.unlink()
                with self.assertRaises(FileNotFoundError):
                    parse_markdown(path)
                raise RuntimeError("end operation")

            with self.assertRaisesRegex(RuntimeError, "end operation"):
                change()
            path.write_text(render_markdown({"title": "next operation"}))
            self.assertEqual(parse_markdown(path).frontmatter["title"], "next operation")

    def test_repository_parses_each_document_once_and_keeps_reference_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            path = root / "bundles/general/example.md"
            path.parent.mkdir(parents=True)
            path.write_text(render_markdown({
                "type": "guide", "title": "unique-parse-marker", "status": "active",
                "evidence": ["evidence/example-org/missing.md"],
            }))
            with patch("circled_wiki.core.frontmatter.yaml.safe_load", wraps=yaml.safe_load) as load:
                results = validate_repository(root)
            document_reads = [call for call in load.call_args_list if "unique-parse-marker" in str(call)]
            self.assertEqual(len(document_reads), 1)
            self.assertTrue(any("referenced Evidence Record not found" in error for result in results for error in result.profile_errors))

    def test_large_documents_and_lru_eviction_bound_retained_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f"source-{i}.md" for i in range(3)]
            for path in paths:
                path.write_text(render_markdown({"title": "source"}))

            @markdown_read_session
            def read_with_eviction():
                for path in paths:
                    parse_markdown(path)
                parse_markdown(paths[0])

            with patch.dict(parse_markdown.__globals__, _CACHE_ENTRIES=2), patch("circled_wiki.core.frontmatter.yaml.safe_load", wraps=yaml.safe_load) as load:
                read_with_eviction()
                self.assertEqual(load.call_count, 4)

            @markdown_read_session
            def read_large():
                parse_markdown(paths[0])
                parse_markdown(paths[0])

            with patch.dict(parse_markdown.__globals__, _CACHE_DOCUMENT_BYTES=1), patch("circled_wiki.core.frontmatter.yaml.safe_load", wraps=yaml.safe_load) as load:
                read_large()
                self.assertEqual(load.call_count, 2)

    def test_repository_parses_once_even_when_batch_cache_is_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            path = root / "bundles/general/example.md"
            path.parent.mkdir(parents=True)
            path.write_text(render_markdown({"type": "guide", "title": "no-cache-marker"}))
            with patch.dict(parse_markdown.__globals__, _CACHE_DOCUMENT_BYTES=0), patch("circled_wiki.core.frontmatter.yaml.safe_load", wraps=yaml.safe_load) as load:
                validate_repository(root)
            self.assertEqual(len([call for call in load.call_args_list if "no-cache-marker" in str(call)]), 1)
