import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.engineering.cli import main, run_product_cli, verify_release_source


class ProductCliTests(unittest.TestCase):
    def test_product_cli_is_registered_as_a_source_repository_command(self):
        project = Path(__file__).resolve().parents[2]
        metadata = (project / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(
            'circled-wiki-product = "circled_wiki.engineering.cli:run_product_cli"',
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
                with patch("circled_wiki.engineering.cli.intake_operational_issue") as intake:
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
        self.assertIn("--validator-passed", json.loads(output.getvalue())["message"])

    def test_deployment_command_explains_workspace_relative_receipt_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            output = io.StringIO()
            with patch(
                "sys.argv",
                [
                    "circled-wiki-product", "--workspace", str(workspace),
                    "record-deployment-receipt",
                    "--release-receipt", "workspace/receipts/releases/v1.json",
                    "--previous-release", "v0", "--target-ref", "team-wiki",
                    "--backup-ref", ".circled-wiki-backups/v0",
                ],
            ):
                with patch("sys.stdout", output):
                    status = run_product_cli()

        self.assertEqual(status, 2)
        message = json.loads(output.getvalue())["message"]
        self.assertIn("workspace/workspace/receipts", message)
        self.assertIn("receipts/releases/<release>.json", message)

    def test_release_source_check_requires_exact_clean_head(self):
        completed = lambda output: type("Completed", (), {"stdout": output})()
        with patch(
            "circled_wiki.engineering.cli.subprocess.run",
            side_effect=[completed("a" * 40 + "\n"), completed(""), completed("release commit\n")],
        ) as run:
            result = verify_release_source("a" * 40, Path("/product"))

        self.assertEqual(
            result,
            {"revision": "a" * 40, "subject": "release commit", "worktree_clean": True},
        )
        self.assertEqual(run.call_count, 3)

    def test_release_source_check_rejects_dirty_worktree(self):
        completed = lambda output: type("Completed", (), {"stdout": output})()
        with patch(
            "circled_wiki.engineering.cli.subprocess.run",
            side_effect=[completed("a" * 40 + "\n"), completed(" M source.py\n")],
        ):
            with self.assertRaisesRegex(ValueError, "worktree must be clean"):
                verify_release_source("a" * 40, Path("/product"))

    def test_prepare_release_rejects_dirty_source_before_building_manifest(self):
        output = io.StringIO()
        with patch(
            "sys.argv",
            [
                "circled-wiki-product", "prepare-release",
                "--manifest", "/tmp/release.json",
                "--source-revision", "a" * 40,
                "--validation", '{"unit":"passed","integration":"passed","repository_validator":"passed"}',
                "--verified-by", "release-preparer",
            ],
        ):
            with patch(
                "circled_wiki.engineering.cli.verify_release_source",
                side_effect=ValueError("release source worktree must be clean"),
            ):
                with patch("circled_wiki.engineering.cli.build_release_manifest") as build:
                    with patch("circled_wiki.engineering.cli.write_release_manifest") as write:
                        with patch("sys.stdout", output):
                            status = run_product_cli()

        self.assertEqual(status, 2)
        self.assertIn("worktree must be clean", json.loads(output.getvalue())["message"])
        build.assert_not_called()
        write.assert_not_called()

    def test_prepare_release_orders_gate_manifest_and_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            manifest_path = Path(directory) / "release.json"
            output = io.StringIO()
            source_check = {
                "revision": "a" * 40,
                "subject": "release commit",
                "worktree_clean": True,
            }
            manifest = {
                "schema_version": 1,
                "os_release": "v-test",
                "assets": {".circled-wiki/AGENT_ROUTER.md": "sha256:router"},
                "runtime_profiles": ["knowledge-query.md"],
                "router_checksum": "sha256:router",
            }
            events = []
            with patch(
                "sys.argv",
                [
                    "circled-wiki-product", "--workspace", str(workspace),
                    "prepare-release", "--manifest", str(manifest_path),
                    "--source-revision", "a" * 40,
                    "--validation", '{"unit":"passed","integration":"passed","repository_validator":"passed"}',
                    "--verified-by", "release-preparer",
                ],
            ):
                with patch(
                    "circled_wiki.engineering.cli.verify_release_source",
                    side_effect=lambda revision: events.append("verify") or source_check,
                ) as verify:
                    with patch(
                        "circled_wiki.engineering.cli.build_release_manifest",
                        side_effect=lambda root: events.append("build") or manifest,
                    ) as build:
                        with patch(
                            "circled_wiki.engineering.cli.write_release_manifest",
                            side_effect=lambda path, value: events.append("manifest") or {"path": str(path)},
                        ) as write:
                            with patch(
                                "circled_wiki.engineering.cli.record_release_receipt",
                                side_effect=lambda *args, **kwargs: events.append("receipt") or {"path": "receipt.json"},
                            ) as record:
                                with patch("sys.stdout", output):
                                    status = main()

            self.assertEqual(status, 0)
            self.assertEqual(events, ["verify", "build", "manifest", "receipt"])
            verify.assert_called_once_with("a" * 40)
            build.assert_called_once_with(Path.cwd())
            write.assert_called_once_with(manifest_path, manifest)
            self.assertEqual(record.call_args.kwargs["source_commit_check"], source_check)

    def test_prepare_release_rejects_failed_validation_before_manifest(self):
        output = io.StringIO()
        with patch(
            "sys.argv",
            [
                "circled-wiki-product", "prepare-release",
                "--manifest", "/tmp/release.json",
                "--source-revision", "a" * 40,
                "--validation", '{"unit":"failed","integration":"passed","repository_validator":"passed"}',
                "--verified-by", "release-preparer",
            ],
        ):
            with patch(
                "circled_wiki.engineering.cli.verify_release_source",
                return_value={"revision": "a" * 40, "subject": "release", "worktree_clean": True},
            ):
                with patch("circled_wiki.engineering.cli.build_release_manifest") as build:
                    with patch("circled_wiki.engineering.cli.write_release_manifest") as write:
                        with patch("sys.stdout", output):
                            status = run_product_cli()

        self.assertEqual(status, 2)
        self.assertIn("release validation must pass", json.loads(output.getvalue())["message"])
        build.assert_not_called()
        write.assert_not_called()

    def test_prepare_release_emits_manifest_and_receipt_after_clean_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "OPERATING_RULES.md").write_text("rules\n", encoding="utf-8")
            (source / "agent-rules").mkdir()
            (source / "agent-rules" / "knowledge-query.md").write_text("query\n", encoding="utf-8")
            (source / ".circled-wiki").mkdir()
            (source / ".circled-wiki" / "AGENT_ROUTER.md").write_text("router\n", encoding="utf-8")
            (source / ".circled-wiki" / "runtime").mkdir()
            (source / ".circled-wiki" / "runtime" / "pyproject.toml").write_text(
                "[project]\nname = 'circled-wiki-runtime'\n", encoding="utf-8"
            )
            runtime = source / "src" / "circled_wiki" / "runtime"
            runtime.mkdir(parents=True)
            (runtime / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=source, check=True)
            subprocess.run(["git", "config", "user.name", "Release Test"], cwd=source, check=True)
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(["git", "commit", "-qm", "release source"], cwd=source, check=True)
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=source, text=True
            ).strip()

            manifest_path = source / "workspace" / "release-manifests" / "candidate.json"
            output = io.StringIO()
            with patch("circled_wiki.engineering.cli.Path.cwd", return_value=source):
                with patch(
                    "sys.argv",
                    [
                        "circled-wiki-product", "--workspace", str(source / "workspace"),
                        "prepare-release", "--manifest", str(manifest_path),
                        "--source-revision", revision,
                        "--included-issue", "issue-1",
                        "--validation", '{"unit":"passed","integration":"passed","repository_validator":"passed"}',
                        "--verified-by", "release-preparer",
                    ],
                ):
                    with patch("sys.stdout", output):
                        status = main()

            self.assertEqual(status, 0)
            result = json.loads(output.getvalue())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            receipt_path = (
                source / "workspace" / "receipts" / "releases"
                / f"{manifest['os_release']}.json"
            )
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(result["manifest_path"], manifest_path.as_posix())
            self.assertEqual(result["release_id"], manifest["os_release"])
            self.assertEqual(receipt["source_revision"], revision)
            self.assertTrue(receipt["source_commit_check"]["worktree_clean"])
            self.assertEqual(receipt["release_id"], manifest["os_release"])
