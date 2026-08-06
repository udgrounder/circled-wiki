import json
import tempfile
import unittest
from pathlib import Path

from circled_wiki.engineering.receipts import (
    build_release_manifest,
    record_deployment_receipt,
    record_release_receipt,
    record_verification_receipt,
    write_release_manifest,
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

    def test_build_release_manifest_is_side_effect_free_and_uses_only_managed_assets(self):
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

            manifest = build_release_manifest(source)

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["runtime_profiles"], ["knowledge-query.md"])
            self.assertIn(".circled-wiki/runtime/circled_wiki/module.py", manifest["assets"])
            self.assertFalse((source / "workspace").exists())

    def test_release_manifest_is_immutable_and_allows_identical_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "release.json"
            manifest = {
                "schema_version": 1,
                "os_release": "v-test",
                "assets": {".circled-wiki/AGENT_ROUTER.md": "sha256:router"},
                "runtime_profiles": ["knowledge-query.md"],
                "router_checksum": "sha256:router",
            }

            result = write_release_manifest(path, manifest)
            replay = write_release_manifest(path, manifest)
            self.assertEqual(result["path"], path.as_posix())
            self.assertEqual(replay["os_release"], "v-test")

            changed = dict(manifest)
            changed["os_release"] = "v-other"
            with self.assertRaisesRegex(ValueError, "immutable release manifest"):
                write_release_manifest(path, changed)

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

    def test_failed_deployment_allows_a_new_immutable_attempt_for_same_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipts = root / "workspace" / "receipts"
            release = record_release_receipt(
                receipts, manifest_path=self._manifest(root), source_revision="a" * 40,
                included_issue_ids=[],
                validation={"unit": "passed", "integration": "passed", "repository_validator": "passed"},
                verified_by="reviewer",
            )
            failed = record_deployment_receipt(
                receipts, release_receipt=Path(release["path"]), previous_release="v1",
                target_ref="team-wiki", backup_ref="backup/v1",
                actions={"applied": [], "preserved": [], "proposed": []}, status="failed",
            )
            retry = record_deployment_receipt(
                receipts, release_receipt=Path(release["path"]), previous_release="v2",
                target_ref="team-wiki", backup_ref="backup/v2",
                actions={"applied": [], "preserved": [], "proposed": []}, status="verification_pending",
            )
            self.assertEqual(failed["deployment_attempt"], 1)
            self.assertEqual(retry["deployment_attempt"], 2)
            self.assertTrue(retry["path"].endswith("v2.attempt-2.json"))

    def test_release_receipt_records_a_verified_source_commit_check(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = record_release_receipt(
                root / "workspace" / "receipts",
                manifest_path=self._manifest(root),
                source_revision="a" * 40,
                included_issue_ids=[],
                validation={
                    "unit": "passed", "integration": "passed", "repository_validator": "passed",
                },
                verified_by="reviewer",
                source_commit_check={
                    "revision": "a" * 40,
                    "subject": "release source", "worktree_clean": True,
                },
            )

            self.assertEqual(receipt["source_commit_check"]["revision"], "a" * 40)
            self.assertTrue(receipt["source_commit_check"]["worktree_clean"])

    def test_release_receipt_rejects_assets_outside_runtime_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self._manifest(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["assets"]["product-agent-rules/release-preparation.md"] = "sha256:product"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "asset outside the allowlist"):
                record_release_receipt(
                    root / "workspace" / "receipts",
                    manifest_path=manifest_path,
                    source_revision="a" * 40,
                    included_issue_ids=[],
                    validation={
                        "unit": "passed", "integration": "passed", "repository_validator": "passed",
                    },
                    verified_by="reviewer",
                )

    def test_release_receipt_rejects_runtime_profiles_outside_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = self._manifest(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["runtime_profiles"].append("release-preparation.md")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Runtime Profile outside the allowlist"):
                record_release_receipt(
                    root / "workspace" / "receipts",
                    manifest_path=manifest_path,
                    source_revision="a" * 40,
                    included_issue_ids=[],
                    validation={
                        "unit": "passed", "integration": "passed", "repository_validator": "passed",
                    },
                    verified_by="reviewer",
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
                    validator_passed=True,
                    config_preserved=True,
                    knowledge_preserved=True,
                    workspace_preserved=False,
                    reproduction_passed=True,
                )
