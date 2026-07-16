import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from knowledge_os.core.bootstrap import MANIFEST_PATH, bootstrap_knowledge_root


ROOT = Path(__file__).resolve().parents[2]


class BootstrapKnowledgeRootTests(unittest.TestCase):
    @staticmethod
    def _make_source(root: Path, template_content: str) -> Path:
        root.mkdir()
        (root / "OPERATING_RULES.md").write_text("# Rules\n", encoding="utf-8")
        (root / "agent-rules").mkdir()
        for directory in ("templates", "policies", "schemas"):
            (root / ".knowledge-os" / directory).mkdir(parents=True)
        (root / ".knowledge-os" / "templates" / "runbook.md").write_text(
            template_content, encoding="utf-8"
        )
        return root

    def test_refuses_to_install_into_the_source_project(self):
        with self.assertRaisesRegex(ValueError, "separate project root"):
            bootstrap_knowledge_root(ROOT, ROOT, apply=True)

    def test_plan_then_apply_creates_only_operating_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            user_note = target / "existing-meeting-notes.md"
            user_note.write_text("사용자 원문", encoding="utf-8")

            plan = bootstrap_knowledge_root(target, ROOT)
            self.assertFalse(plan["applied"])
            self.assertGreater(plan["summary"]["create"], 0)
            self.assertTrue(all(
                item["path"].startswith(".knowledge-os/") for item in plan["actions"]
            ))
            self.assertFalse((target / MANIFEST_PATH).exists())
            self.assertEqual(user_note.read_text(encoding="utf-8"), "사용자 원문")

            applied = bootstrap_knowledge_root(target, ROOT, apply=True)
            self.assertTrue(applied["applied"])
            self.assertTrue((target / MANIFEST_PATH).is_file())
            self.assertTrue((target / ".knowledge-os" / "OPERATING_RULES.md").is_file())
            self.assertTrue((target / "knowledge" / "inbox").is_dir())
            self.assertTrue((target / ".knowledge-os" / "templates" / "runbook.md").is_file())
            self.assertTrue((target / ".knowledge-os" / "bin" / "knowledge-os.py").is_file())
            self.assertTrue((target / ".knowledge-os" / "runtime" / "knowledge_os" / "cli" / "__main__.py").is_file())
            self.assertTrue((target / ".knowledge-os" / "AGENT_BOOTSTRAP.md").is_file())
            agent_entrypoint = target / "AGENTS.md"
            self.assertTrue(agent_entrypoint.is_file())
            entrypoint_content = agent_entrypoint.read_text(encoding="utf-8")
            self.assertIn(".knowledge-os/AGENT_BOOTSTRAP.md", entrypoint_content)
            self.assertIn(".knowledge-os/OPERATING_RULES.md", entrypoint_content)
            self.assertNotIn("Run the local CLI", entrypoint_content)
            self.assertEqual(applied["agent_entrypoint_action"], "create")
            claude_entrypoint = target / "CLAUDE.md"
            claude_content = claude_entrypoint.read_text(encoding="utf-8")
            self.assertIn(".knowledge-os/AGENT_BOOTSTRAP.md", claude_content)
            self.assertIn(".knowledge-os/OPERATING_RULES.md", claude_content)
            self.assertNotIn("Run the local CLI", claude_content)
            self.assertEqual(applied["claude_entrypoint_action"], "create")
            self.assertFalse((target / ".knowledge-os-backups").exists())
            self.assertEqual(user_note.read_text(encoding="utf-8"), "사용자 원문")

    def test_installed_runtime_runs_the_cli_without_the_source_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_knowledge_root(target, ROOT, apply=True)
            launcher = target / ".knowledge-os" / "bin" / "knowledge-os.py"

            result = subprocess.run(
                [sys.executable, str(launcher), "validate"],
                cwd=Path(directory),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("invalid=0", result.stdout)

    def test_existing_agent_entrypoint_without_operating_rules_gets_an_append_only_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "AGENTS.md"
            entrypoint.write_text("# Existing team instructions\n", encoding="utf-8")

            report = bootstrap_knowledge_root(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["agent_entrypoint_action"], "append_operating_reference")
            self.assertTrue(content.startswith("# Existing team instructions\n"))
            self.assertIn(".knowledge-os/OPERATING_RULES.md", content)
            self.assertEqual(content.count("<!-- knowledge-os:agent-bootstrap -->"), 1)
            self.assertNotIn("Run the local CLI", content)

            repeated = bootstrap_knowledge_root(target, ROOT, apply=True)
            self.assertEqual(repeated["agent_entrypoint_action"], "preserve_existing")
            self.assertEqual(
                entrypoint.read_text(encoding="utf-8").count("<!-- knowledge-os:agent-bootstrap -->"), 1
            )

    def test_legacy_generated_agent_entrypoint_is_replaced_with_references_only(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "AGENTS.md"
            entrypoint.write_text(
                "# Knowledge OS Agent Entry Point\n\n"
                "This project uses Knowledge OS. Before taking action, read these files in order:\n",
                encoding="utf-8",
            )

            report = bootstrap_knowledge_root(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["agent_entrypoint_action"], "replace_legacy_generated_entrypoint")
            self.assertIn(".knowledge-os/AGENT_BOOTSTRAP.md", content)
            self.assertIn(".knowledge-os/OPERATING_RULES.md", content)
            self.assertNotIn("Before taking action", content)

    def test_existing_claude_entrypoint_gets_a_reference_without_overwriting_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "CLAUDE.md"
            entrypoint.write_text("# Team Claude preferences\n", encoding="utf-8")

            report = bootstrap_knowledge_root(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["claude_entrypoint_action"], "append_operating_reference")
            self.assertTrue(content.startswith("# Team Claude preferences\n"))
            self.assertIn(".knowledge-os/OPERATING_RULES.md", content)
            self.assertEqual(content.count("<!-- knowledge-os:claude-bootstrap -->"), 1)

    def test_modified_managed_asset_is_preserved_and_new_version_is_proposed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_knowledge_root(target, ROOT, apply=True)
            template = target / ".knowledge-os" / "templates" / "runbook.md"
            original = template.read_text(encoding="utf-8")
            template.write_text(original + "\n사용자 조직 규칙\n", encoding="utf-8")

            report = bootstrap_knowledge_root(target, ROOT, apply=True)
            self.assertGreater(report["summary"]["preserve_and_propose"], 0)
            self.assertIn("사용자 조직 규칙", template.read_text(encoding="utf-8"))
            proposal = target / ".knowledge-os" / "proposals" / ".knowledge-os__templates__runbook.md.new"
            self.assertTrue(proposal.is_file())
            self.assertEqual(proposal.read_text(encoding="utf-8"), original)

    def test_upgrade_never_changes_existing_knowledge_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            source = target / "knowledge" / "legacy" / "procedure.md"
            source.parent.mkdir(parents=True)
            source.write_text("조직의 기존 원문", encoding="utf-8")
            before = source.read_bytes()

            bootstrap_knowledge_root(target, ROOT, apply=True)
            bootstrap_knowledge_root(target, ROOT, apply=True)

            self.assertEqual(source.read_bytes(), before)
            manifest = (target / MANIFEST_PATH).read_text(encoding="utf-8")
            self.assertNotIn("knowledge/", manifest)

    def test_upgrade_preserves_local_operational_issue_records(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_knowledge_root(target, ROOT, apply=True)
            issue = target / ".knowledge-os" / "issues" / "issue-user-feedback.md"
            issue.write_text("# User feedback\n", encoding="utf-8")
            original_rules = target / ".knowledge-os" / "OPERATING_RULES.md"
            original_rules.write_text(
                original_rules.read_text(encoding="utf-8") + "\nLocal team note\n",
                encoding="utf-8",
            )

            report = bootstrap_knowledge_root(target, ROOT, apply=True)

            self.assertTrue(report["backup_path"])
            self.assertEqual(issue.read_text(encoding="utf-8"), "# User feedback\n")
            self.assertTrue(
                (Path(report["backup_path"]) / "issues" / "issue-user-feedback.md").is_file()
            )

    def test_upgrade_backs_up_the_previous_os_version_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._make_source(root / "source", "version 1\n")
            target = root / "target"
            bootstrap_knowledge_root(target, source, apply=True)
            knowledge_file = target / "knowledge" / "private-note.md"
            knowledge_file.write_text("preserve me", encoding="utf-8")
            old_manifest = json.loads((target / MANIFEST_PATH).read_text(encoding="utf-8"))

            (source / ".knowledge-os" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )
            plan = bootstrap_knowledge_root(target, source)
            self.assertTrue(plan["backup_required"])
            self.assertIsNone(plan["backup_path"])

            report = bootstrap_knowledge_root(target, source, apply=True)
            backup = Path(report["backup_path"])
            self.assertTrue(backup.is_dir())
            self.assertTrue(backup.name.startswith(old_manifest["os_release"] + "-"))
            self.assertEqual(
                (backup / "templates" / "runbook.md").read_text(encoding="utf-8"),
                "version 1\n",
            )
            self.assertEqual(
                (target / ".knowledge-os" / "templates" / "runbook.md").read_text(
                    encoding="utf-8"
                ),
                "version 2\n",
            )
            self.assertEqual(knowledge_file.read_text(encoding="utf-8"), "preserve me")
            new_manifest = json.loads((target / MANIFEST_PATH).read_text(encoding="utf-8"))
            resolved_target = Path(report["target"])
            self.assertEqual(
                new_manifest["last_backup"], backup.relative_to(resolved_target).as_posix()
            )

            backups_before = sorted((target / ".knowledge-os-backups").iterdir())
            no_op = bootstrap_knowledge_root(target, source, apply=True)
            self.assertFalse(no_op["backup_required"])
            self.assertIsNone(no_op["backup_path"])
            self.assertEqual(sorted((target / ".knowledge-os-backups").iterdir()), backups_before)

    def test_backup_failure_stops_upgrade_before_existing_os_is_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._make_source(root / "source", "version 1\n")
            target = root / "target"
            bootstrap_knowledge_root(target, source, apply=True)
            installed = target / ".knowledge-os" / "templates" / "runbook.md"
            manifest = target / MANIFEST_PATH
            before_file = installed.read_bytes()
            before_manifest = manifest.read_bytes()
            (source / ".knowledge-os" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )

            with patch(
                "knowledge_os.core.bootstrap.shutil.copytree",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaisesRegex(RuntimeError, "stopped before modifying"):
                    bootstrap_knowledge_root(target, source, apply=True)

            self.assertEqual(installed.read_bytes(), before_file)
            self.assertEqual(manifest.read_bytes(), before_manifest)
