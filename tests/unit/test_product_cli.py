import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.product_cli import main, run_product_cli


class ProductCliTests(unittest.TestCase):
    def test_product_cli_is_registered_as_a_source_repository_command(self):
        project = Path(__file__).resolve().parents[2]
        metadata = (project / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'circled-wiki-product = "circled_wiki.product_cli:run_product_cli"',
            metadata,
        )

    def test_intake_command_routes_explicit_arguments_to_the_product_core(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "circled-wiki-product", "--workspace", str(workspace),
                    "intake-operational-issue", "--source-project", "/safe/source",
                    "--project-ref", "team-wiki", "--issue", "issue-1",
                    "--requested-by", "user-1", "--moved-by", "agent-1",
                ],
            ):
                with patch("circled_wiki.product_cli.intake_operational_issue") as intake:
                    intake.return_value = {"status": "pending_review"}
                    with patch("sys.stdout", output):
                        status = main()

            self.assertEqual(status, 0)
            self.assertEqual(json.loads(output.getvalue())["status"], "pending_review")
            intake.assert_called_once_with(
                workspace.resolve(),
                Path("/safe/source"),
                project_ref="team-wiki",
                issue_ref="issue-1",
                requested_by="user-1",
                moved_by="agent-1",
            )

    def test_archive_command_rejects_paths_outside_the_product_workspace(self):
        output = io.StringIO()
        with patch(
            "sys.argv",
            [
                "circled-wiki-product", "--workspace", "/safe/workspace",
                "archive-workspace-issue", "--item", "/outside/item.md",
                "--archived-by", "agent", "--reason", "done",
                "--restore-condition", "recurrence",
            ],
        ):
            with patch("sys.stdout", output):
                status = run_product_cli()

        payload = json.loads(output.getvalue())
        self.assertEqual(status, 2)
        self.assertEqual(payload["error"], "product_operation_failed")
        self.assertIn("below the Product Workspace", payload["message"])

    def test_verification_command_requires_all_runtime_preservation_attestations(self):
        output = io.StringIO()
        with patch(
            "sys.argv",
            [
                "circled-wiki-product", "record-verification-receipt",
                "--deployment-receipt", "receipts/deployments/team/v1.json",
                "--expected-release", "v1", "--observed-release", "v1",
                "--verified-by", "reviewer", "--implemented-by", "implementer",
            ],
        ):
            with patch("sys.stdout", output):
                status = run_product_cli()

        self.assertEqual(status, 2)
        self.assertIn("--preflight-ready", json.loads(output.getvalue())["message"])
