import tempfile
import unittest
import subprocess
import shutil
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.ingest import (
    accept_conversation_intake,
    accept_ready_inbox,
    capture_conversation as _capture_conversation,
    complete_inbox_sensitivity_review,
)
from circled_wiki.worker.jobs import (
    MaintenanceReport,
    ingest_accepted_inbox,
    inspect_inbox,
    reconcile_curation,
    reconcile_inbox,
    reconcile_inbox_then_curation,
    run_curation_batch,
    run_maintenance,
)
from circled_wiki.core.publisher import PublishError, publish_changes
from circled_wiki.core.inbox_contracts import curation_blocker_policy
from circled_wiki.core.frontmatter import parse_markdown


def capture_conversation(*args, **kwargs):
    decision = kwargs.pop("sensitivity_review", None)
    result = _capture_conversation(*args, **kwargs)
    if decision in {"completed", "not_applicable"}:
        complete_inbox_sensitivity_review(
            args[0], result.intake_id, "test-inspection-agent", decision,
            policy_ref="inbox-sensitivity/v1",
            checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
            matched_categories=["test_fixture"] if decision == "completed" else [],
            rationale="테스트 fixture의 명시적 민감성 검사 결과다.",
        )
    return result


class WorkerJobTests(unittest.TestCase):
    def test_reconcile_inbox_archives_orphaned_review_task_without_recreating_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "inbox.yaml", "curation.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )
            captured = capture_conversation(
                root, "orphan source", "test", title="Orphan", why_collected="test",
                intended_use=["test"], idempotency_key="orphan-review",
            )
            captured.inbox_path.unlink()

            result = reconcile_inbox(root, "contract-worker")

            self.assertEqual(len(result["orphaned"]), 1)
            self.assertEqual(result["orphaned"][0]["intake_id"], captured.intake_id)
            archived = root.parent / result["orphaned"][0]["path"]
            self.assertTrue(archived.is_file())
            self.assertEqual(parse_markdown(archived).frontmatter["current"]["stage"], "orphaned")
            self.assertFalse(captured.inbox_path.exists())

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
            self.assertEqual(result["ingested"]["failed_count"], 0)
            self.assertEqual(result["blocked"][0]["intake_id"], blocked.intake_id)
            self.assertEqual(result["blocked"][0]["next_action"], "inbox_reconciliation")
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

    def test_reconcile_inbox_then_curation_starts_only_after_all_ready_inbox_is_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "inbox.yaml", "curation.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )
            capture_conversation(
                root, "safe source", "test", title="Ready", why_collected="test",
                intended_use=["test"], idempotency_key="pipeline-ready",
                sensitivity_review="completed",
            )

            with patch("circled_wiki.worker.jobs.reconcile_curation", return_value={"status": "processed"}) as curation:
                result = reconcile_inbox_then_curation(root, "contract-worker")

            self.assertEqual(result["status"], "curation_started")
            self.assertEqual(result["queue"]["item_count"], 1)
            self.assertEqual(result["inbox"]["runs"][0]["ingested"]["ingested_count"], 1)
            curation.assert_called_once_with(root, limit=100)

    def test_reconcile_inbox_then_curation_skips_curation_when_inbox_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "inbox.yaml", "curation.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )
            capture_conversation(
                root, "review source", "test", title="Blocked", why_collected="test",
                intended_use=["test"], idempotency_key="pipeline-blocked",
                sensitivity_review="required",
            )

            with patch("circled_wiki.worker.jobs.reconcile_curation") as curation:
                result = reconcile_inbox_then_curation(root, "contract-worker")

            self.assertEqual(result["status"], "inbox_blocked")
            self.assertEqual(result["curation"]["status"], "skipped")
            curation.assert_not_called()

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

    def test_reconcile_inbox_rejects_an_unsupported_review_requirement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            contract_root = root.parent / "agent-rules" / "contracts"
            contract_root.mkdir(parents=True)
            for name in ("index.yaml", "inbox.yaml"):
                shutil.copyfile(
                    Path(__file__).resolve().parents[2] / "agent-rules" / "contracts" / name,
                    contract_root / name,
                )
            contract_path = contract_root / "inbox.yaml"
            contract_path.write_text(
                contract_path.read_text(encoding="utf-8").replace(
                    "review_data_protection", "approve_without_review", 1
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "contract transition is unsupported: pending"):
                reconcile_inbox(root, "contract-worker")

    def test_every_curation_blocker_reason_has_a_contract_policy(self):
        expected = {
            "adapter_disabled": ("configuration", "configure_curation_adapter"),
            "adapter_command_empty": ("configuration", "configure_curation_adapter"),
            "evidence_original_unavailable": ("evidence_source", "restore_evidence_original"),
            "proposal_blocked": ("gate", "resolve_curation_gate"),
            "contract_or_gate_rejected": ("gate", "resolve_curation_gate"),
            "adapter_failed": ("adapter_execution", "retry_curation"),
            "adapter_unavailable": ("adapter_execution", "retry_curation"),
            "invalid_json": ("adapter_execution", "retry_curation"),
            "timeout": ("adapter_execution", "retry_curation"),
        }

        for reason, (category, next_action) in expected.items():
            with self.subTest(reason=reason):
                self.assertEqual(
                    curation_blocker_policy(reason),
                    {"category": category, "safe_next_action": next_action},
                )

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
