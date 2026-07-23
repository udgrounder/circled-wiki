import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.bootstrap import bootstrap_circled_wiki
from circled_wiki.core.issue_workspace import (
    archive_workspace_issue,
    intake_operational_issue,
    link_workspace_issue_resolution,
    review_workspace_issue,
    triage_workspace_issue,
)
from circled_wiki.core.observations import record_system_issue
from circled_wiki.core.receipts import (
    record_deployment_receipt,
    record_release_receipt,
    record_verification_receipt,
)


class IssueImprovementEndToEndTests(unittest.TestCase):
    def _source(self, root: Path) -> Path:
        source = root / "product-source"
        (source / "agent-rules").mkdir(parents=True)
        for profile in ("system-observation.md", "runtime-upgrade-verification.md"):
            (source / "agent-rules" / profile).write_text(
                f"# {profile}\n", encoding="utf-8"
            )
        control = source / ".circled-wiki"
        for directory in ("templates", "policies", "schemas", "bin"):
            (control / directory).mkdir(parents=True)
        (source / "OPERATING_RULES.md").write_text("# Runtime rules\n", encoding="utf-8")
        (control / "AGENT_ROUTER.md").write_text("# Runtime router\n", encoding="utf-8")
        (control / "templates" / "runbook.md").write_text("version 1\n", encoding="utf-8")
        (control / "templates" / ".gitignore").write_text(
            "# BEGIN circled-wiki:generated-artifacts\n"
            ".circled-wiki-backups/\n"
            "# END circled-wiki:generated-artifacts\n",
            encoding="utf-8",
        )
        runtime = source / "src" / "circled_wiki"
        runtime.mkdir(parents=True)
        (runtime / "__init__.py").write_text("__version__ = 'test'\n", encoding="utf-8")
        return source

    def _init_git(self, target: Path) -> None:
        subprocess.run(["git", "init", str(target)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(target), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(target), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(target), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(target), "commit", "-m", "install runtime"],
            check=True,
            capture_output=True,
        )

    def test_issue_to_upgrade_verification_and_versioned_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source(root)
            target = root / "installed-wiki"
            product_workspace = root / "product-workspace"
            bootstrap_circled_wiki(target, source, apply=True)
            self._init_git(target)
            issue = record_system_issue(
                target,
                title="Runtime failure",
                summary="Upgrade scenario fails.",
                reported_by="user-1",
                reported_from="user",
                area="runtime",
            )
            subprocess.run(["git", "-C", str(target), "add", "."], check=True)
            subprocess.run(
                ["git", "-C", str(target), "commit", "-m", "record runtime issue"],
                check=True,
                capture_output=True,
            )

            item = Path(
                intake_operational_issue(
                    product_workspace,
                    target,
                    project_ref="team-wiki",
                    issue_ref=issue["issue_id"],
                    requested_by="user-1",
                    moved_by="product-agent",
                )["path"]
            )
            review_workspace_issue(
                item,
                reviewed_by="user-1",
                decision="accepted",
                history_relation="new",
                canonical_issue_key="runtime-upgrade-failure",
            )
            triage_workspace_issue(
                item,
                classification="product_defect",
                linked_work=["tests/runtime-upgrade-regression"],
            )

            sentinel = target / "workspace" / "agent-log" / "state.bin"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_bytes(b"user-owned-state")
            old_release = json.loads(
                (target / ".circled-wiki" / "manifest.json").read_text(encoding="utf-8")
            )["os_release"]
            (source / ".circled-wiki" / "templates" / "runbook.md").write_text(
                "version 2\n", encoding="utf-8"
            )
            upgrade = bootstrap_circled_wiki(target, source, apply=True)
            self.assertEqual(sentinel.read_bytes(), b"user-owned-state")

            receipts = target / "workspace" / "receipts"
            release = record_release_receipt(
                receipts,
                manifest_path=target / ".circled-wiki" / "manifest.json",
                source_revision="a" * 40,
                included_issue_ids=[issue["issue_id"]],
                validation={
                    "unit": "passed",
                    "integration": "passed",
                    "repository_validator": "passed",
                },
                verified_by="release-reviewer",
            )
            deployment = record_deployment_receipt(
                receipts,
                release_receipt=Path(release["path"]),
                previous_release=old_release,
                target_ref="team-wiki",
                backup_ref=Path(upgrade["backup_path"]).relative_to(target.resolve()).as_posix(),
                actions={
                    "applied": [
                        action["path"]
                        for action in upgrade["actions"]
                        if action["action"] in {"create", "upgrade"}
                    ],
                    "preserved": [
                        action["path"]
                        for action in upgrade["actions"]
                        if action["action"] in {"unchanged", "preserve_existing"}
                    ],
                    "proposed": [
                        action["path"]
                        for action in upgrade["actions"]
                        if action["action"] == "preserve_and_propose"
                    ],
                },
            )
            verification = record_verification_receipt(
                receipts,
                deployment_receipt=Path(deployment["path"]),
                expected_release=upgrade["os_release"],
                observed_release=upgrade["os_release"],
                verified_by="runtime-reviewer",
                implemented_by="product-agent",
                preflight_ready=True,
                validator_passed=True,
                config_preserved=True,
                knowledge_preserved=True,
                workspace_preserved=True,
                reproduction_passed=True,
            )
            link_workspace_issue_resolution(
                item,
                disposition="resolved",
                release=upgrade["os_release"],
                deployment_receipt=Path(deployment["path"]).as_posix(),
                verification_receipt=Path(verification["path"]).as_posix(),
            )
            archived = archive_workspace_issue(
                product_workspace,
                item,
                archived_by="product-agent",
                reason="release deployed and independently verified",
                restore_condition="new recurrence",
            )

            self.assertTrue(Path(archived["path"]).is_file())
            self.assertFalse(item.exists())
            self.assertTrue(archived["path"].endswith("runtime-upgrade-failure/v0001.md"))
