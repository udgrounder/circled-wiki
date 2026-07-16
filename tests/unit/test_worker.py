import tempfile
import unittest
import subprocess
from pathlib import Path

from knowledge_os.core.ingest import accept_conversation_intake, capture_conversation
from knowledge_os.worker.jobs import ingest_accepted_inbox, inspect_inbox, run_curation_batch, run_maintenance
from knowledge_os.core.publisher import PublishError, _require_sensitive_data_review, publish_changes


class WorkerJobTests(unittest.TestCase):
    def test_unmanaged_inbox_recovery_includes_exact_capture_file_argument(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge"
            inbox = root / "inbox"
            inbox.mkdir(parents=True)
            source = inbox / "신규 입사자 요청서.txt"
            source.write_text("test only", encoding="utf-8")

            report = inspect_inbox(root)

            self.assertEqual(report["skipped_unmanaged"], 1)
            self.assertIn(
                "--inbox-file '신규 입사자 요청서.txt'",
                report["unmanaged_files"][0]["recovery"],
            )

    def test_inbox_batch_rejects_tampered_content_without_creating_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge"
            result = capture_conversation(
                root,
                "원본 대화",
                "codex",
                title="변조 검사",
                why_collected="무결성 검증",
                intended_use=["integrity-test"],
                idempotency_key="tamper-test",
            )
            result.inbox_path.write_text(
                result.inbox_path.read_text(encoding="utf-8").replace("원본 대화", "변조 대화"),
                encoding="utf-8",
            )
            batch = inspect_inbox(root)

            self.assertEqual(batch["item_count"], 0)
            self.assertEqual(batch["invalid_count"], 1)
            self.assertIn("checksum", batch["invalid"][0]["error"])
            self.assertTrue(result.inbox_path.is_file())
            self.assertEqual(list((root / "evidence").rglob("*.md")), [])

    def test_inbox_batch_is_separate_from_capture_and_idempotent_after_processing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge"
            result = capture_conversation(
                root,
                "## User\n\n메뉴 이미지를 만들어줘.\n",
                "codex",
                title="메뉴 이미지 생성 대화",
                why_collected="Runbook 개선",
                intended_use=["menu-image-production"],
                idempotency_key="worker-thread:turns-1-1",
            )
            self.assertTrue(result.inbox_path.is_file())
            self.assertEqual(run_curation_batch(root)["proposal_count"], 0)
            inspection = inspect_inbox(root)
            self.assertEqual(inspection["items"][0]["gate_status"], "blocked")
            with self.assertRaisesRegex(ValueError, "sensitivity review"):
                accept_conversation_intake(root, result.intake_id, "inspection-agent")

            reviewed = capture_conversation(
                root,
                "## User\n\n다른 메뉴 이미지를 만들어줘.\n",
                "codex",
                title="검토 완료 대화",
                why_collected="Runbook 개선",
                intended_use=["menu-image-production"],
                idempotency_key="worker-thread:turns-2-2",
                sensitivity_review="completed",
            )
            accept_conversation_intake(root, reviewed.intake_id, "inspection-agent")
            first = ingest_accepted_inbox(root)
            second = ingest_accepted_inbox(root)

        self.assertEqual(first["ingested_count"], 1)
        self.assertEqual(first["items"][0]["intake_id"], reviewed.intake_id)
        self.assertEqual(second["ingested_count"], 0)

    def test_empty_repository_is_a_valid_repeatable_maintenance_run(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge"
            (root / "bundles").mkdir(parents=True)
            (root / "evidence").mkdir()
            first = run_maintenance(root)
            second = run_maintenance(root)
        self.assertEqual(first, second)
        self.assertTrue(first.valid)

    def test_publication_requires_a_git_repository(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "knowledge" / "bundles").mkdir(parents=True)
            (root / "knowledge" / "evidence").mkdir()
            with self.assertRaisesRegex(PublishError, "not a Git repository"):
                publish_changes(root, "knowledge: publish")

    def test_publication_blocks_unscanned_git_tracked_evidence(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            evidence = root / "knowledge" / "evidence" / "manual" / "sample.md"
            evidence.parent.mkdir(parents=True)
            evidence.write_text("---\ntype: evidence\noriginal_file_git_tracked: true\nextensions:\n  pii_scanned: false\n---\n", encoding="utf-8")
            with self.assertRaisesRegex(PublishError, "sensitive-data scan is incomplete"):
                _require_sensitive_data_review(root / "knowledge")

    def test_publication_rejects_preexisting_staged_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "knowledge" / "bundles").mkdir(parents=True)
            (root / "knowledge" / "evidence").mkdir()
            (root / "README.md").write_text("unrelated", encoding="utf-8")
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(root), "add", "README.md"], check=True)

            with self.assertRaisesRegex(PublishError, "pre-existing staged changes"):
                publish_changes(root, "knowledge: publish")
