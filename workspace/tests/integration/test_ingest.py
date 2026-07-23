from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import tempfile
import threading
import unittest
from pathlib import Path

from knowledge_os.core.frontmatter import parse_markdown, render_markdown
from knowledge_os.core.ingest import (
    CaptureIdempotencyConflict,
    MAX_GIT_EVIDENCE_BYTES,
    accept_conversation_intake,
    capture_conversation,
    capture_document,
    capture_file,
    ingest_evidence,
)
from knowledge_os.core.repository import apply_bundle_revision, create_bundle
from knowledge_os.core.curator import propose_update
from knowledge_os.core.search import search_knowledge
from knowledge_os.core.service import KnowledgeService
from knowledge_os.core.validator import validate_repository
from knowledge_os.integrations.channel import answer_knowledge_query, prepare_channel_workflow
from knowledge_os.worker.jobs import ingest_accepted_inbox, inspect_inbox


class IngestEvidenceTests(unittest.TestCase):
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
            self.assertEqual(by_id[word.intake_id]["gate_status"], "ready_for_acceptance")

            for captured in (conversation, web_document, pdf, word):
                acceptance = accept_conversation_intake(
                    knowledge_root, captured.intake_id, "simulated-human-reviewer"
                )
                self.assertEqual(acceptance["status"], "accepted")
                accepted = parse_markdown(captured.inbox_path)
                self.assertEqual(
                    accepted.frontmatter["inspection"]["actor"], "simulated-human-reviewer"
                )
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
            )
            self.assertEqual(draft.frontmatter["status"], "draft")
            approved = deepcopy(draft.frontmatter)
            approved["status"] = "active"
            approved["owners"] = ["simulated-knowledge-owner"]
            approved["evidence"] = evidence_ids
            approved["extensions"]["review_state"] = "approved"
            approved["extensions"]["governance"] = {
                "reviewed_at": "2026-07-01T09:00:00+09:00",
                "review_due_at": "2026-07-31T09:00:00+09:00",
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
            active = apply_bundle_revision(
                knowledge_root,
                bundle_id=str(draft.frontmatter["id"]),
                expected_revision=1,
                proposed_frontmatter=approved,
                body="# Procedure\n\n1. 원문을 검색한다.\n2. 검토한다.\n3. 출처와 함께 답변한다.\n",
                actor="simulated-human-owner",
            )
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
            service.review_inbox_sensitivity(
                outcome["intake_id"], "simulated-human-reviewer", "completed"
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
                evidence.frontmatter["extensions"]["checksum_scope"], "original_content"
            )
            self.assertEqual(evidence.frontmatter["extensions"]["capture_fidelity"], "verbatim")
            self.assertFalse(evidence.frontmatter["extensions"]["pii_scanned"])
            self.assertIn(content, evidence.body)
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
            )
            proposal = propose_update(knowledge_root, item["evidence_id"])
            self.assertIn(
                bundle.frontmatter["id"],
                [candidate["id"] for candidate in proposal["candidate_bundles"]],
            )
            self.assertEqual(
                proposal["recommended_action"], "assign_owner_and_review_draft"
            )
            self.assertIn("draft_bundle_owner_missing", proposal["blocking_conditions"])

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
                idempotency_key="lifecycle-key", sensitivity_review="completed",
            )
            self.assertTrue(repeated["reused"])
            self.assertEqual(repeated["status"], "ingested")
            self.assertEqual(repeated["evidence_id"], ingested["evidence_id"])
            self.assertIsNone(repeated["intake_id"])

            with self.assertRaises(CaptureIdempotencyConflict) as raised:
                service.capture_conversation(
                    "changed transcript", "codex", title="Lifecycle idempotency",
                    why_collected="lifecycle test", intended_use=["capture-test"],
                    idempotency_key="lifecycle-key", sensitivity_review="completed",
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
            self.assertEqual(manifest.frontmatter["status"], "new")
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

            with self.assertRaisesRegex(ValueError, "stay inside"):
                service.ingest_evidence(
                    "../outside.txt", "manual",
                    why_collected="경로 제한 검증", intended_use=["policy"],
                )
            evidence = service.ingest_evidence(
                "policy.txt", "manual",
                why_collected="운영 정책 초안 근거", intended_use=["operations-policy"],
            )
            draft = service.create_draft_bundle(
                domain="operations", slug="operations-policy", title="Operations Policy",
                bundle_type="policy", summary="Initial summary.",
                evidence_id=str(evidence["evidence_id"]), body="# Policy\n\nInitial.\n",
                actor="hermes-curator",
            )
            proposal = dict(draft["frontmatter"])
            proposal["summary"] = "Reviewed summary."
            updated = service.apply_bundle_revision(
                str(draft["id"]), expected_revision=1, frontmatter=proposal,
                body="# Policy\n\nReviewed.\n", actor="verification-agent",
            )

            self.assertEqual(updated["frontmatter"]["extensions"]["knowledge_revision"], 2)
            self.assertEqual(updated["frontmatter"]["extensions"]["updated_by"], "verification-agent")
            self.assertIn("Reviewed.", updated["body"])
            evidence_manifest = parse_markdown(
                knowledge_root.parent / str(evidence["manifest_path"])
            )
            self.assertIn(draft["id"], evidence_manifest.frontmatter["curated_into"])

            with self.assertRaisesRegex(ValueError, "revision conflict"):
                service.apply_bundle_revision(
                    str(draft["id"]), expected_revision=1, frontmatter=proposal,
                    body="stale", actor="stale-agent",
                )
            invalid = dict(updated["frontmatter"])
            invalid["status"] = "active"
            with self.assertRaisesRegex(ValueError, "validation failed"):
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

    def test_batch_idempotency_reuses_same_evidence_and_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            knowledge_root = Path(temp_directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            service = KnowledgeService(knowledge_root)
            source = inbox / "batch.txt"
            source.write_text("version one", encoding="utf-8")
            first = service.ingest_evidence(
                "batch.txt", "batch", why_collected="정기 Batch 수집",
                intended_use=["batch-policy"], captured_from="sync",
                idempotency_key="notion:page-123:revision-1",
            )
            source.write_text("version one", encoding="utf-8")
            repeated = service.ingest_evidence(
                "batch.txt", "batch", why_collected="정기 Batch 재실행",
                intended_use=["batch-policy"], captured_from="sync",
                idempotency_key="notion:page-123:revision-1",
            )

            self.assertEqual(repeated["evidence_id"], first["evidence_id"])
            self.assertTrue(repeated["reused"])
            self.assertFalse(source.exists())
            self.assertEqual(
                len(list((knowledge_root / "evidence" / "batch").rglob("*.md"))), 1
            )

            source.write_text("changed content", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "different checksum"):
                service.ingest_evidence(
                    "batch.txt", "batch", why_collected="잘못된 키 재사용",
                    intended_use=["batch-policy"], captured_from="sync",
                    idempotency_key="notion:page-123:revision-1",
                )
