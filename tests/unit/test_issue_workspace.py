import subprocess
import tempfile
import unittest
import json
from datetime import datetime, timezone
from pathlib import Path

from circled_wiki.core.frontmatter import parse_markdown
from circled_wiki.core.issue_workspace import (
    archive_workspace_issue,
    intake_operational_issue,
    link_workspace_issue_resolution,
    review_workspace_issue,
    triage_workspace_issue,
)


class IssueWorkspaceTests(unittest.TestCase):
    def _source_repo(self, root: Path, issue_id: str = "issue-runtime-1") -> Path:
        source = root / "runtime-project"
        issue = source / "workspace" / "issues" / f"{issue_id}.md"
        issue.parent.mkdir(parents=True)
        issue.write_text(
            f"# Runtime failure\n\n"
            f"- Issue ID: `{issue_id}`\n"
            "- Area: runtime\n"
            "- Release observed: v1-old\n"
            "- Status: open\n\n"
            "## Summary\n\nThe runtime failed.\n",
            encoding="utf-8",
        )
        manifest = source / ".circled-wiki" / "manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            json.dumps({"schema_version": 1, "os_release": "v1-old", "assets": {}}),
            encoding="utf-8",
        )
        subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.email", "test@example.com"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(["git", "-C", str(source), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-m", "record issue"],
            check=True,
            capture_output=True,
        )
        return source

    def test_intake_moves_a_committed_issue_and_preserves_git_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_repo(root)
            product_workspace = root / "product" / "workspace"

            result = intake_operational_issue(
                product_workspace,
                source,
                project_ref="team-wiki",
                issue_ref="issue-runtime-1",
                requested_by="user-1",
                moved_by="agent-1",
            )

            item = Path(result["path"])
            self.assertTrue(item.is_file())
            self.assertEqual(item.parent.parent.parent.name, "issues")
            self.assertFalse((product_workspace / "issue").exists())
            self.assertFalse(
                (source / "workspace" / "issues" / "issue-runtime-1.md").exists()
            )
            metadata = parse_markdown(item).frontmatter
            self.assertEqual(metadata["status"], "pending_review")
            self.assertEqual(metadata["source_project_ref"], "team-wiki")
            self.assertEqual(len(metadata["source_git_revision"]), 40)

    def test_intake_rejects_uncommitted_changes_without_moving_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_repo(root)
            issue = source / "workspace" / "issues" / "issue-runtime-1.md"
            issue.write_text(issue.read_text(encoding="utf-8") + "\ndrift\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "uncommitted"):
                intake_operational_issue(
                    root / "product" / "workspace",
                    source,
                    project_ref="team-wiki",
                    issue_ref="issue-runtime-1",
                    requested_by="user-1",
                    moved_by="agent-1",
                )

            self.assertTrue(issue.is_file())

    def test_review_is_required_before_triage_and_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_repo(root)
            product_workspace = root / "product" / "workspace"
            item = Path(
                intake_operational_issue(
                    product_workspace,
                    source,
                    project_ref="team-wiki",
                    issue_ref="issue-runtime-1",
                    requested_by="user-1",
                    moved_by="agent-1",
                )["path"]
            )

            with self.assertRaisesRegex(ValueError, "accepted user review"):
                triage_workspace_issue(item, classification="product_defect")
            with self.assertRaisesRegex(ValueError, "review receipt"):
                archive_workspace_issue(
                    product_workspace,
                    item,
                    archived_by="agent-1",
                    reason="done",
                    restore_condition="recurrence",
                )
            with self.assertRaisesRegex(ValueError, "determined history relation"):
                review_workspace_issue(
                    item,
                    reviewed_by="user-1",
                    decision="accepted",
                    history_relation="undetermined",
                )

    def test_resolved_issue_requires_receipts_and_is_moved_to_date_organized_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._source_repo(root)
            product_workspace = root / "product" / "workspace"
            item = Path(
                intake_operational_issue(
                    product_workspace,
                    source,
                    project_ref="team-wiki",
                    issue_ref="issue-runtime-1",
                    requested_by="user-1",
                    moved_by="agent-1",
                )["path"]
            )
            review_workspace_issue(
                item,
                reviewed_by="user-1",
                decision="accepted",
                history_relation="new",
                canonical_issue_key="runtime-failure",
            )
            triage_workspace_issue(item, classification="product_defect")
            link_workspace_issue_resolution(item, disposition="resolved", release="v2")
            with self.assertRaisesRegex(ValueError, "deployment, and verification"):
                archive_workspace_issue(
                    product_workspace,
                    item,
                    archived_by="agent-1",
                    reason="fixed",
                    restore_condition="reopen on recurrence",
                )
            link_workspace_issue_resolution(
                item,
                disposition="resolved",
                release="v2",
                deployment_receipt="deployment/team-wiki/v2",
                verification_receipt="verification/team-wiki/v2",
            )

            archived = archive_workspace_issue(
                product_workspace,
                item,
                archived_by="agent-1",
                reason="fixed and independently verified",
                restore_condition="reopen on recurrence",
            )

            self.assertFalse(item.exists())
            self.assertTrue(Path(archived["path"]).is_file())
            path = Path(archived["path"])
            self.assertEqual(path.parent.parent.name, str(datetime.now(timezone.utc).year))
            self.assertEqual(path.parent.name, f"{datetime.now(timezone.utc).month:02d}")
            self.assertRegex(path.name, r"^\d{8}T\d{6}Z-runtime-failure-v0001\.md$")

    def test_recurrence_intake_surfaces_previous_resolution_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            product_workspace = root / "product" / "workspace"
            first_source = self._source_repo(root, "issue-runtime-1")
            first_item = Path(
                intake_operational_issue(
                    product_workspace,
                    first_source,
                    project_ref="team-wiki",
                    issue_ref="issue-runtime-1",
                    requested_by="user-1",
                    moved_by="agent-1",
                )["path"]
            )
            review_workspace_issue(
                first_item,
                reviewed_by="user-1",
                decision="rejected",
                history_relation="new",
                canonical_issue_key="runtime-failure",
            )
            link_workspace_issue_resolution(first_item, disposition="rejected")
            archive_workspace_issue(
                product_workspace,
                first_item,
                archived_by="agent-1",
                reason="baseline history",
                restore_condition="new occurrence",
            )

            second_root = root / "second"
            second_source = self._source_repo(second_root, "issue-runtime-2")
            result = intake_operational_issue(
                product_workspace,
                second_source,
                project_ref="team-wiki-2",
                issue_ref="issue-runtime-2",
                requested_by="user-1",
                moved_by="agent-1",
            )

            self.assertEqual(len(result["similar_history"]), 1)
            self.assertIn(
                "same normalized title",
                result["similar_history"][0]["similarity_reasons"],
            )
