import tempfile
import unittest
import subprocess
import shutil
from pathlib import Path

from circled_wiki.core.ingest import (
    accept_conversation_intake,
    accept_ready_inbox,
    capture_conversation,
)
from circled_wiki.worker.jobs import (
    MaintenanceReport,
    ingest_accepted_inbox,
    inspect_inbox,
    reconcile_curation,
    reconcile_inbox,
    run_curation_batch,
    run_maintenance,
)
from circled_wiki.core.publisher import PublishError, _require_sensitive_data_review, publish_changes


class WorkerJobTests(unittest.TestCase):
    def test_reconcile_inbox_advances_only_contract_safe_stages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            shutil.copyfile(
                Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / "index.yaml",
                contract_root / "index.yaml",
            )
            shutil.copyfile(
                Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / "inbox.yaml",
                contract_root / "inbox.yaml",
            )
            shutil.copyfile(
                Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / "curation.yaml",
                contract_root / "curation.yaml",
            )
            ready = capture_conversation(
                root, "safe source", "test", title="Ready", why_collected="test",
                intended_use=["test"], idempotency_key="reconcile-ready",
                sensitivity_review="completed",
            )
            blocked = capture_conversation(
                root, "review source", "test", title="Blocked", why_collected="test",
                intended_use=["test"], idempotency_key="reconcile-blocked",
                sensitivity_review="required",
            )

            result = reconcile_inbox(root, "contract-worker")

            self.assertEqual(result["contract"]["name"], "inbox_reconciliation")
            self.assertEqual(result["before"]["item_count"], 2)
            self.assertEqual(result["accepted"]["accepted_count"], 1)
            self.assertEqual(result["ingested"]["ingested_count"], 1)
            self.assertEqual(result["blocked"][0]["intake_id"], blocked.intake_id)
            self.assertEqual(result["blocked"][0]["next_action"], "inbox_review_queue")
            self.assertEqual(
                next(item for item in result["after"]["items"] if item["intake_id"] == ready.intake_id)["status"],
                "evidence",
            )
            self.assertFalse(ready.inbox_path.exists())
            self.assertTrue(blocked.inbox_path.exists())

    def test_reconcile_curation_uses_registered_contract_without_applying_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "inbox.yaml", "curation.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )

            result = reconcile_curation(root)

            self.assertEqual(result["contract"]["name"], "curation_reconciliation")
            self.assertEqual(result["before"]["item_count"], 0)
            self.assertEqual(result["actions"]["attempted"], 0)
            self.assertEqual(result["blocked"], [])

    def test_reconcile_curation_rejects_an_incomplete_outcome_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "curation.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )
            contract_path = contract_root / "curation.yaml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8").replace(
                    "        draft_created:\n", "        omitted_draft_created:\n", 1
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "contract outcomes are incomplete"):
                reconcile_curation(root)

    def test_accept_ready_inbox_accepts_only_items_that_already_pass_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            ready = capture_conversation(
                root, "safe source", "test", title="Ready", why_collected="test",
                intended_use=["test"], idempotency_key="ready", sensitivity_review="completed",
            )
            blocked = capture_conversation(
                root, "review source", "test", title="Blocked", why_collected="test",
                intended_use=["test"], idempotency_key="blocked", sensitivity_review="required",
            )

            result = accept_ready_inbox(root, "batch-inspector")

            self.assertEqual(result["accepted_count"], 1)
            self.assertEqual(result["items"][0]["intake_id"], ready.intake_id)
            self.assertEqual(result["skipped_count"], 1)
            self.assertEqual(result["skipped"][0]["intake_id"], blocked.intake_id)

    def test_maintenance_report_uses_evidence_record_name_with_compatibility_alias(self):
        report = MaintenanceReport(
            valid=True,
            managed_documents=2,
            bundles=1,
            evidence_records=1,
            audit_issues=0,
            audit_errors=0,
        )

        payload = report.as_dict()

        self.assertEqual(payload["evidence_records"], 1)
        self.assertEqual(payload["evidence_manifests"], 1)
        self.assertEqual(report.evidence_manifests, 1)

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

    def test_required_sensitivity_review_blocks_acceptance_and_evidence_ingest(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge"
            captured = capture_conversation(
                root, "가상 테스트용 운영 메모", "synthetic",
                title="민감성 검토 대기", why_collected="Gate 통합 검증",
                intended_use=["safety-test"], idempotency_key="required-review-flow",
            )

            with self.assertRaisesRegex(ValueError, "sensitivity review"):
                accept_conversation_intake(root, captured.intake_id, "reviewer")
            ingested = ingest_accepted_inbox(root)

            self.assertEqual(ingested["ingested_count"], 0)
            self.assertEqual(list((root / "evidence").rglob("*.md")), [])
            self.assertEqual(inspect_inbox(root)["items"][0]["gate_status"], "blocked")

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
