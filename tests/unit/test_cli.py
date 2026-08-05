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

    def test_direct_ingest_command_is_not_exposed(self):
        output = io.StringIO()
        with patch("sys.argv", ["circled-wiki", "ingest-evidence"]):
            with patch("sys.stdout", output):
                status = run_cli()

        self.assertEqual(status, 2)
        self.assertIn("invalid choice", output.getvalue())

    def test_quarantine_and_disposal_commands_use_service(self):
        intake_id = "inbox://acme/slack/11111111-1111-1111-1111-111111111111"
        output = io.StringIO()
        with patch("sys.argv", [
            "circled-wiki", "quarantine-inbox-item", "--intake", intake_id,
            "--classifier", "slack-filter", "--rule-version", "v1", "--reason", "non-business",
        ]):
            with patch("circled_wiki.cli.__main__.KnowledgeService") as service_class:
                service_class.return_value.quarantine_inbox_item.return_value = {"status": "pending_disposal_review"}
                with patch("sys.stdout", output):
                    self.assertEqual(run_cli(), 0)
        service_class.return_value.quarantine_inbox_item.assert_called_once_with(
            intake_id, classifier="slack-filter", rule_version="v1", reason="non-business",
        )

    def test_apply_automatic_curation_update_cli_uses_append_service_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            body = Path(directory) / "delta.md"
            body.write_text("## New section\n", encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", [
                "circled-wiki", "apply-automatic-curation-update",
                "--evidence", "evidence/test",
                "--existing-bundle", "bundle/test",
                "--update-mode", "append",
                "--body-file", str(body),
                "--actor", "curator",
                "--curation-receipt", "curation://test",
                "--security-receipt", "security://test",
            ]):
                with patch("circled_wiki.cli.__main__.KnowledgeService") as service_class:
                    service_class.return_value.apply_automatic_curation_append.return_value = {
                        "action": "updated", "queue_completed": True,
                    }
                    with patch("sys.stdout", output):
                        status = run_cli()

            self.assertEqual(status, 0)
            service_class.return_value.apply_automatic_curation_append.assert_called_once_with(
                "evidence/test", existing_bundle_id="bundle/test", body="## New section\n",
                actor="curator", curation_receipt="curation://test",
                security_receipt="security://test", update_mode="append",
            )

    def test_verify_curation_commit_cli_returns_gate_status(self):
        output = io.StringIO()
        with patch("sys.argv", ["circled-wiki", "verify-curation-commit"]):
            with patch("circled_wiki.cli.__main__.KnowledgeService") as service_class:
                service_class.return_value.verify_curation_commit.return_value = {
                    "passed": False, "status": "blocked", "missing_archive": ["archive.md"],
                }
                with patch("sys.stdout", output):
                    status = run_cli()

        self.assertEqual(status, 1)
        payload = json.loads(output.getvalue())
        self.assertEqual(payload["status"], "blocked")

if __name__ == "__main__":
    unittest.main()
