from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.ingest import (
    CaptureIdempotencyConflict,
    MAX_GIT_EVIDENCE_BYTES,
    accept_conversation_intake,
    capture_conversation as _capture_conversation,
    capture_document as _capture_document,
    capture_file as _capture_file,
    complete_inbox_sensitivity_review,
    ingest_evidence,
    record_inbox_pii_scan_receipt,
    request_inbox_sensitivity_decision,
)
from circled_wiki.core.inbox_review_queue import get_inbox_review, list_inbox_review_queue
from circled_wiki.core.repository import apply_bundle_revision, create_bundle
from circled_wiki.core.curator import propose_update
from circled_wiki.core.search import search_knowledge
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.validator import validate_repository
from circled_wiki.integrations.channel import answer_knowledge_query, prepare_channel_workflow
from circled_wiki.worker.jobs import ingest_accepted_inbox, inspect_inbox


def _capture_with_resolved_sensitivity(capture, *args, **kwargs):
    decision = kwargs.pop("sensitivity_review", None)
    result = capture(*args, **kwargs)
    # A file has no generic text candidate for the integrated scanner.  The
    # test supplies an explicit external scan receipt before resolving it.
    if decision in {"completed", "not_applicable"} and capture.__name__ != "capture_file":
        complete_inbox_sensitivity_review(
            args[0], result.intake_id, "test-inspection-agent", decision,
            policy_ref="inbox-sensitivity/v1",
            checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
            matched_categories=["test_fixture"] if decision == "completed" else [],
            rationale="테스트 fixture의 명시적 민감성 검사 결과다.",
        )
    return result


def capture_conversation(*args, **kwargs):
    return _capture_with_resolved_sensitivity(_capture_conversation, *args, **kwargs)


def capture_document(*args, **kwargs):
    return _capture_with_resolved_sensitivity(_capture_document, *args, **kwargs)


def capture_file(*args, **kwargs):
    return _capture_with_resolved_sensitivity(_capture_file, *args, **kwargs)


