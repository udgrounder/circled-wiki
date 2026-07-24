import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.bootstrap import (
    MANIFEST_PATH,
    _checksum,
    bootstrap_circled_wiki,
    initialize_operational_workspace,
    rollback_control_plane,
)


ROOT = Path(__file__).resolve().parents[2]


class BootstrapKnowledgeRootTests(unittest.TestCase):
    @staticmethod
    def _make_source(root: Path, template_content: str) -> Path:
        root.mkdir()
        (root / "OPERATING_RULES.md").write_text("# Rules\n", encoding="utf-8")
        (root / "agent-rules").mkdir()
        (root / ".circled-wiki").mkdir()
        (root / ".circled-wiki" / "AGENT_ROUTER.md").write_text(
            "# Runtime Router\n", encoding="utf-8"
        )
        for directory in ("templates", "policies", "schemas"):
            (root / ".circled-wiki" / directory).mkdir(parents=True)
        (root / ".circled-wiki" / "templates" / "runbook.md").write_text(
            template_content, encoding="utf-8"
        )
        (root / ".circled-wiki" / "templates" / ".gitignore").write_text(
            "# BEGIN circled-wiki:generated-artifacts\n"
            "__pycache__/\n"
            "# END circled-wiki:generated-artifacts\n",
            encoding="utf-8",
        )
        return root

    def test_refuses_to_install_into_the_source_project(self):
        with self.assertRaisesRegex(ValueError, "separate project root"):
            bootstrap_circled_wiki(ROOT, ROOT, apply=True)

    def test_plan_then_apply_creates_only_operating_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            user_note = target / "existing-meeting-notes.md"
            user_note.write_text("사용자 원문", encoding="utf-8")

            plan = bootstrap_circled_wiki(target, ROOT)
            self.assertFalse(plan["applied"])
            self.assertGreater(plan["summary"]["create"], 0)
            self.assertTrue(
                all(item["path"].startswith(".circled-wiki/") for item in plan["actions"])
            )
            self.assertFalse((target / MANIFEST_PATH).exists())
            self.assertEqual(user_note.read_text(encoding="utf-8"), "사용자 원문")

            applied = bootstrap_circled_wiki(target, ROOT, apply=True)
            self.assertTrue(applied["applied"])
            self.assertTrue((target / MANIFEST_PATH).is_file())
            self.assertTrue((target / ".circled-wiki" / "OPERATING_RULES.md").is_file())
            installed_rules = (target / ".circled-wiki" / "OPERATING_RULES.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("RB-KNW-022", installed_rules)
            self.assertIn("RB-KNW-023", installed_rules)
            self.assertIn(".circled-wiki/config.yaml", installed_rules)
            installed_profiles = {
                path.name
                for path in (target / ".circled-wiki" / "agent-rules").glob("*.md")
            }
            self.assertNotIn("repository-engineering.md", installed_profiles)
            self.assertNotIn("bootstrap-circled-wiki.md", installed_profiles)
            self.assertIn("system-observation.md", installed_profiles)
            self.assertTrue((target / "knowledge" / "inbox").is_dir())
            self.assertTrue((target / "workspace").is_dir())
            self.assertTrue((target / ".circled-wiki" / "templates" / "runbook.md").is_file())
            self.assertTrue((target / ".circled-wiki" / "templates" / ".gitignore").is_file())
            self.assertTrue((target / ".circled-wiki" / "bin" / "circled-wiki.py").is_file())
            self.assertTrue((target / ".circled-wiki" / "runtime" / "circled_wiki" / "cli" / "__main__.py").is_file())
            self.assertFalse(
                (
                    target
                    / ".circled-wiki"
                    / "runtime"
                    / "circled_wiki"
                    / "core"
                    / "issue_workspace.py"
                ).exists()
            )
            self.assertFalse(
                (target / ".circled-wiki" / "runtime" / "circled_wiki" / "product_cli.py").exists()
            )
            self.assertTrue((target / ".circled-wiki" / "AGENT_BOOTSTRAP.md").is_file())
            self.assertTrue((target / ".circled-wiki" / "AGENT_ROUTER.md").is_file())
            self.assertTrue((target / ".circled-wiki" / "AUTONOMOUS_AGENT_STARTUP.md").is_file())
            self.assertTrue((target / ".circled-wiki" / "GRAPHIFY.md").is_file())
            self.assertTrue((target / ".circled-wiki" / "config.yaml").is_file())
            agent_entrypoint = target / "AGENTS.md"
            self.assertTrue(agent_entrypoint.is_file())
            entrypoint_content = agent_entrypoint.read_text(encoding="utf-8")
            self.assertIn(".circled-wiki/AGENT_BOOTSTRAP.md", entrypoint_content)
            self.assertIn(".circled-wiki/AGENT_ROUTER.md", entrypoint_content)
            self.assertIn(".circled-wiki/OPERATING_RULES.md", entrypoint_content)
            self.assertNotIn("Run the local CLI", entrypoint_content)
            self.assertEqual(applied["agent_entrypoint_action"], "create")
            claude_entrypoint = target / "CLAUDE.md"
            claude_content = claude_entrypoint.read_text(encoding="utf-8")
            self.assertIn(".circled-wiki/AGENT_BOOTSTRAP.md", claude_content)
            self.assertIn(".circled-wiki/AGENT_ROUTER.md", claude_content)
            self.assertIn(".circled-wiki/OPERATING_RULES.md", claude_content)
            self.assertNotIn("Run the local CLI", claude_content)
            self.assertEqual(applied["claude_entrypoint_action"], "create")
            hermes_content = (target / "HERMES.md").read_text(encoding="utf-8")
            self.assertIn(".circled-wiki/AUTONOMOUS_AGENT_STARTUP.md", hermes_content)
            self.assertEqual(applied["hermes_entrypoint_action"], "create")
            self.assertEqual(applied["gitignore_action"], "create")
            gitignore = (target / ".gitignore").read_text(encoding="utf-8")
            self.assertIn("# BEGIN circled-wiki:generated-artifacts", gitignore)
            self.assertIn("# END circled-wiki:generated-artifacts", gitignore)
            self.assertIn(".circled-wiki-backups/", gitignore)
            self.assertIn("**/.obsidian/graph.json", gitignore)
            self.assertEqual(applied["configuration_action"], "create")
            self.assertEqual(applied["configuration"]["organization_id"], "example-org")
            installed_config = (target / ".circled-wiki" / "config.yaml").read_text(
                encoding="utf-8"
            )
            self.assertIn("default_owners: []", installed_config)
            self.assertIn("allowed_paths:\n  - knowledge", installed_config)
            self.assertFalse((target / ".circled-wiki-backups").exists())
            manifest = (target / MANIFEST_PATH).read_text(encoding="utf-8")
            self.assertNotIn('"workspace/', manifest)
            manifest_payload = json.loads(manifest)
            self.assertIn("system-observation.md", manifest_payload["runtime_profiles"])
            self.assertNotIn("repository-engineering.md", manifest_payload["runtime_profiles"])
            self.assertEqual(
                manifest_payload["router_checksum"],
                manifest_payload["assets"][".circled-wiki/AGENT_ROUTER.md"],
            )
            self.assertEqual(user_note.read_text(encoding="utf-8"), "사용자 원문")

    def test_existing_gitignore_gets_append_only_generated_artifact_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            gitignore = target / ".gitignore"
            gitignore.write_text("team-secret-output/\n", encoding="utf-8")

            first = bootstrap_circled_wiki(target, ROOT, apply=True)
            first_content = gitignore.read_text(encoding="utf-8")
            second = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertEqual(first["gitignore_action"], "append_generated_artifacts")
            self.assertEqual(second["gitignore_action"], "preserve_existing")
            self.assertTrue(first_content.startswith("team-secret-output/\n"))
            self.assertEqual(first_content.count("# BEGIN circled-wiki:generated-artifacts"), 1)
            self.assertEqual(first_content.count("# END circled-wiki:generated-artifacts"), 1)
            self.assertEqual(gitignore.read_text(encoding="utf-8"), first_content)

            subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
            generated = (
                target / "src" / "circled_wiki" / "__pycache__" / "module.cpython-311.pyc"
            )
            generated.parent.mkdir(parents=True)
            generated.write_bytes(b"cache")
            backup = target / ".circled-wiki-backups" / "release" / "manifest.json"
            backup.parent.mkdir(parents=True)
            backup.write_text("{}", encoding="utf-8")
            graph = target / "knowledge" / ".obsidian" / "graph.json"
            graph.parent.mkdir(parents=True)
            graph.write_text("{}", encoding="utf-8")

            ignored = subprocess.run(
                ["git", "-C", str(target), "check-ignore", str(generated), str(backup), str(graph)],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(ignored.returncode, 0, ignored.stderr)
            self.assertEqual(len(ignored.stdout.splitlines()), 3)

    def test_gitignore_upgrade_replaces_only_the_managed_region_when_lines_differ(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            bootstrap_circled_wiki(target, ROOT, apply=True)
            gitignore = target / ".gitignore"
            content = gitignore.read_text(encoding="utf-8")
            content = content.replace(".temp/\n", "obsolete-generated-output/\n")
            gitignore.write_text("team-before/\n" + content + "team-after/\n", encoding="utf-8")

            plan = bootstrap_circled_wiki(target, ROOT)
            applied = bootstrap_circled_wiki(target, ROOT, apply=True)
            updated = gitignore.read_text(encoding="utf-8")

            self.assertEqual(plan["gitignore_action"], "replace_generated_artifacts")
            self.assertEqual(plan["gitignore_missing_patterns"], [".temp/"])
            self.assertEqual(applied["gitignore_action"], "replace_generated_artifacts")
            self.assertTrue(updated.startswith("team-before/\n"))
            self.assertTrue(updated.endswith("team-after/\n"))
            self.assertIn(".temp/", updated)
            self.assertNotIn("obsolete-generated-output/", updated)
            self.assertEqual(updated.count("# BEGIN circled-wiki:generated-artifacts"), 1)
            self.assertEqual(updated.count("# END circled-wiki:generated-artifacts"), 1)

    def test_gitignore_upgrade_migrates_the_legacy_single_marker_block(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            gitignore = target / ".gitignore"
            gitignore.write_text(
                "team-before/\n\n"
                "# circled-wiki:generated-artifacts\n"
                "__pycache__/\n"
                "*.pyc\n\n"
                "team-after/\n",
                encoding="utf-8",
            )

            report = bootstrap_circled_wiki(target, ROOT, apply=True)
            updated = gitignore.read_text(encoding="utf-8")

            self.assertEqual(report["gitignore_action"], "migrate_legacy_generated_artifacts")
            self.assertIn("*.py[cod]", report["gitignore_missing_patterns"])
            self.assertTrue(updated.startswith("team-before/\n"))
            self.assertTrue(updated.endswith("team-after/\n"))
            self.assertNotIn("# circled-wiki:generated-artifacts\n", updated)
            self.assertIn("# BEGIN circled-wiki:generated-artifacts", updated)
            self.assertIn("# END circled-wiki:generated-artifacts", updated)

    def test_gitignore_expectations_are_read_from_the_template_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._make_source(root / "source", "version 1\n")
            target = root / "target"
            bootstrap_circled_wiki(target, source, apply=True)
            template = source / ".circled-wiki" / "templates" / ".gitignore"
            template.write_text(
                template.read_text(encoding="utf-8").replace(
                    "# END circled-wiki:generated-artifacts",
                    "custom-generated-output/\n# END circled-wiki:generated-artifacts",
                ),
                encoding="utf-8",
            )

            plan = bootstrap_circled_wiki(target, source)
            applied = bootstrap_circled_wiki(target, source, apply=True)

            self.assertEqual(plan["gitignore_action"], "replace_generated_artifacts")
            self.assertEqual(plan["gitignore_missing_patterns"], ["custom-generated-output/"])
            self.assertEqual(applied["gitignore_action"], "replace_generated_artifacts")
            self.assertIn(
                "custom-generated-output/",
                (target / ".gitignore").read_text(encoding="utf-8"),
            )

    def test_first_install_writes_custom_identity_and_preserves_it_on_upgrade(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(
                target,
                ROOT,
                apply=True,
                organization_id="acme",
                organization_name="Acme Corporation",
                operator_agent="atlas",
                graphify_enabled=True,
            )
            config = (target / ".circled-wiki" / "config.yaml").read_text(encoding="utf-8")
            self.assertIn("id: acme", config)
            self.assertIn("name: Acme Corporation", config)
            self.assertIn("operator: atlas", config)
            self.assertIn("enabled: true", config)

            repeated = bootstrap_circled_wiki(
                target,
                ROOT,
                apply=True,
                organization_id="wrong",
                organization_name="Wrong",
                operator_agent="wrong",
            )
            self.assertEqual(repeated["configuration_action"], "preserve_existing")
            self.assertEqual(repeated["configuration"]["organization_id"], "acme")
            self.assertEqual(
                (target / ".circled-wiki" / "config.yaml").read_text(encoding="utf-8"),
                config,
            )

    def test_installed_runtime_runs_the_cli_without_the_source_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            launcher = target / ".circled-wiki" / "bin" / "circled-wiki.py"

            result = subprocess.run(
                [sys.executable, str(launcher), "validate"],
                cwd=Path(directory),
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("invalid=0", result.stdout)

    def test_preflight_reports_enabled_graphify_as_external_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True, graphify_enabled=True)
            launcher = target / ".circled-wiki" / "bin" / "circled-wiki.py"

            result = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(payload["graphify"]["enabled"])
            self.assertFalse(payload["graphify"]["ready"])
            self.assertIn("Graphify", payload["next_action"])

    def test_preflight_reports_release_and_blocks_runtime_checksum_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            launcher = target / ".circled-wiki" / "bin" / "circled-wiki.py"

            clean = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            clean_payload = json.loads(clean.stdout)
            manifest = json.loads((target / MANIFEST_PATH).read_text(encoding="utf-8"))

            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertTrue(clean_payload["ready"])
            self.assertTrue(clean_payload["runtime"]["compatible"])
            self.assertTrue(clean_payload["control_plane"]["compatible"])
            self.assertEqual(clean_payload["control_plane"]["pending_proposals"], [])
            self.assertEqual(clean_payload["control_plane"]["reference_errors"], [])
            self.assertEqual(clean_payload["runtime"]["release_id"], manifest["os_release"])
            self.assertTrue(clean_payload["runtime"]["executing_canonical_runtime"])
            self.assertGreater(clean_payload["runtime"]["runtime_asset_count"], 0)

            drifted = target / ".circled-wiki" / "runtime" / "circled_wiki" / "config" / "settings.py"
            original_runtime_content = drifted.read_text(encoding="utf-8")
            drifted.write_text(
                original_runtime_content + "\n# local drift\n",
                encoding="utf-8",
            )
            blocked = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            blocked_payload = json.loads(blocked.stdout)

            self.assertEqual(blocked.returncode, 1)
            self.assertFalse(blocked_payload["ready"])
            self.assertFalse(blocked_payload["runtime"]["compatible"])
            self.assertIn(
                ".circled-wiki/runtime/circled_wiki/config/settings.py",
                blocked_payload["runtime"]["mismatched_assets"],
            )
            self.assertIn("canonical Circled Wiki runtime", blocked_payload["next_action"])

            drifted.write_text(original_runtime_content, encoding="utf-8")
            (target / "src" / "circled_wiki").mkdir(parents=True)
            duplicate = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            duplicate_payload = json.loads(duplicate.stdout)

            self.assertEqual(duplicate.returncode, 1)
            self.assertTrue(duplicate_payload["runtime"]["multiple_runtime_candidates"])
            self.assertFalse(duplicate_payload["runtime"]["compatible"])

    def test_preflight_blocks_pending_control_plane_proposal_until_adopted(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            startup = target / ".circled-wiki" / "AUTONOMOUS_AGENT_STARTUP.md"
            startup.write_text(
                startup.read_text(encoding="utf-8") + "\nLocal override.\n",
                encoding="utf-8",
            )

            upgraded = bootstrap_circled_wiki(target, ROOT, apply=True)
            launcher = target / ".circled-wiki" / "bin" / "circled-wiki.py"
            blocked = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            blocked_payload = json.loads(blocked.stdout)

            self.assertEqual(blocked.returncode, 1)
            self.assertFalse(blocked_payload["ready"])
            self.assertFalse(blocked_payload["control_plane"]["compatible"])
            self.assertEqual(len(upgraded["pending_proposals"]), 1)
            self.assertEqual(
                upgraded["pending_proposals"][0]["path"],
                ".circled-wiki/AUTONOMOUS_AGENT_STARTUP.md",
            )
            self.assertIn(
                "pending Control Plane proposals",
                blocked_payload["next_action"],
            )

            proposal = target / upgraded["pending_proposals"][0]["proposal"]
            startup.write_bytes(proposal.read_bytes())
            resolved = bootstrap_circled_wiki(target, ROOT, apply=True)
            ready = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            ready_payload = json.loads(ready.stdout)

            startup_action = next(
                item["action"]
                for item in resolved["actions"]
                if item["path"] == ".circled-wiki/AUTONOMOUS_AGENT_STARTUP.md"
            )
            self.assertEqual(startup_action, "unchanged")
            self.assertEqual(resolved["pending_proposals"], [])
            self.assertEqual(ready.returncode, 0, ready.stderr)
            self.assertTrue(ready_payload["control_plane"]["compatible"])

    def test_preflight_smoke_checks_agent_router_and_launcher_references(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            hermes = target / "HERMES.md"
            hermes.write_text(
                hermes.read_text(encoding="utf-8").replace(
                    ".circled-wiki/AGENT_ROUTER.md",
                    ".circled-wiki/missing-router.md",
                ),
                encoding="utf-8",
            )
            launcher = target / ".circled-wiki" / "bin" / "circled-wiki.py"

            result = subprocess.run(
                [sys.executable, str(launcher), "operational-preflight"],
                cwd=target,
                capture_output=True,
                text=True,
                check=False,
            )
            payload = json.loads(result.stdout)

            self.assertEqual(result.returncode, 1)
            self.assertFalse(payload["ready"])
            self.assertIn(
                "HERMES.md: missing reference to .circled-wiki/AGENT_ROUTER.md",
                payload["control_plane"]["reference_errors"],
            )
            self.assertIn(
                "repair Control Plane startup, Router, or launcher references",
                payload["next_action"],
            )

    def test_existing_agent_entrypoint_without_operating_rules_gets_an_append_only_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "AGENTS.md"
            entrypoint.write_text("# Existing team instructions\n", encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["agent_entrypoint_action"], "append_operating_reference")
            self.assertTrue(content.startswith("# Existing team instructions\n"))
            self.assertIn(".circled-wiki/OPERATING_RULES.md", content)
            self.assertEqual(content.count("<!-- circled-wiki:agent-bootstrap -->"), 1)
            self.assertNotIn("Run the local CLI", content)

            repeated = bootstrap_circled_wiki(target, ROOT, apply=True)
            self.assertEqual(repeated["agent_entrypoint_action"], "preserve_existing")
            self.assertEqual(
                entrypoint.read_text(encoding="utf-8").count("<!-- circled-wiki:agent-bootstrap -->"), 1
            )

    def test_legacy_generated_agent_entrypoint_is_replaced_with_references_only(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "AGENTS.md"
            entrypoint.write_text(
                "# Circled Wiki Agent Entry Point\n\n"
                "This project uses Circled Wiki. Before taking action, read these files in order:\n",
                encoding="utf-8",
            )

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["agent_entrypoint_action"], "replace_legacy_generated_entrypoint")
            self.assertIn(".circled-wiki/AGENT_BOOTSTRAP.md", content)
            self.assertIn(".circled-wiki/OPERATING_RULES.md", content)
            self.assertNotIn("Before taking action", content)

    def test_existing_claude_entrypoint_gets_a_reference_without_overwriting_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            target.mkdir()
            entrypoint = target / "CLAUDE.md"
            entrypoint.write_text("# Team Claude preferences\n", encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            content = entrypoint.read_text(encoding="utf-8")
            self.assertEqual(report["claude_entrypoint_action"], "append_operating_reference")
            self.assertTrue(content.startswith("# Team Claude preferences\n"))
            self.assertIn(".circled-wiki/OPERATING_RULES.md", content)
            self.assertEqual(content.count("<!-- circled-wiki:claude-bootstrap -->"), 1)

    def test_modified_managed_asset_is_preserved_and_new_version_is_proposed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            template = target / ".circled-wiki" / "templates" / "runbook.md"
            original = template.read_text(encoding="utf-8")
            template.write_text(original + "\n사용자 조직 규칙\n", encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)
            self.assertGreater(report["summary"]["preserve_and_propose"], 0)
            self.assertIn("사용자 조직 규칙", template.read_text(encoding="utf-8"))
            proposal = target / ".circled-wiki" / "proposals" / ".circled-wiki__templates__runbook.md.new"
            self.assertTrue(proposal.is_file())
            self.assertEqual(proposal.read_text(encoding="utf-8"), original)

    def test_unrecorded_identical_legacy_asset_is_adopted_and_next_upgrade_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            manifest_path = target / MANIFEST_PATH
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            legacy_asset = ".circled-wiki/templates/runbook.md"
            manifest["assets"].pop(legacy_asset)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            adopted = bootstrap_circled_wiki(target, ROOT, apply=True)

            action = next(item["action"] for item in adopted["actions"] if item["path"] == legacy_asset)
            self.assertEqual(action, "adopt")
            updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertIn(legacy_asset, updated_manifest["assets"])
            repeated = bootstrap_circled_wiki(target, ROOT, apply=True)
            repeated_action = next(item["action"] for item in repeated["actions"] if item["path"] == legacy_asset)
            self.assertEqual(repeated_action, "unchanged")

    def test_modified_runtime_module_is_upgraded_to_keep_runtime_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            settings = target / ".circled-wiki" / "runtime" / "circled_wiki" / "config" / "settings.py"
            settings.write_text(settings.read_text(encoding="utf-8") + "\n# obsolete local runtime edit\n", encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            action = next(item["action"] for item in report["actions"] if item["path"].endswith("config/settings.py"))
            self.assertEqual(action, "upgrade")
            self.assertNotIn("obsolete local runtime edit", settings.read_text(encoding="utf-8"))

    def test_portable_cli_is_executable_after_install(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-knowledge"
            bootstrap_circled_wiki(target, ROOT, apply=True)

            cli = target / ".circled-wiki" / "bin" / "circled-wiki.py"
            self.assertTrue(cli.stat().st_mode & 0o111)
            self.assertTrue(cli.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3\n"))
            completed = subprocess.run(
                [str(cli), "validate"], cwd=target, text=True,
                capture_output=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_upgrade_never_changes_existing_knowledge_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            source = target / "knowledge" / "legacy" / "procedure.md"
            source.parent.mkdir(parents=True)
            source.write_text("조직의 기존 원문", encoding="utf-8")
            before = source.read_bytes()

            bootstrap_circled_wiki(target, ROOT, apply=True)
            bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertEqual(source.read_bytes(), before)
            manifest = (target / MANIFEST_PATH).read_text(encoding="utf-8")
            self.assertNotIn("knowledge/", manifest)

    def test_upgrade_never_changes_or_backs_up_existing_workspace_content(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            workspace_file = target / "workspace" / "agent-log" / "state.bin"
            workspace_file.parent.mkdir(parents=True)
            workspace_file.write_bytes(b"\x00user-owned-state\xff")
            before = workspace_file.read_bytes()
            managed_rules = target / ".circled-wiki" / "OPERATING_RULES.md"
            managed_rules.write_text(
                managed_rules.read_text(encoding="utf-8") + "\nlocal drift\n",
                encoding="utf-8",
            )

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertEqual(workspace_file.read_bytes(), before)
            self.assertNotIn("workspace/", (target / MANIFEST_PATH).read_text(encoding="utf-8"))
            self.assertTrue(report["backup_path"])
            self.assertFalse((Path(report["backup_path"]) / "workspace").exists())

    def test_existing_install_requires_explicit_workspace_initialization(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            workspace = target / "workspace"
            workspace.rmdir()

            upgrade = bootstrap_circled_wiki(target, ROOT, apply=True)
            plan = initialize_operational_workspace(target)
            applied = initialize_operational_workspace(target, apply=True)

            self.assertEqual(upgrade["workspace_action"], "preserve")
            self.assertFalse(plan["applied"])
            self.assertEqual(plan["workspace_action"], "create_empty_root")
            self.assertEqual(applied["workspace_action"], "create_empty_root")
            self.assertTrue(workspace.is_dir())

    def test_upgrade_retires_unmodified_legacy_product_profiles_only(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            profile = (
                target
                / ".circled-wiki"
                / "agent-rules"
                / "repository-engineering.md"
            )
            profile.write_text("# Legacy product authority\n", encoding="utf-8")
            manifest_path = target / MANIFEST_PATH
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            from circled_wiki.core.bootstrap import _checksum
            relative = ".circled-wiki/agent-rules/repository-engineering.md"
            manifest["assets"][relative] = _checksum(profile.read_bytes())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertFalse(profile.exists())
            self.assertEqual(
                next(item["action"] for item in report["actions"] if item["path"] == relative),
                "retire_legacy_asset",
            )
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn(relative, updated["assets"])

    def test_upgrade_retires_unmodified_knowledge_os_runtime_and_launcher(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            manifest_path = target / MANIFEST_PATH
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            runtime = target / ".circled-wiki/runtime/knowledge_os/core/legacy.py"
            launcher = target / ".circled-wiki/bin/knowledge-os.py"
            profile = target / ".circled-wiki/agent-rules/bootstrap-knowledge-os.md"
            for path, content in (
                (runtime, b"legacy runtime\n"),
                (launcher, b"legacy launcher\n"),
                (profile, b"legacy product profile\n"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                manifest["assets"][path.relative_to(target).as_posix()] = _checksum(content)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertFalse(runtime.exists())
            self.assertFalse(launcher.exists())
            self.assertFalse(profile.exists())
            self.assertFalse((target / ".circled-wiki/runtime/knowledge_os").exists())
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertFalse(any("knowledge_os" in path for path in updated["assets"]))
            self.assertNotIn(".circled-wiki/bin/knowledge-os.py", updated["assets"])
            self.assertEqual(report["legacy_asset_warnings"], [])

    def test_upgrade_preserves_and_warns_about_modified_legacy_product_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            profile = (
                target
                / ".circled-wiki"
                / "agent-rules"
                / "repository-engineering.md"
            )
            profile.write_text("# Original legacy product authority\n", encoding="utf-8")
            manifest_path = target / MANIFEST_PATH
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            from circled_wiki.core.bootstrap import _checksum
            relative = ".circled-wiki/agent-rules/repository-engineering.md"
            manifest["assets"][relative] = _checksum(profile.read_bytes())
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            profile.write_text("# User-modified legacy authority\n", encoding="utf-8")

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertEqual(
                profile.read_text(encoding="utf-8"),
                "# User-modified legacy authority\n",
            )
            self.assertIn(relative, report["legacy_asset_warnings"])
            self.assertTrue(
                (
                    target
                    / ".circled-wiki"
                    / "proposals"
                    / "legacy-asset__.circled-wiki__agent-rules__repository-engineering.md.review.md"
                ).is_file()
            )
            updated = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertNotIn(relative, updated["assets"])

    def test_obsolete_control_plane_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            knowledge_file = target / "knowledge" / "existing.md"
            knowledge_file.write_text("keep this knowledge", encoding="utf-8")
            obsolete = target / ".obsolete-control-plane"
            obsolete.mkdir()

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

            self.assertTrue((target / ".circled-wiki" / "manifest.json").is_file())
            self.assertTrue(obsolete.exists())
            self.assertEqual(knowledge_file.read_text(encoding="utf-8"), "keep this knowledge")

    def test_upgrade_preserves_local_operational_issue_records(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "team-project"
            bootstrap_circled_wiki(target, ROOT, apply=True)
            issue = target / ".circled-wiki" / "issues" / "issue-user-feedback.md"
            issue.parent.mkdir(parents=True)
            issue.write_text("# User feedback\n", encoding="utf-8")
            original_rules = target / ".circled-wiki" / "OPERATING_RULES.md"
            original_rules.write_text(
                original_rules.read_text(encoding="utf-8") + "\nLocal team note\n",
                encoding="utf-8",
            )

            report = bootstrap_circled_wiki(target, ROOT, apply=True)

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
            bootstrap_circled_wiki(target, source, apply=True)
            knowledge_file = target / "knowledge" / "private-note.md"
            knowledge_file.write_text("preserve me", encoding="utf-8")
            old_manifest = json.loads((target / MANIFEST_PATH).read_text(encoding="utf-8"))

            (source / ".circled-wiki" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )
            plan = bootstrap_circled_wiki(target, source)
            self.assertTrue(plan["backup_required"])
            self.assertIsNone(plan["backup_path"])

            report = bootstrap_circled_wiki(target, source, apply=True)
            backup = Path(report["backup_path"])
            self.assertTrue(backup.is_dir())
            self.assertTrue(backup.name.startswith(old_manifest["os_release"] + "-"))
            self.assertEqual(
                (backup / "templates" / "runbook.md").read_text(encoding="utf-8"),
                "version 1\n",
            )
            self.assertEqual(
                (target / ".circled-wiki" / "templates" / "runbook.md").read_text(
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

            backups_before = sorted((target / ".circled-wiki-backups").iterdir())
            no_op = bootstrap_circled_wiki(target, source, apply=True)
            self.assertFalse(no_op["backup_required"])
            self.assertIsNone(no_op["backup_path"])
            self.assertEqual(sorted((target / ".circled-wiki-backups").iterdir()), backups_before)

    def test_backup_failure_stops_upgrade_before_existing_os_is_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._make_source(root / "source", "version 1\n")
            target = root / "target"
            bootstrap_circled_wiki(target, source, apply=True)
            installed = target / ".circled-wiki" / "templates" / "runbook.md"
            manifest = target / MANIFEST_PATH
            before_file = installed.read_bytes()
            before_manifest = manifest.read_bytes()
            (source / ".circled-wiki" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )

            with patch(
                "circled_wiki.core.bootstrap.shutil.copytree",
                side_effect=OSError("disk full"),
            ):
                with self.assertRaisesRegex(RuntimeError, "stopped before modifying"):
                    bootstrap_circled_wiki(target, source, apply=True)

            self.assertEqual(installed.read_bytes(), before_file)
            self.assertEqual(manifest.read_bytes(), before_manifest)

    def test_rollback_restores_only_the_control_plane_and_preserves_user_planes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._make_source(root / "source", "version 1\n")
            target = root / "target"
            bootstrap_circled_wiki(target, source, apply=True)
            knowledge = target / "knowledge" / "private.md"
            knowledge.write_text("knowledge state", encoding="utf-8")
            workspace = target / "workspace" / "agent" / "state.bin"
            workspace.parent.mkdir(parents=True)
            workspace.write_bytes(b"workspace state")
            (source / ".circled-wiki" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )
            upgraded = bootstrap_circled_wiki(target, source, apply=True)

            report = rollback_control_plane(
                target,
                Path(upgraded["backup_path"]).relative_to(target.resolve()).as_posix(),
            )

            self.assertEqual(
                (target / ".circled-wiki" / "templates" / "runbook.md").read_text(
                    encoding="utf-8"
                ),
                "version 1\n",
            )
            self.assertEqual(knowledge.read_text(encoding="utf-8"), "knowledge state")
            self.assertEqual(workspace.read_bytes(), b"workspace state")
            self.assertEqual(report["knowledge_action"], "preserve")
            self.assertEqual(report["workspace_action"], "preserve")
