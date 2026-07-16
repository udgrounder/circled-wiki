import tempfile
import unittest
from pathlib import Path

from knowledge_os.core.observations import record_system_issue, update_system_issue_status


class SystemObservationTests(unittest.TestCase):
    def test_records_a_structured_local_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            result = record_system_issue(
                project,
                title="Inbox error is unclear",
                summary="The intake ID was omitted from the error.",
                reported_by="operator-1",
                reported_from="user",
                area="cli",
                severity="medium",
                expected="The failing intake is identified.",
                actual="Only a generic error appears.",
                reproduction="Inspect a malformed intake.",
                improvement_hint="Include the intake ID.",
                related_paths=[".knowledge-os/runtime/knowledge_os/worker/jobs.py"],
            )

            issue_path = Path(result["path"])
            content = issue_path.read_text(encoding="utf-8")
            self.assertTrue(issue_path.parent.samefile(project / ".knowledge-os" / "issues"))
            self.assertEqual(result["status"], "open")
            self.assertIn("Area: cli", content)
            self.assertIn("Severity: medium", content)
            self.assertIn("Reported from: user", content)
            self.assertIn("Pending system-maintainer review", content)

    def test_rejects_unknown_issue_area(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "area must be one of"):
                record_system_issue(
                    Path(directory),
                    title="Invalid area",
                    summary="test",
                    reported_by="operator-1",
                    area="unknown",
                )

    def test_rejects_unknown_issue_reporter_type(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "reported_from must be one of"):
                record_system_issue(
                    Path(directory),
                    title="Invalid reporter",
                    summary="test",
                    reported_by="operator-1",
                    reported_from="unknown",
                )

    def test_tracks_auditable_issue_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            created = record_system_issue(
                project, title="Lifecycle", summary="test", reported_by="operator-1"
            )
            triaged = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="triaged", actor="maintainer",
                note="Scoped the problem.",
            )
            mitigated = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="mitigated", actor="maintainer",
                note="Implemented the safe fallback.", fixed_release="v1-test",
            )
            verified = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="verified", actor="reviewer",
                note="Verified the regression test.", verification="unit test passed",
            )
            resolved = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="resolved", actor="reviewer",
                note="Closed after verification.",
            )
            self.assertEqual(triaged["status"], "triaged")
            self.assertEqual(mitigated["status"], "mitigated")
            self.assertEqual(verified["status"], "verified")
            self.assertEqual(resolved["status"], "resolved")
            content = Path(created["path"]).read_text(encoding="utf-8")
            self.assertIn("Status: resolved", content)
            self.assertIn("fixed release: `v1-test`", content)
            self.assertIn("verification: unit test passed", content)
