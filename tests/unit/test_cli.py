import tempfile
import unittest
import unicodedata
import io
import json
import argparse
from pathlib import Path
from unittest.mock import patch

from circled_wiki.cli.__main__ import (
    _bootstrap_configuration,
    _resolve_capture_file,
    main,
    run_cli,
)
from circled_wiki.config.settings import render_settings
from circled_wiki.config.paths import project_root


class CliTests(unittest.TestCase):
    def test_project_root_resolves_source_repository_without_knowledge(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "pyproject.toml").write_text("[project]\nname = 'test'\n", encoding="utf-8")
            (root / "src" / "circled_wiki").mkdir(parents=True)

            self.assertEqual(project_root(root), root.resolve())

    def test_project_exposes_circled_wiki_cli_alias(self):
        project = Path(__file__).resolve().parents[2]
        metadata = (project / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('circled-wiki = "circled_wiki.runtime.cli.__main__:main"', metadata)

    def test_first_install_prompts_for_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                target=str(Path(directory) / "target"),
                organization_id=None,
                organization_name=None,
                operator_agent=None,
                graphify=None,
            )
            with patch("sys.stdin.isatty", return_value=True):
                with patch("builtins.input", side_effect=["acme", "Acme", "atlas", "yes"]):
                    result = _bootstrap_configuration(args)
        self.assertEqual(result["organization_id"], "acme")
        self.assertEqual(result["organization_name"], "Acme")
        self.assertEqual(result["operator_agent"], "atlas")
        self.assertTrue(result["graphify_enabled"])

    def test_noninteractive_first_install_requires_explicit_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(
                target=str(Path(directory) / "target"),
                organization_id=None,
                organization_name=None,
                operator_agent=None,
                graphify=None,
            )
            with patch("sys.stdin.isatty", return_value=False):
                with self.assertRaisesRegex(ValueError, "first installation requires"):
                    _bootstrap_configuration(args)

    def test_resolve_capture_file_uses_existing_knowledge_root_once(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            filename = "신규 입사자 요청서.txt"
            stored_name = unicodedata.normalize("NFD", filename)
            source = inbox / stored_name
            source.write_text("test only", encoding="utf-8")

            resolved = _resolve_capture_file(knowledge_root, None, filename)

            self.assertEqual(resolved, source.resolve())
            self.assertFalse((knowledge_root / "knowledge").exists())

    def test_run_cli_returns_structured_runtime_error_without_traceback(self):
        output = io.StringIO()
        with patch("circled_wiki.cli.__main__.main", side_effect=ValueError("safe failure")):
            with patch("sys.argv", ["circled-wiki", "record-task-step"]):
                with patch("sys.stdout", output):
                    status = run_cli()

        self.assertEqual(status, 2)
        payload = output.getvalue()
        self.assertIn('"error": "operation_failed"', payload)
        self.assertIn('"stage": "record-task-step"', payload)
        self.assertNotIn("Traceback", payload)

    def test_find_workflow_uses_named_request_option(self):
        output = io.StringIO()
        with patch("sys.argv", ["circled-wiki", "find-workflow", "--request", "test"]):
            with patch("circled_wiki.cli.__main__.KnowledgeService") as service_class:
                service_class.return_value.find_workflow.return_value = []
                with patch("sys.stdout", output):
                    status = run_cli()

        self.assertEqual(status, 0)
        service_class.return_value.find_workflow.assert_called_once_with("test")

    def test_run_cli_rejects_legacy_positional_argument(self):
        output = io.StringIO()
        with patch("sys.argv", ["circled-wiki", "find-workflow", "test"]):
            with patch("sys.stdout", output):
                status = run_cli()

        self.assertEqual(status, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error"], "operation_failed")
        self.assertEqual(payload["stage"], "find-workflow")
        self.assertIn("the following arguments are required: --request", payload["message"])

    def test_ingest_help_explains_required_inbox_routing(self):
        output = io.StringIO()
        with patch("sys.argv", ["circled-wiki", "ingest-evidence", "--help"]):
            with patch("sys.stdout", output):
                with self.assertRaises(SystemExit) as raised:
                    main()

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("inside knowledge/inbox/", output.getvalue())
        self.assertIn("capture-file", output.getvalue())

if __name__ == "__main__":
    unittest.main()
