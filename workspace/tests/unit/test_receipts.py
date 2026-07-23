import json
import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.receipts import (
    record_deployment_receipt,
    record_release_receipt,
    record_verification_receipt,
)


class ReceiptTests(unittest.TestCase):
    def _manifest(self, root: Path) -> Path:
        path = root / "manifest.json"
        router = "sha256:router"
        path.write_text(
            json.dumps({
                "os_release": "v2",
                "router_checksum": router,
                "runtime_profiles": [
                    "knowledge-query.md",
                    "system-observation.md",
                    "runtime-upgrade-verification.md",
                ],
                "assets": {
                    ".circled-wiki/AGENT_ROUTER.md": router,
                    ".circled-wiki/runtime/circled_wiki/core/service.py": "sha256:runtime",
                },
            }),
            encoding="utf-8",
        )
        return path

    def test_records_cross_linked_release_deployment_and_verification_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "workspace" / "receipts"
            release = record_release_receipt(
                receipts,
                manifest_path=self._manifest(root),
                source_revision="a" * 40,
                included_issue_ids=["issue-1"],
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
                previous_release="v1",
                target_ref="team-wiki",
                backup_ref=".circled-wiki-backups/v1-test",
                actions={"applied": [".circled-wiki/AGENT_ROUTER.md"], "preserved": [], "proposed": []},
            )
            verification = record_verification_receipt(
                receipts,
                deployment_receipt=Path(deployment["path"]),
                expected_release="v2",
                observed_release="v2",
                verified_by="runtime-reviewer",
                implemented_by="implementer",
                preflight_ready=True,
                validator_passed=True,
                config_preserved=True,
                knowledge_preserved=True,
                workspace_preserved=True,
                reproduction_passed=True,
            )

            self.assertEqual(verification["status"], "verified")
            self.assertTrue(Path(verification["path"]).is_file())

    def test_deployment_rejects_user_plane_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "workspace" / "receipts"
            release = record_release_receipt(
                receipts,
                manifest_path=self._manifest(root),
                source_revision="a" * 40,
                included_issue_ids=[],
                validation={
                    "unit": "passed",
                    "integration": "passed",
                    "repository_validator": "passed",
                },
                verified_by="reviewer",
            )
            with self.assertRaisesRegex(ValueError, "knowledge/ or workspace/"):
                record_deployment_receipt(
                    receipts,
                    release_receipt=Path(release["path"]),
                    previous_release="v1",
                    target_ref="team-wiki",
                    backup_ref="backup/v1",
                    actions={"applied": ["workspace/issues/x.md"], "preserved": [], "proposed": []},
                )

    def test_verification_blocks_self_verification_and_failed_preservation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "workspace" / "receipts"
            release = record_release_receipt(
                receipts,
                manifest_path=self._manifest(root),
                source_revision="a" * 40,
                included_issue_ids=[],
                validation={
                    "unit": "passed",
                    "integration": "passed",
                    "repository_validator": "passed",
                },
                verified_by="reviewer",
            )
            deployment = record_deployment_receipt(
                receipts,
                release_receipt=Path(release["path"]),
                previous_release="v1",
                target_ref="team-wiki",
                backup_ref="backup/v1",
                actions={"applied": [], "preserved": [], "proposed": []},
            )
            with self.assertRaisesRegex(ValueError, "independent actor"):
                record_verification_receipt(
                    receipts,
                    deployment_receipt=Path(deployment["path"]),
                    expected_release="v2",
                    observed_release="v2",
                    verified_by="same",
                    implemented_by="same",
                    preflight_ready=True,
                    validator_passed=True,
                    config_preserved=True,
                    knowledge_preserved=True,
                    workspace_preserved=True,
                    reproduction_passed=True,
                )
            with self.assertRaisesRegex(ValueError, "workspace_preserved"):
                record_verification_receipt(
                    receipts,
                    deployment_receipt=Path(deployment["path"]),
                    expected_release="v2",
                    observed_release="v2",
                    verified_by="reviewer",
                    implemented_by="implementer",
                    preflight_ready=True,
                    validator_passed=True,
                    config_preserved=True,
                    knowledge_preserved=True,
                    workspace_preserved=False,
                    reproduction_passed=True,
                )
