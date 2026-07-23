import tempfile
import unittest
import json
from pathlib import Path

from circled_wiki.core.observations import (
    migrate_legacy_system_issues,
    record_system_issue,
    update_system_issue_status,
)


class SystemObservationTests(unittest.TestCase):
    @staticmethod
    def _verification_receipts(
        project: Path, release: str, verifier: str
    ) -> tuple[str, str]:
        deployment = (
            project
            / "workspace"
            / "receipts"
            / "deployments"
            / "team"
            / f"{release}.json"
        )
        verification = (
            project
            / "workspace"
            / "receipts"
            / "verifications"
            / "team"
            / f"{release}.json"
        )
        deployment.parent.mkdir(parents=True)
        deployment.write_text(
            json.dumps({
                "receipt_type": "deployment",
                "release_id": release,
                "target_ref": "team",
                "status": "verification_pending",
            }),
            encoding="utf-8",
        )
        verification.parent.mkdir(parents=True)
        verification.write_text(
            json.dumps({
                "receipt_type": "verification",
                "release_id": release,
                "target_ref": "team",
                "deployment_receipt": deployment.as_posix(),
                "verified_by": verifier,
                "status": "verified",
            }),
            encoding="utf-8",
        )
        return (
            deployment.relative_to(project).as_posix(),
            verification.relative_to(project).as_posix(),
        )

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
                related_paths=[".circled-wiki/runtime/circled_wiki/worker/jobs.py"],
            )

            issue_path = Path(result["path"])
            content = issue_path.read_text(encoding="utf-8")
            self.assertTrue(issue_path.parent.samefile(project / "workspace" / "issues"))
            self.assertEqual(result["status"], "open")
            self.assertIn("Area: cli", content)
            self.assertIn("Severity: medium", content)
            self.assertIn("Reported from: user", content)
            self.assertIn("Release observed: unknown", content)
            self.assertIn("## Impact", content)
            self.assertIn("## Cause hypothesis", content)
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
                note="Scoped the problem.", classification="product_defect",
                next_action="prepare a regression test",
            )
            mitigated = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="mitigated", actor="maintainer",
                note="Implemented the safe fallback.", fixed_release="v1-test",
            )
            deployment_receipt, verification_receipt = self._verification_receipts(
                project, "v1-test", "reviewer"
            )
            verified = update_system_issue_status(
                project, issue_ref=created["issue_id"], status="verified", actor="reviewer",
                note="Verified the regression test.", fixed_release="v1-test",
                deployed_release="v1-test",
                deployment_receipt=deployment_receipt,
                verification="runtime reproduction passed",
                verification_receipt=verification_receipt,
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
            self.assertIn(f"deployment receipt: `{deployment_receipt}`", content)
            self.assertIn("verification: runtime reproduction passed", content)

    def test_blocks_self_verification_and_unproven_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            created = record_system_issue(project, title="Gate", summary="test", reported_by="operator")
            update_system_issue_status(
                project, issue_ref=created["issue_id"], status="triaged",
                actor="maintainer", note="triaged", classification="product_defect",
                next_action="implement a fix",
            )
            update_system_issue_status(project, issue_ref=created["issue_id"], status="mitigated", actor="implementer", note="fixed", fixed_release="v1")
            deployment_receipt, verification_receipt = self._verification_receipts(
                project, "v1", "implementer"
            )
            with self.assertRaisesRegex(ValueError, "independent actor"):
                update_system_issue_status(
                    project, issue_ref=created["issue_id"], status="verified",
                    actor="implementer", note="self check", fixed_release="v1",
                    deployed_release="v1", deployment_receipt=deployment_receipt,
                    verification="test", verification_receipt=verification_receipt,
                )
            with self.assertRaisesRegex(ValueError, "invalid Issue status transition"):
                update_system_issue_status(project, issue_ref=created["issue_id"], status="resolved", actor="maintainer", note="premature")

    def test_verified_requires_the_deployed_release_to_match_the_fix(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            created = record_system_issue(
                project, title="Release gate", summary="test", reported_by="operator"
            )
            update_system_issue_status(
                project, issue_ref=created["issue_id"], status="triaged",
                actor="maintainer", note="triaged", classification="product_defect",
                next_action="implement a fix",
            )
            update_system_issue_status(
                project, issue_ref=created["issue_id"], status="mitigated",
                actor="implementer", note="fixed", fixed_release="v2",
            )

            with self.assertRaisesRegex(ValueError, "match fixed_release"):
                update_system_issue_status(
                    project, issue_ref=created["issue_id"], status="verified",
                    actor="reviewer", note="wrong deployment", fixed_release="v2",
                    deployed_release="v1", deployment_receipt="deployment/v1",
                    verification="scenario passed", verification_receipt="verification/v1",
                )

    def test_can_update_a_legacy_control_plane_issue_without_moving_it(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            legacy = project / ".circled-wiki" / "issues" / "issue-legacy.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# Legacy\n\n- Issue ID: `issue-legacy`\n- Status: open\n",
                encoding="utf-8",
            )

            result = update_system_issue_status(
                project,
                issue_ref="issue-legacy",
                status="triaged",
                actor="maintainer",
                note="Legacy issue remains readable in place.",
                classification="operational_procedure",
                next_action="retain legacy compatibility",
            )

            self.assertEqual(Path(result["path"]).resolve(), legacy.resolve())
            self.assertFalse((project / "workspace" / "issues" / legacy.name).exists())

    def test_legacy_issue_migration_requires_explicit_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            legacy = project / ".circled-wiki" / "issues" / "issue-legacy.md"
            legacy.parent.mkdir(parents=True)
            legacy.write_text(
                "# Legacy\n\n- Issue ID: `issue-legacy`\n- Status: open\n",
                encoding="utf-8",
            )

            plan = migrate_legacy_system_issues(
                project, issue_refs=["issue-legacy"]
            )
            self.assertFalse(plan["applied"])
            self.assertTrue(legacy.is_file())
            applied = migrate_legacy_system_issues(
                project, issue_refs=["issue-legacy"], apply=True
            )

            migrated = project / "workspace" / "issues" / legacy.name
            self.assertEqual(applied["moved"], 1)
            self.assertFalse(legacy.exists())
            self.assertTrue(migrated.is_file())