class IngestEvidenceTests(unittest.TestCase):
    def test_required_sensitivity_is_agent_work_not_a_user_review_queue(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "reviewed source", "manual", title="Review needed",
                why_collected="review queue test", intended_use=["test"],
                idempotency_key="review-queue-sensitivity",
            )

            self.assertEqual(list_inbox_review_queue(knowledge_root), [])
            task_path = next((knowledge_root.parent / "workspace" / "task" / "inbox_reconciliation").glob("*.md"))
            task = parse_markdown(task_path)
            self.assertEqual(task.frontmatter["type"], "contract_task")
            self.assertEqual(task.frontmatter["contract"], {"name": "inbox_reconciliation", "version": 1})
            self.assertEqual(task.frontmatter["current"]["status"], "pending")
            self.assertEqual(task.frontmatter["current"]["actor"], "inbox-inspection-agent")
            self.assertEqual(task.frontmatter["requirements"][0]["reason_code"], "sensitivity_review_required")
            self.assertTrue(task.frontmatter["step_receipts"])

            complete_inbox_sensitivity_review(
                knowledge_root, captured.intake_id, "inbox-inspection-agent", "completed",
                policy_ref="inbox-sensitivity/v1",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                matched_categories=["internal_business_context"],
                rationale="내부 보존 범위와 접근 제한 조치를 적용한다.",
            )
            inspection = parse_markdown(captured.inbox_path).frontmatter["sensitivity_inspection"]
            self.assertEqual(inspection["policy_ref"], "inbox-sensitivity/v1")
            self.assertEqual(inspection["matched_categories"], ["internal_business_context"])
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)

            self.assertEqual(result["ingested_count"], 1)
            self.assertEqual(list_inbox_review_queue(knowledge_root), [])
            evidence = parse_markdown(knowledge_root.parent / result["items"][0]["evidence_path"])
            self.assertEqual(
                evidence.frontmatter["extensions"]["inbox_review"]["reason_codes"],
                ["sensitivity_review_required"],
            )

    def test_sensitivity_review_rejects_decision_without_required_receipt_basis(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "public procedure", "manual", title="Receipt required",
                why_collected="sensitivity receipt test", intended_use=["test"],
                idempotency_key="sensitivity-receipt-required",
            )

            with self.assertRaisesRegex(ValueError, "checks must contain"):
                complete_inbox_sensitivity_review(
                    knowledge_root, captured.intake_id, "inbox-inspection-agent", "not_applicable",
                    policy_ref="inbox-sensitivity/v1", checks=[], matched_categories=[],
                    rationale="근거 없는 결정은 허용하지 않는다.",
                )
            self.assertEqual(
                parse_markdown(captured.inbox_path).frontmatter["sensitivity_review"], "required"
            )

    def test_unresolved_sensitivity_records_structured_user_decision_request(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "restricted source", "manual", title="Need decision",
                why_collected="sensitivity escalation test", intended_use=["test"],
                idempotency_key="sensitivity-escalation",
            )

            result = request_inbox_sensitivity_decision(
                knowledge_root, captured.intake_id, "inbox-inspection-agent",
                question="이 접근 제한 원문을 internal 범위로 보존해도 되는가?",
                missing_procedure="접근 제한 원문의 보존 범위 절차가 없다.",
                safe_next_action="보존 범위와 visibility를 결정한다.",
                facts=["담당자 연락처는 010-1234-5678이며 원문에 접근 제한 표시가 있다."],
                hypotheses=["internal 보존이 가능할 수 있다."],
            )

            self.assertEqual(result["status"], "awaiting_user")
            queue = list_inbox_review_queue(knowledge_root)
            self.assertEqual(len(queue), 1)
            requirement = queue[0]["requirements"][0]
            self.assertEqual(requirement["blocked_step"], "sensitivity_review")
            self.assertEqual(requirement["facts"], ["담당자 연락처는 ********이며 원문에 접근 제한 표시가 있다."])
            self.assertEqual(requirement["hypotheses"], ["internal 보존이 가능할 수 있다."])
            self.assertEqual(requirement["pii_scan"]["result"], "passed")
            self.assertEqual(requirement["pii_scan"]["categories"], [])
            self.assertEqual(
                requirement["pii_scan"]["policy_candidates"], ["mobile_phone_number"]
            )

            task_path = knowledge_root.parent / "workspace" / "task" / "inbox_reconciliation" / (
                captured.intake_id.rsplit("/", 1)[-1] + ".md"
            )
            task = parse_markdown(task_path)
            task.frontmatter["requirements"][0]["pii_scan"]["source_checksum"] = "sha256:invalid"
            task_path.write_text(render_markdown(task.frontmatter, task.body), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PII receipt is invalid"):
                get_inbox_review(knowledge_root, captured.intake_id)
            invalid = list_inbox_review_queue(knowledge_root)
            self.assertEqual(len(invalid), 1)
            self.assertEqual(invalid[0]["status"], "invalid_receipt")
            self.assertEqual(invalid[0]["safe_next_action"], "repair_inbox_task_receipt")

    def test_mobile_phone_number_is_preserved_only_after_data_protection_review(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "담당자 연락처는 010-1234-5678", "manual",
                title="전화번호 포함", why_collected="PII 처리 회귀 검증",
                intended_use=["test"], idempotency_key="mobile-phone-standard-scan",
            )
            with self.assertRaisesRegex(ValueError, "requires review-data-protection"):
                complete_inbox_sensitivity_review(
                    knowledge_root, captured.intake_id, "inspector", "completed",
                    policy_ref="inbox-sensitivity/v1",
                    checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                    matched_categories=["mobile_phone_number"],
                    rationale="업무용 연락처라고만 판단해서는 보존할 수 없다.",
                )
            from circled_wiki.core.ingest import review_data_protection
            review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="승인된 협력업체 업무용 연락처다.",
            )
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)

            self.assertEqual(result["ingested_count"], 1)
            self.assertEqual(result["items"][0]["pii_scan_result"], "passed")
            evidence = (knowledge_root.parent / result["items"][0]["evidence_path"])
            self.assertIn("010-1234-5678", evidence.read_text(encoding="utf-8"))
            self.assertEqual(list_inbox_review_queue(knowledge_root), [])
            archived = list((
                knowledge_root.parent / "workspace" / "task" / ".archive" / "inbox_reconciliation"
            ).glob("*.md"))
            self.assertEqual(len(archived), 1)
            task = parse_markdown(archived[0]).frontmatter
            self.assertEqual(task["current"]["stage"], "evidence")
            self.assertEqual(task["current"]["status"], "completed")
            self.assertTrue(task["transitions"])

    def test_data_protection_review_masks_agent_identified_compensation_and_preserves_contact(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            compensation = "월 급여는 5,000,000원"
            captured = capture_document(
                knowledge_root, f"협력업체 담당자 연락처는 010-1234-5678이고 {compensation}이다.",
                "manual", title="협력업체 계약 정보", why_collected="민감정보 마스킹 회귀 검증",
                intended_use=["test"], idempotency_key="compensation-with-contact",
            )
            from circled_wiki.core.ingest import review_data_protection
            review = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="협력업체 업무 연락처는 보존하고 Agent가 식별한 급여 문구만 마스킹한다.",
                findings=[{"category": "compensation", "value": compensation}],
            )

            self.assertEqual(
                review["data_protection"]["agent_masked_findings"],
                [{"category": "compensation", "count": 1}],
            )
            inspected = parse_markdown(captured.inbox_path)
            self.assertNotIn(compensation, inspected.body)
            self.assertIn("010-1234-5678", inspected.body)
            self.assertNotIn(compensation, str(inspected.frontmatter["sensitivity_inspection"]))
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)
            evidence = knowledge_root.parent / result["items"][0]["evidence_path"]
            self.assertNotIn(compensation, evidence.read_text(encoding="utf-8"))
            self.assertIn("010-1234-5678", evidence.read_text(encoding="utf-8"))

    def test_data_protection_review_does_not_mask_legal_processing_or_decisions(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            legal_text = (
                "계약 해지 조건을 검토하고 협상 포지션을 결정한다. "
                "분쟁 대응 전략과 법률 자문 결과에 따라 규제기관 제출 문안을 확정한다."
            )
            captured = _capture_conversation(
                knowledge_root, legal_text, "manual", title="법무 처리 결정",
                why_collected="법무 업무 기록", intended_use=["내부 검토"],
                idempotency_key="legal-processing-is-not-sensitive",
            )
            from circled_wiki.core.ingest import read_conversation_intake, review_data_protection

            review = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="법률·계약·분쟁·규제 처리와 결정은 이 민감도 정책의 제한 대상이 아니다.",
            )
            _, content = read_conversation_intake(captured.inbox_path)

        self.assertEqual(review["sensitivity_review"], "not_applicable")
        self.assertEqual(review["data_protection"]["agent_masked_findings"], [])
        self.assertIn(legal_text, content)

    def test_data_protection_review_masks_only_explicit_unlawful_content(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            unlawful_text = "불법 행위 실행 지시: 증거를 삭제하고 감사를 회피하는 방법"
            captured = _capture_conversation(
                knowledge_root, f"정상적인 법률 검토와 {unlawful_text}", "manual",
                title="불법 실행 내용", why_collected="정책 경계 검증",
                intended_use=["내부 검토"], idempotency_key="unlawful-content-boundary",
            )
            from circled_wiki.core.ingest import read_conversation_intake, review_data_protection

            review = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="명시적인 불법 실행 지시만 해당 범위로 마스킹한다.",
                findings=[{"category": "unlawful_content", "value": unlawful_text}],
            )
            _, content = read_conversation_intake(captured.inbox_path)

        self.assertEqual(
            review["data_protection"]["agent_masked_findings"],
            [{"category": "unlawful_content", "count": 1}],
        )
        self.assertNotIn(unlawful_text, content)
        self.assertIn("정상적인 법률 검토", content)

    def test_data_protection_review_masks_unpublished_business_and_security_details(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            revenue = "미공개 매출·정산 금액은 12억원"
            security = "보안 솔루션 구성 상세는 내부 정책에 따라 비공개"
            captured = _capture_conversation(
                knowledge_root, f"{revenue}; {security}; 일반 입사·퇴사 일정", "manual",
                title="사업·보안 정책 경계", why_collected="정책 경계 검증",
                intended_use=["내부 검토"], idempotency_key="business-security-boundary",
            )
            from circled_wiki.core.ingest import read_conversation_intake, review_data_protection

            review = review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="미공개 사업정보와 보안 구성 상세만 해당 범위로 마스킹한다.",
                findings=[
                    {"category": "unpublished_business_information", "value": revenue},
                    {"category": "security_configuration", "value": security},
                ],
            )
            _, content = read_conversation_intake(captured.inbox_path)

        self.assertEqual(
            review["data_protection"]["agent_masked_findings"],
            [
                {"category": "unpublished_business_information", "count": 1},
                {"category": "security_configuration", "count": 1},
            ],
        )
        self.assertNotIn(revenue, content)
        self.assertNotIn(security, content)
        self.assertIn("일반 입사·퇴사 일정", content)

    def test_data_protection_review_reuses_one_pii_scan_after_agent_masking(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            compensation = "월 급여는 6,000,000원"
            captured = _capture_conversation(
                knowledge_root, f"협력업체 연락처 010-5555-6666, {compensation}", "manual",
                title="PII ordering", why_collected="ordering verification", intended_use=["test"],
                idempotency_key="pii-before-after-sensitivity",
            )
            from circled_wiki.core.ingest import read_conversation_intake, review_data_protection
            from circled_wiki.core.ingest import run_automatic_pii_scan as canonical_scan
            observed_contents = []

            def observe_scan(root, intake_id):
                result = canonical_scan(root, intake_id)
                _, content = read_conversation_intake(captured.inbox_path)
                observed_contents.append(content)
                return result

            with (
                patch("circled_wiki.core.ingest.run_automatic_pii_scan", side_effect=observe_scan),
                patch(
                    "circled_wiki.core.ingest._policy_candidates_for_inbox",
                    side_effect=AssertionError("review must use candidates from the single PII scan"),
                ),
            ):
                review_data_protection(
                    knowledge_root, captured.intake_id, "inspector", context="",
                    checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                    rationale="PII scan precedes semantic masking and is rebound after the change.",
                    findings=[{"category": "compensation", "value": compensation}],
                )
            _, final_content = read_conversation_intake(captured.inbox_path)

        self.assertEqual(len(observed_contents), 1)
        self.assertIn(compensation, observed_contents[0])
        self.assertNotIn(compensation, final_content)

    def test_reprocessing_review_uses_intake_uuid_when_legacy_checksum_is_stale(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "reviewed source", "manual", title="UUID queue",
                why_collected="review queue test", intended_use=["test"],
                idempotency_key="uuid-queue-reconciliation",
            )
            complete_inbox_sensitivity_review(
                knowledge_root, captured.intake_id, "human-reviewer", "completed",
                policy_ref="inbox-sensitivity/v1",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                matched_categories=["internal_business_context"],
                rationale="내부 보존 범위와 접근 제한 조치를 적용한다.",
            )
            queue_path = next((knowledge_root.parent / "workspace" / "task" / "inbox_reconciliation").glob("*.md"))
            queue = parse_markdown(queue_path)
            self.assertNotIn("source_checksum", queue.frontmatter)
            self.assertNotIn("source_checksum", queue.frontmatter["subject"])
            stale = dict(queue.frontmatter)
            legacy_checksum = captured.checksum
            stale["source_checksum"] = legacy_checksum
            stale["subject"] = {**stale["subject"], "source_checksum": legacy_checksum}
            queue_path.write_text(render_markdown(stale), encoding="utf-8")

            document = parse_markdown(captured.inbox_path)
            unsafe_content = "password=unsafe-test-value"
            document.frontmatter["checksum"] = (
                "sha256:" + hashlib.sha256(unsafe_content.encode("utf-8")).hexdigest()
            )
            captured.inbox_path.write_text(
                render_markdown(
                    document.frontmatter,
                    "# Inbox Document\n\n<!-- INBOX_CONTENT_START -->"
                    + unsafe_content
                    + "<!-- INBOX_CONTENT_END -->\n",
                ),
                encoding="utf-8",
            )
            from circled_wiki.core.ingest import run_automatic_pii_scan
            run_automatic_pii_scan(knowledge_root, captured.intake_id)
            from circled_wiki.core.ingest import review_data_protection
            review_data_protection(
                knowledge_root, captured.intake_id, "inspector", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="변경된 후보를 통합 Data Protection 단계에서 다시 확정한다.",
            )
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            masked_candidate = parse_markdown(captured.inbox_path)
            self.assertNotIn(unsafe_content, masked_candidate.body)
            self.assertNotEqual(masked_candidate.frontmatter["checksum"], legacy_checksum)
            result = ingest_accepted_inbox(knowledge_root)

            self.assertEqual(result["ingested_count"], 1)
            self.assertEqual(list_inbox_review_queue(knowledge_root), [])

    def test_pii_needs_review_blocks_then_resumes_and_archives_queue(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "safe replacement", "manual", title="PII review",
                why_collected="review queue test", intended_use=["test"],
                idempotency_key="review-queue-pii", sensitivity_review="not_applicable",
            )
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            self.assertEqual(list_inbox_review_queue(knowledge_root), [])
            blocked = record_inbox_pii_scan_receipt(
                knowledge_root, captured.intake_id, scanner="test", scanner_version="1",
                result="needs_review", reviewed_by="scanner", receipt="test://needs-review",
            )
            self.assertEqual(blocked["review_queue"]["status"], "awaiting_user")
            self.assertEqual(list_inbox_review_queue(knowledge_root)[0]["current_stage"], "data_protection")
            self.assertEqual(
                parse_markdown(captured.inbox_path).frontmatter["status"], "pending"
            )
            self.assertEqual(ingest_accepted_inbox(knowledge_root)["ingested_count"], 0)

            resumed = record_inbox_pii_scan_receipt(
                knowledge_root, captured.intake_id, scanner="test", scanner_version="2",
                result="masked", reviewed_by="human-reviewer", receipt="test://masked",
            )
            self.assertEqual(resumed["review_status"], "awaiting_user")
            from circled_wiki.core.ingest import review_data_protection
            review_data_protection(
                knowledge_root, captured.intake_id, "human-reviewer", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="외부 PII 결과를 통합 Data Protection 단계에서 재확정한다.",
            )
            accept_conversation_intake(knowledge_root, captured.intake_id, "inspector")
            result = ingest_accepted_inbox(knowledge_root)

            self.assertEqual(result["ingested_count"], 1)
            self.assertEqual(list_inbox_review_queue(knowledge_root), [])
            archived = list((knowledge_root.parent / "workspace" / "task" / ".archive" / "inbox_reconciliation").glob("*.md"))
            self.assertEqual(len(archived), 1)
            archived_task = parse_markdown(archived[0])
            self.assertEqual(archived_task.frontmatter["type"], "contract_task")
            self.assertEqual(
                archived_task.frontmatter["current"],
                {
                    "stage": "evidence", "status": "completed",
                    "actor": "evidence-ingest-agent",
                },
            )
            evidence = parse_markdown(knowledge_root.parent / result["items"][0]["evidence_path"])
            self.assertEqual(evidence.frontmatter["extensions"]["pii_scan"]["result"], "masked")
            self.assertEqual(
                evidence.frontmatter["extensions"]["inbox_review"]["reason_codes"],
                ["sensitivity_review_required", "pii_needs_review"],
            )
            self.assertEqual(
                evidence.frontmatter["extensions"]["inbox_review"]["decisions"][1]["decision"],
                "data_protection_not_applicable",
            )

    def test_inbox_pii_receipt_is_fixed_at_evidence_creation(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root, "masked content", "manual",
                title="Scanned source", why_collected="security",
                intended_use=["test"], idempotency_key="scan-before-evidence",
                sensitivity_review="not_applicable",
            )
            record_inbox_pii_scan_receipt(
                knowledge_root, captured.intake_id, scanner="test",
                scanner_version="1", result="passed", reviewed_by="security",
                receipt="test://scan",
            )
            from circled_wiki.core.ingest import review_data_protection
            review_data_protection(
                knowledge_root, captured.intake_id, "security", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="외부 PII 결과를 통합 Data Protection 단계에서 재확정한다.",
            )
            accept_conversation_intake(knowledge_root, captured.intake_id, "reviewer")
            result = ingest_accepted_inbox(knowledge_root)
            evidence_path = knowledge_root.parent / result["items"][0]["evidence_path"]
            evidence = parse_markdown(evidence_path)

            self.assertTrue(evidence.frontmatter["extensions"]["pii_scanned"])
            self.assertEqual(
                evidence.frontmatter["extensions"]["pii_scan"]["source_checksum"],
                evidence.frontmatter["checksum"],
            )

    def test_evidence_and_curation_queue_registration_are_atomic(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            source = knowledge_root / "inbox" / "manual" / "atomic.txt"
            source.parent.mkdir(parents=True)
            source.write_text("atomic evidence", encoding="utf-8")

            with patch(
                "circled_wiki.core.curation_queue.enqueue_curation_work",
                side_effect=OSError("queue unavailable"),
            ):
                with self.assertRaisesRegex(OSError, "queue unavailable"):
                    ingest_evidence(
                        knowledge_root, source, "manual",
                        why_collected="atomicity test", intended_use=["test"],
                    )

            self.assertEqual(list((knowledge_root / "evidence").rglob("*.md")), [])
            self.assertEqual(
                list((knowledge_root.parent / "workspace" / "task" / "curation_reconciliation").glob("*.md")),
                [],
            )

    def test_input_format_simulation_preserves_sources_and_gates(self):
        """Exercise planned conversation, URL, HTML, PDF, and Word input flows."""
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            conversation = capture_conversation(
                knowledge_root, "사용자: 최신 고객 응대 절차를 알려줘\n", "slack",
                title="고객 응대 절차 문의", why_collected="채널 문의와 답변 품질을 개선",
                intended_use=["customer-support"], idempotency_key="slack:thread-1",
                sensitivity_review="completed",
            )
            web_document = capture_document(
                knowledge_root, "<html><body><h1>배송 정책</h1></body></html>", "web",
                title="배송 정책 웹 페이지", why_collected="URL 제공 정책 원문을 검토",
                intended_use=["customer-support", "policy-review"], idempotency_key="web:delivery-policy:v1",
                source_url="https://example.test/policies/delivery",
                source_locator="retrieved_at=2026-07-15T09:00:00+09:00", captured_from="manual",
                sensitivity_review="completed",
            )
            pdf = capture_file(
                knowledge_root, b"%PDF-1.7\\nSimulated procedure source\\n", "support-procedure.pdf", "upload",
                title="고객센터 절차 PDF", why_collected="고객센터 절차 문의의 원문 근거",
                intended_use=["customer-support"], idempotency_key="upload:support-procedure:rev-1",
                source_locator="page=1", sensitivity_review="completed",
            )
            word = capture_file(
                knowledge_root, b"PK\\x03\\x04simulated-docx", "decision-record.docx", "upload",
                title="의사결정 기록 Word", why_collected="최근 결정 사항 문의의 원문 근거",
                intended_use=["decision-support"], idempotency_key="upload:decision-record:rev-1",
                sensitivity_review="completed",
            )

            inspection = inspect_inbox(knowledge_root)
            self.assertEqual(inspection["item_count"], 4)
            by_id = {item["intake_id"]: item for item in inspection["items"]}
            self.assertEqual(by_id[conversation.intake_id]["gate_status"], "ready_for_acceptance")
            self.assertEqual(by_id[web_document.intake_id]["content_type"], "document")
            self.assertEqual(by_id[pdf.intake_id]["content_type"], "file")
            self.assertEqual(by_id[word.intake_id]["gate_status"], "blocked")

            for captured in (conversation, web_document):
                acceptance = accept_conversation_intake(
                    knowledge_root, captured.intake_id, "simulated-human-reviewer"
                )
                self.assertEqual(acceptance["status"], "accepted")
                accepted = parse_markdown(captured.inbox_path)
                self.assertEqual(
                    accepted.frontmatter["inspection"]["actor"], "simulated-human-reviewer"
                )
            for captured in (pdf, word):
                record_inbox_pii_scan_receipt(
                    knowledge_root, captured.intake_id,
                    scanner="simulated-file-review", scanner_version="v1",
                    result="passed", reviewed_by="simulated-human-reviewer",
                    receipt=f"review://file/{captured.intake_id.rsplit('/', 1)[-1]}",
                )
                from circled_wiki.core.ingest import review_data_protection
                review_data_protection(
                    knowledge_root, captured.intake_id, "simulated-human-reviewer", context="",
                    checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                    rationale="외부 파일 원본을 별도 검토한 뒤 보존한다.",
                )
                acceptance = accept_conversation_intake(
                    knowledge_root, captured.intake_id, "simulated-human-reviewer"
                )
                self.assertEqual(acceptance["status"], "accepted")
            ingested = ingest_accepted_inbox(knowledge_root)
            self.assertEqual(ingested["ingested_count"], 4)
            self.assertEqual(ingested["failed_count"], 0)
            self.assertFalse(conversation.inbox_path.exists())
            self.assertEqual(len(list((knowledge_root / "inbox" / "upload").glob("*"))), 0)

            evidence_by_title = {}
            for item in ingested["items"]:
                evidence = parse_markdown(knowledge_root.parent / item["evidence_path"])
                evidence_by_title[evidence.frontmatter["title"]] = evidence
            self.assertEqual(
                evidence_by_title["배송 정책 웹 페이지"].frontmatter["source_ref"]["provider_url"],
                "https://example.test/policies/delivery",
            )
            pdf_manifest = evidence_by_title["고객센터 절차 PDF"]
            self.assertEqual(pdf_manifest.frontmatter["extensions"]["content_mode"], "external_file")
            pdf_original = pdf_manifest.path.parent / pdf_manifest.frontmatter["original_file"]
            self.assertEqual(pdf_original.read_bytes(), b"%PDF-1.7\\nSimulated procedure source\\n")
            self.assertEqual(
                evidence_by_title["의사결정 기록 Word"].frontmatter["extensions"]["content_mode"], "external_file"
            )

    def test_markdown_file_original_does_not_overwrite_evidence_manifest(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            fixture_reviewed_at = datetime.now(timezone.utc) - timedelta(days=1)
            fixture_review_due_at = fixture_reviewed_at + timedelta(days=30)
            content = b"# Synthetic fixture\n\nNo personal data.\n"
            captured = capture_file(
                knowledge_root,
                content,
                "safe-fixture.md",
                "fixture-test",
                title="Safe Markdown fixture",
                why_collected="Markdown file ingest regression",
                intended_use=["integration-test"],
                idempotency_key="safe-markdown-fixture-v1",
                sensitivity_review="not_applicable",
            )
            record_inbox_pii_scan_receipt(
                knowledge_root, captured.intake_id,
                scanner="simulated-file-review", scanner_version="v1",
                result="passed", reviewed_by="simulated-human-reviewer",
                receipt="review://file/safe-markdown-fixture",
            )

            from circled_wiki.core.ingest import review_data_protection
            review_data_protection(
                knowledge_root, captured.intake_id, "simulated-human-reviewer", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="외부 파일 원본을 별도 검토한 뒤 보존한다.",
            )
            accept_conversation_intake(
                knowledge_root, captured.intake_id, "simulated-human-reviewer"
            )

            ingested = ingest_accepted_inbox(knowledge_root)

            self.assertEqual(ingested["ingested_count"], 1)
            self.assertEqual(ingested["failed_count"], 0)
            evidence = parse_markdown(
                knowledge_root.parent / ingested["items"][0]["evidence_path"]
            )
            self.assertEqual(evidence.frontmatter["type"], "evidence")
            self.assertTrue(evidence.frontmatter["original_file"].endswith(".md.original"))
            original = evidence.path.parent / evidence.frontmatter["original_file"]
            self.assertEqual(original.read_bytes(), content)
            self.assertTrue(
                all(result.is_valid for result in validate_repository(knowledge_root))
            )

            # Simulate the curator's judgment that all four sources support one
            # reusable customer-support Runbook, then simulate owner review.
            evidence_ids = [item["evidence_id"] for item in ingested["items"]]
            proposal = propose_update(knowledge_root, evidence_ids[0])
            self.assertEqual(proposal["recommended_action"], "create_draft_bundle")
            draft = create_bundle(
                knowledge_root,
                domain="customer-support",
                slug="source-intake-simulation",
                title="고객센터 원문 수집 및 답변 절차",
                bundle_type="runbook",
                summary="검증된 원문을 수집하고 고객 문의에 출처와 함께 답변한다.",
                evidence_id=evidence_ids[0],
                body="# Procedure\n\n원문과 출처를 확인한 뒤 답변한다.\n",
                curated_by="simulated-curator",
                approved_review_id="review-simulated-owner-approval",
            )
            self.assertEqual(draft.frontmatter["status"], "draft")
            self.assertIn("source-intake-simulation", draft.frontmatter["tags"])
            approved = deepcopy(draft.frontmatter)
            approved["status"] = "active"
            approved["owners"] = ["simulated-knowledge-owner"]
            approved["evidence"] = evidence_ids
            approved["extensions"]["review_state"] = "approved"
            approved["extensions"]["governance"] = {
                "reviewed_at": fixture_reviewed_at.isoformat(),
                "review_due_at": fixture_review_due_at.isoformat(),
                "freshness_policy": "risk_based",
                "risk_tier": "medium",
                "source_volatility": "periodic",
                "validity_days": 30,
                "change_triggers": ["user_requested", "source_change"],
            }
            approved["extensions"]["workflow"] = {
                "workflow_id": "customer-source-intake",
                "version": 1,
                "execution_mode": "guided",
                "trigger_intents": ["고객센터 절차를 알려줘"],
                "applies_to": ["customer-support"],
                "excludes": [],
                "required_inputs": [{"name": "request", "description": "사용자 요청"}],
                "steps": [
                    {"id": "find-sources", "title": "관련 원문 검색", "kind": "action"},
                    {
                        "id": "approve-answer", "title": "답변 검토", "kind": "approval",
                        "approvers": ["simulated-human-owner"],
                    },
                    {"id": "send-answer", "title": "출처 포함 답변", "kind": "validation"},
                ],
                "approval_gates": ["approve-answer"],
                "completion_criteria": ["근거와 원문 링크가 포함된 답변을 제공한다."],
                "examples": {"successful": [], "failed": []},
                "learning": {
                    "maturity": "pilot",
                    "min_outcomes_for_review": 3,
                    "review_on_failure": True,
                    "review_on_feedback": True,
                },
            }
            with self.assertRaisesRegex(ValueError, "status transitions require"):
                apply_bundle_revision(
                    knowledge_root,
                    bundle_id=str(draft.frontmatter["id"]),
                    expected_revision=1,
                    proposed_frontmatter=approved,
                    body="# Procedure\n\n1. 원문을 검색한다.\n2. 검토한다.\n3. 출처와 함께 답변한다.\n",
                    actor="simulated-human-owner",
                )
            # This test's remaining channel assertions need an existing legacy
            # active Runbook fixture; construct it explicitly rather than using
            # the production revision API as a promotion shortcut.
            approved["status"] = "draft"
            updated = apply_bundle_revision(
                knowledge_root,
                bundle_id=str(draft.frontmatter["id"]),
                expected_revision=1,
                proposed_frontmatter=approved,
                body="# Procedure\n\n1. 원문을 검색한다.\n2. 검토한다.\n3. 출처와 함께 답변한다.\n",
                actor="simulated-human-owner",
            )
            fixture_data = dict(updated.frontmatter)
            fixture_data["status"] = "active"
            fixture_extensions = dict(fixture_data["extensions"])
            fixture_extensions.pop("curation", None)
            fixture_data["extensions"] = fixture_extensions
            updated.path.write_text(
                render_markdown(
                    fixture_data,
                    updated.body + "\n## Workflow Summary\n\n원문을 검색·검토한 뒤 출처와 함께 답변한다.\n",
                ),
                encoding="utf-8",
            )
            active = parse_markdown(updated.path)
            self.assertEqual(active.frontmatter["status"], "active")
            self.assertEqual(active.frontmatter["extensions"]["updated_by"], "simulated-human-owner")
            self.assertEqual(KnowledgeService(knowledge_root).propose_pending()["proposal_count"], 0)
            self.assertEqual(validate_repository(knowledge_root)[0].profile_errors, [])
            self.assertIn(
                active.frontmatter["id"],
                [hit.document_id for hit in search_knowledge(knowledge_root, "고객센터 절차")],
            )

            # Continue the same simulation through a Slack-like channel request,
            # human approval, Outcome capture, and a second Inbox pass.
            service = KnowledgeService(knowledge_root)
            answer = answer_knowledge_query(service, "고객센터 원문 수집")
            self.assertEqual(answer["answers"][0]["bundle_id"], active.frontmatter["id"])
            self.assertTrue(answer["answers"][0]["sources"])
            channel = prepare_channel_workflow(
                service,
                "고객센터 절차를 안내해줘",
                workflow_id="customer-source-intake",
                inputs={"request": "고객센터 절차 안내"},
            )
            self.assertEqual(channel["status"], "ready")
            task_id = channel["task_id"]
            service.record_task_step(
                task_id, "find-sources", status="completed", result="공식 원문을 찾았다.", actor="agent"
            )
            service.record_task_step(
                task_id, "approve-answer", status="approved", result="답변을 검토했다.", actor="simulated-human-owner"
            )
            service.record_task_step(
                task_id, "send-answer", status="completed", result="출처를 포함해 답변했다.", actor="agent"
            )
            outcome = service.record_outcome(
                task_id, status="completed", summary="고객센터 절차와 원문 출처를 제공했다.",
                feedback="출처 링크가 유용했다.",
            )
            self.assertEqual(outcome["next_action"], "inspect_and_accept_outcome_inbox")
            service.review_data_protection(
                outcome["intake_id"], "simulated-human-reviewer", context="",
                checks=["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                rationale="내부 업무 결과로 보존하며 접근 범위를 제한한다.",
            )
            service.accept_inbox(outcome["intake_id"], "simulated-human-owner")
            outcome_batch = service.ingest_accepted()
            self.assertTrue(outcome_batch["items"][0]["outcome_linked"])
            self.assertIn("improvement_task", outcome_batch["items"][0])
            self.assertEqual(service.propose_pending()["proposal_count"], 1)
    def test_external_document_preserves_source_provenance_through_inbox(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            captured = capture_document(
                knowledge_root,
                "# 변경된 고객 응대 절차\n\n승인 기준을 갱신한다.\n",
                "notion",
                title="고객 응대 절차 변경",
                why_collected="전일 변경된 절차를 지식화",
                intended_use=["customer-support"],
                idempotency_key="notion:page-123:2026-07-15T01:00:00Z",
                source_url="https://www.notion.so/page-123",
                source_locator="page_id=page-123",
                sensitivity_review="completed",
            )

            inspection = inspect_inbox(knowledge_root)
            self.assertEqual(inspection["items"][0]["gate_status"], "ready_for_acceptance")
            accept_conversation_intake(knowledge_root, captured.intake_id, "sync-inspector")
            ingested = ingest_accepted_inbox(knowledge_root)
            evidence = parse_markdown(knowledge_root.parent / ingested["items"][0]["evidence_path"])

            self.assertEqual(evidence.frontmatter["source_ref"]["provider_url"], "https://www.notion.so/page-123")
            self.assertEqual(evidence.frontmatter["source_ref"]["locator"], "page_id=page-123")
            self.assertEqual(evidence.frontmatter["source_ref"]["captured_from"], "sync")
            self.assertEqual(evidence.frontmatter["extensions"]["content_mode"], "embedded")

    def test_capture_lands_in_inbox_before_batch_ingests_and_proposes(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            content = "# Transcript\n\n## User\n\n메뉴 이미지를 만들어줘.\n"

            result = capture_conversation(
                knowledge_root,
                content,
                "codex",
                title="디지털 메뉴 제작 대화",
                why_collected="대화 기반 Runbook 개선",
                intended_use=["ai-digital-menu-image-production"],
                idempotency_key="thread-1:turns-1-2",
                thread_ref="thread-1",
                turn_from=1,
                turn_to=2,
                sensitivity_review="completed",
            )

            self.assertTrue(result.inbox_path.is_file())
            self.assertIn("/inbox/codex/", result.inbox_path.as_posix())
            self.assertEqual(list((knowledge_root / "evidence").rglob("*.md")), [])
            intake = parse_markdown(result.inbox_path)
            self.assertEqual(intake.frontmatter["type"], "inbox_item")
            self.assertEqual(intake.frontmatter["status"], "pending")
            self.assertIn(content, intake.body)

            inspection = inspect_inbox(knowledge_root)
            self.assertEqual(inspection["items"][0]["gate_status"], "ready_for_acceptance")
            KnowledgeService(knowledge_root).accept_inbox(result.intake_id, "inspection-agent")
            batch = ingest_accepted_inbox(knowledge_root)
            self.assertEqual(batch["ingested_count"], 1)
            self.assertFalse(result.inbox_path.exists())
            item = batch["items"][0]
            evidence_path = knowledge_root.parent / item["evidence_path"]
            self.assertNotIn("ingest-", evidence_path.name)
            evidence = parse_markdown(evidence_path)
            self.assertNotIn("original_file", evidence.frontmatter)
            self.assertEqual(evidence.frontmatter["extensions"]["content_mode"], "embedded")
            self.assertEqual(
                evidence.frontmatter["extensions"]["checksum_scope"], "document_body"
            )
            self.assertEqual(
                evidence.frontmatter["extensions"]["embedded_format_version"], 2
            )
            self.assertEqual(evidence.frontmatter["extensions"]["capture_fidelity"], "verbatim")
            self.assertTrue(evidence.frontmatter["extensions"]["pii_scanned"])
            self.assertEqual(evidence.body, content)
            self.assertEqual(validate_repository(knowledge_root)[0].profile_errors, [])

            proposal = propose_update(knowledge_root, item["evidence_id"])
            self.assertTrue(proposal["original_available"])
            self.assertIn("메뉴 이미지를 만들어줘", proposal["excerpt"])

            bundle = create_bundle(
                knowledge_root,
                domain="marketing",
                slug="digital-menu-image-production",
                title="디지털 메뉴 제작",
                bundle_type="runbook",
                summary="디지털 메뉴 이미지 제작 절차",
                evidence_id=item["evidence_id"],
                approved_review_id="review-test-approved",
            )
            proposal = propose_update(knowledge_root, item["evidence_id"])
            self.assertIn(
                bundle.frontmatter["id"],
                [candidate["id"] for candidate in proposal["candidate_bundles"]],
            )
            self.assertEqual(
                proposal["recommended_action"], "review_draft_bundle"
            )
            self.assertNotIn("draft_bundle_owner_missing", proposal["blocking_conditions"])

            evidence_path.write_text(
                evidence_path.read_text(encoding="utf-8").replace(
                    "메뉴 이미지를 만들어줘", "메뉴 이미지를 바꿔줘"
                ),
                encoding="utf-8",
            )
            invalid = validate_repository(knowledge_root)
            self.assertIn(
                "Evidence original checksum does not match manifest",
                [error for result in invalid for error in result.profile_errors],
            )

    def test_conversation_capture_idempotency_reuses_pending_inbox_item(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            arguments = {
                "title": "반복 대화",
                "why_collected": "중복 방지 검증",
                "intended_use": ["capture-test"],
                "idempotency_key": "thread-2:turns-1-1",
            }
            first = capture_conversation(knowledge_root, "동일한 대화", "codex", **arguments)
            repeated = capture_conversation(knowledge_root, "동일한 대화", "codex", **arguments)

            self.assertEqual(first.intake_id, repeated.intake_id)
            self.assertTrue(repeated.reused)
            self.assertEqual(
                len(list((knowledge_root / "inbox" / "codex").glob("*.md"))), 1
            )
            intake = parse_markdown(first.inbox_path)
            self.assertEqual(
                intake.frontmatter["sensitivity_review"],
                "required",
            )

    def test_conversation_capture_rejects_unsafe_provider_before_creating_inbox(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            with self.assertRaisesRegex(ValueError, "provider must contain"):
                capture_conversation(
                    knowledge_root,
                    "대화",
                    "../outside",
                    title="잘못된 소스",
                    why_collected="경로 검증",
                    intended_use=["capture-test"],
                    idempotency_key="unsafe-provider",
                )
            self.assertFalse((knowledge_root / "inbox").exists())

    def test_conversation_capture_conflict_identifies_existing_intake_without_content(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            first = capture_conversation(
                knowledge_root, "first transcript", "codex", title="Conflict test",
                why_collected="recovery response verification", intended_use=["capture-test"],
                idempotency_key="thread-conflict:turns-1-1",
            )
            with self.assertRaises(CaptureIdempotencyConflict) as raised:
                capture_conversation(
                    knowledge_root, "changed transcript", "codex", title="Conflict test",
                    why_collected="recovery response verification", intended_use=["capture-test"],
                    idempotency_key="thread-conflict:turns-1-1",
                )
            payload = raised.exception.as_dict(knowledge_root.parent)
            self.assertEqual(payload["error"], "idempotency_checksum_conflict")
            self.assertEqual(payload["existing_intake_id"], first.intake_id)
            self.assertEqual(
                payload["existing_inbox_path"],
                first.inbox_path.resolve().relative_to(knowledge_root.parent.resolve()).as_posix(),
            )
            self.assertNotIn("first transcript", str(payload))

    def test_conversation_capture_reuses_ingested_evidence_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            service = KnowledgeService(knowledge_root)
            first = capture_conversation(
                knowledge_root, "preserved transcript", "codex",
                title="Lifecycle idempotency", why_collected="lifecycle test",
                intended_use=["capture-test"], idempotency_key="lifecycle-key",
                sensitivity_review="completed",
            )
            accept_conversation_intake(knowledge_root, first.intake_id, "reviewer")
            ingested = ingest_accepted_inbox(knowledge_root)["items"][0]

            repeated = service.capture_conversation(
                "preserved transcript", "codex", title="Lifecycle idempotency",
                why_collected="lifecycle test", intended_use=["capture-test"],
                idempotency_key="lifecycle-key",
            )
            self.assertTrue(repeated["reused"])
            self.assertEqual(repeated["status"], "ingested")
            self.assertEqual(repeated["evidence_id"], ingested["evidence_id"])
            self.assertIsNone(repeated["intake_id"])

            with self.assertRaises(CaptureIdempotencyConflict) as raised:
                service.capture_conversation(
                    "changed transcript", "codex", title="Lifecycle idempotency",
                    why_collected="lifecycle test", intended_use=["capture-test"],
                    idempotency_key="lifecycle-key",
                )
            payload = raised.exception.as_dict(knowledge_root.parent)
            self.assertEqual(payload["existing_evidence_id"], ingested["evidence_id"])
            self.assertNotIn("preserved transcript", str(payload))

    def test_concurrent_capture_serializes_one_idempotency_key(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            service = KnowledgeService(knowledge_root)
            barrier = threading.Barrier(2)

            def submit(content: str) -> str:
                barrier.wait()
                try:
                    service.capture_conversation(
                        content, "codex", title="Concurrent capture",
                        why_collected="race test", intended_use=["capture-test"],
                        idempotency_key="concurrent-key",
                    )
                    return "created"
                except CaptureIdempotencyConflict:
                    return "conflict"

            with ThreadPoolExecutor(max_workers=2) as executor:
                outcomes = list(executor.map(submit, ["version one", "version two"]))

            self.assertCountEqual(outcomes, ["created", "conflict"])
            self.assertEqual(
                len(list((knowledge_root / "inbox" / "codex").glob("*.md"))), 1
            )

    def test_curation_rejects_unrelated_draft_candidate_and_suggests_runbook(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            unrelated = capture_conversation(
                knowledge_root, "CLI inbox test", "test", title="CLI inbox test",
                why_collected="test", intended_use=["system-test"], idempotency_key="unrelated",
                sensitivity_review="completed",
            )
            accept_conversation_intake(knowledge_root, unrelated.intake_id, "reviewer")
            unrelated_evidence = ingest_accepted_inbox(knowledge_root)["items"][0]["evidence_id"]
            create_bundle(
                knowledge_root, domain="system-tests", slug="cli-inbox", title="CLI Inbox Test Runbook",
                bundle_type="runbook", summary="Unrelated test procedure", evidence_id=unrelated_evidence,
                approved_review_id="review-test-approved",
            )
            procedure = capture_conversation(
                knowledge_root, "메뉴 이미지 제작 절차를 반복 실행하고 검토한다.", "test",
                title="메뉴 이미지 제작 절차", why_collected="procedure", 
                intended_use=["ai-digital-menu-image-production", "operations-runbook"],
                idempotency_key="menu-procedure", sensitivity_review="completed",
            )
            accept_conversation_intake(knowledge_root, procedure.intake_id, "reviewer")
            procedure_evidence = ingest_accepted_inbox(knowledge_root)["items"][0]["evidence_id"]
            proposal = propose_update(knowledge_root, procedure_evidence)
            self.assertEqual(proposal["candidate_bundles"], [])
            self.assertEqual(proposal["recommended_action"], "create_draft_bundle")
            self.assertEqual(proposal["suggested_bundle_type"], "runbook")

    def test_moves_inbox_original_and_creates_valid_manifest(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            source = inbox / "Refund Policy.txt"
            source.write_text("original source", encoding="utf-8")

            result = ingest_evidence(
                knowledge_root,
                source,
                "manual",
                why_collected="환불 정책 Bundle을 갱신하기 위한 근거",
                intended_use=["refund-policy"],
                source_url="https://source.example/refund",
                source_locator="page=12;section=Refund",
                captured_at=datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc),
            )

            manifest = parse_markdown(result.manifest_path)
            self.assertFalse(source.exists())
            self.assertTrue(result.original_path.exists())
            self.assertEqual(manifest.frontmatter["id"], result.evidence_id)
            self.assertEqual(manifest.frontmatter["original_file"], result.original_path.name)
            self.assertNotIn("status", manifest.frontmatter)
            self.assertNotIn("processed_at", manifest.frontmatter)
            self.assertEqual(manifest.frontmatter["extensions"]["availability"], "available")
            self.assertEqual(
                manifest.frontmatter["extensions"]["capture_context"]["intended_use"],
                ["refund-policy"],
            )

            bundle = create_bundle(
                knowledge_root,
                domain="cs",
                slug="refund-policy",
                title="Refund Policy",
                bundle_type="policy",
                summary="Refund rules.",
                evidence_id=result.evidence_id,
            )
            runbook = create_bundle(
                knowledge_root,
                domain="cs",
                slug="refund-processing",
                title="Refund Processing",
                bundle_type="runbook",
                summary="Refund workflow draft.",
                evidence_id=result.evidence_id,
                approved_review_id="review-test-approved",
            )
            hits = search_knowledge(
                knowledge_root, "refund", {"type": "policy", "status": "draft"}
            )

            self.assertEqual(bundle.frontmatter["evidence"], [result.evidence_id])
            self.assertEqual(runbook.path.parent.name, "runbooks")
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0].document_id, bundle.frontmatter["id"])

            proposal = propose_update(knowledge_root, result.evidence_id)
            self.assertEqual(proposal["evidence_id"], result.evidence_id)
            self.assertTrue(proposal["original_available"])
            self.assertIn("original source", proposal["excerpt"])
            sources = KnowledgeService(knowledge_root).read_bundle(bundle.frontmatter["id"])["sources"]
            self.assertEqual(sources[0]["kind"], "original_source")
            self.assertEqual(sources[0]["uri"], "https://source.example/refund")
            self.assertEqual(sources[0]["locator"], "page=12;section=Refund")
            bundle_data = dict(bundle.frontmatter)
            bundle_data["extensions"] = dict(bundle_data["extensions"], visibility="restricted")
            bundle.path.write_text(render_markdown(bundle_data, bundle.body), encoding="utf-8")
            service = KnowledgeService(knowledge_root)
            self.assertIsNone(service.read_bundle(bundle.frontmatter["id"]))
            self.assertNotIn(
                bundle.frontmatter["id"],
                [result["id"] for result in service.search_knowledge("refund")],
            )
            self.assertFalse(
                any(
                    "does not reference" in warning
                    for validation in validate_repository(knowledge_root)
                    for warning in validation.warnings
                )
            )

    def test_keeps_oversized_original_in_raw_for_external_storage_handling(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            source = inbox / "large.bin"
            source.write_bytes(b"0" * (MAX_GIT_EVIDENCE_BYTES + 1))

            with self.assertRaisesRegex(ValueError, "larger than 10 MiB"):
                ingest_evidence(
                    knowledge_root,
                    source,
                    "manual",
                    why_collected="대용량 Evidence 처리 검증",
                    intended_use=["ingest-validation"],
                )

            self.assertFalse(source.exists())
            self.assertEqual(len(list((knowledge_root / ".raw").glob("*.bin"))), 1)
            self.assertFalse((knowledge_root / "evidence" / "manual").exists())

    def test_operator_curation_path_is_scoped_revisioned_and_reversible(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            (inbox / "policy.txt").write_text("approved source", encoding="utf-8")
            service = KnowledgeService(knowledge_root)
            evidence_result = ingest_evidence(
                knowledge_root, inbox / "policy.txt", "manual",
                why_collected="운영 정책 초안 근거", intended_use=["operations-policy"],
            )
            evidence = {
                "evidence_id": evidence_result.evidence_id,
                "manifest_path": evidence_result.manifest_path.relative_to(
                    knowledge_root.resolve().parent
                ).as_posix(),
            }
            evidence_path = evidence_result.manifest_path
            evidence_before_bundle = evidence_path.read_bytes()
            draft = service.create_draft_bundle(
                domain="operations", slug="operations-policy", title="Operations Policy",
                bundle_type="policy", summary="Initial summary.",
                evidence_id=str(evidence["evidence_id"]), body="# Policy\n\nInitial.\n",
                actor="hermes-curator", tags=["operations", "policy"],
            )
            self.assertIn("operations-policy", draft["frontmatter"]["tags"])
            self.assertEqual(evidence_path.read_bytes(), evidence_before_bundle)
            proposal = dict(draft["frontmatter"])
            proposal["summary"] = "Reviewed summary."
            proposal["tags"] = ["operations", "policy", "reviewed"]
            updated = service.apply_bundle_revision(
                str(draft["id"]), expected_revision=1, frontmatter=proposal,
                body="# Policy\n\nReviewed.\n", actor="verification-agent",
            )

            self.assertEqual(updated["frontmatter"]["extensions"]["knowledge_revision"], 2)
            self.assertEqual(
                updated["frontmatter"]["tags"],
                ["bundles", "policy", "operations", "reviewed", "operations-policy"],
            )
            self.assertEqual(updated["frontmatter"]["extensions"]["updated_by"], "verification-agent")
            self.assertIn("Reviewed.", updated["body"])
            evidence_manifest = parse_markdown(
                knowledge_root.parent / str(evidence["manifest_path"])
            )
            self.assertNotIn("curated_into", evidence_manifest.frontmatter)
            self.assertEqual(evidence_path.read_bytes(), evidence_before_bundle)

            with self.assertRaisesRegex(ValueError, "revision conflict"):
                service.apply_bundle_revision(
                    str(draft["id"]), expected_revision=1, frontmatter=proposal,
                    body="stale", actor="stale-agent",
                )
            invalid = dict(updated["frontmatter"])
            invalid["status"] = "active"
            with self.assertRaisesRegex(ValueError, "status transitions require"):
                service.apply_bundle_revision(
                    str(draft["id"]), expected_revision=2, frontmatter=invalid,
                    body="invalid activation", actor="hermes-curator",
                )
            restored = service.read_bundle(str(draft["id"]))
            self.assertEqual(restored["frontmatter"]["status"], "draft")
            self.assertEqual(restored["frontmatter"]["extensions"]["knowledge_revision"], 2)

    def test_bundle_path_segments_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            source = inbox / "source.txt"
            source.write_text("source", encoding="utf-8")
            evidence = ingest_evidence(
                knowledge_root, source, "manual",
                why_collected="경로 제한 검증", intended_use=["test"],
            )
            with self.assertRaisesRegex(ValueError, "safe lowercase"):
                create_bundle(
                    knowledge_root, domain="../outside", slug="escape",
                    title="Escape", bundle_type="guide", summary="Escape test",
                    evidence_id=evidence.evidence_id,
                )

    def test_internal_ingest_idempotency_reuses_same_evidence_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            source = inbox / "batch.txt"
            source.write_text("version one", encoding="utf-8")
            first = ingest_evidence(
                knowledge_root, source, "batch", why_collected="정기 Batch 수집",
                intended_use=["batch-policy"], captured_from="sync",
                idempotency_key="notion:page-123:revision-1",
            )
            source.write_text("version one", encoding="utf-8")
            repeated = ingest_evidence(
                knowledge_root, source, "batch", why_collected="정기 Batch 재실행",
                intended_use=["batch-policy"], captured_from="sync",
                idempotency_key="notion:page-123:revision-1",
            )

            self.assertEqual(repeated.evidence_id, first.evidence_id)
            self.assertTrue(repeated.reused)
            self.assertFalse(source.exists())
            self.assertEqual(
                len(list((knowledge_root / "evidence" / "batch").rglob("*.md"))), 1
            )

            source.write_text("changed content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different checksum"):
                ingest_evidence(
                    knowledge_root, source, "batch", why_collected="잘못된 키 재사용",
                    intended_use=["batch-policy"], captured_from="sync",
                    idempotency_key="notion:page-123:revision-1",
                )
