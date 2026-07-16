import tempfile
import unittest
import unicodedata
import io
import json
from pathlib import Path
from unittest.mock import patch

from knowledge_os.cli.__main__ import _resolve_capture_file, run_cli


class CliTests(unittest.TestCase):
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
        with patch("knowledge_os.cli.__main__.main", side_effect=ValueError("safe failure")):
            with patch("sys.argv", ["knowledge-os", "record-task-step"]):
                with patch("sys.stdout", output):
                    status = run_cli()

        self.assertEqual(status, 2)
        payload = output.getvalue()
        self.assertIn('"error": "operation_failed"', payload)
        self.assertIn('"stage": "record-task-step"', payload)
        self.assertNotIn("Traceback", payload)

    def test_find_workflow_uses_named_request_option(self):
        output = io.StringIO()
        with patch("sys.argv", ["knowledge-os", "find-workflow", "--request", "test"]):
            with patch("knowledge_os.cli.__main__.KnowledgeService") as service_class:
                service_class.return_value.find_workflow.return_value = []
                with patch("sys.stdout", output):
                    status = run_cli()

        self.assertEqual(status, 0)
        service_class.return_value.find_workflow.assert_called_once_with("test")

    def test_run_cli_rejects_legacy_positional_argument(self):
        output = io.StringIO()
        with patch("sys.argv", ["knowledge-os", "find-workflow", "test"]):
            with patch("sys.stdout", output):
                status = run_cli()

        self.assertEqual(status, 2)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["error"], "operation_failed")
        self.assertEqual(payload["stage"], "find-workflow")
        self.assertIn("the following arguments are required: --request", payload["message"])


if __name__ == "__main__":
    unittest.main()
