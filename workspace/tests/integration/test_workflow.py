import tempfile
import unittest
import json
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from knowledge_os.core.frontmatter import parse_markdown, render_markdown
from knowledge_os.core.evidence import evidence_original_bytes
from knowledge_os.core.service import KnowledgeService
from knowledge_os.core.validator import validate_document
from knowledge_os.integrations.channel import answer_knowledge_query, prepare_channel_workflow


class WorkflowExecutionTests(unittest.TestCase):
    def _create_repository(self, directory: str) -> tuple[Path, str]:
        knowledge_root = Path(directory) / "knowledge"
        now = datetime.now(timezone.utc)
        reviewed_at = (now - timedelta(days=1)).isoformat(timespec="seconds")
        review_due_at = (now + timedelta(days=29)).isoformat(timespec="seconds")
        evidence_uuid = str(uuid4())
        bundle_uuid = str(uuid4())
        evidence_id = f"evidence://example-org/manual/2026/07/14/{evidence_uuid}"
        bundle_id = f"knowledge://example-org/marketing/poster-production_{bundle_uuid}"
        evidence_path = (
            knowledge_root / "evidence" / "manual" / "2026" / "07" / "14"
            / f"poster-source_{evidence_uuid}.md"
        )
        evidence_path.parent.mkdir(parents=True)
        evidence_path.write_text(
            render_markdown(
                {
                    "type": "evidence",
                    "id": evidence_id,
                    "title": "Poster workflow source",
                    "source_uuid": evidence_uuid,
                    "provider": "manual",
                    "source_ref": {"provider": "manual", "captured_from": "manual"},
                    "captured_at": now.isoformat(timespec="seconds"),
                    "status": "processed",
                    "checksum": "sha256:" + hashlib.sha256(b"source").hexdigest(),
                    "original_file": f"poster-source_{evidence_uuid}.txt",
                    "original_file_git_tracked": True,
                    "curated_into": [bundle_id],
                    "extensions": {
                        "availability": "available",
                        "capture_context": {
                            "why_collected": "포스터 제작 Workflow를 공식화하기 위한 근거",
                            "intended_use": ["poster-production"],
                        },
                        "visibility": "internal",
                        "storage": {"class": "git"},
                    },
                }
            ),
            encoding="utf-8",
        )
        (evidence_path.parent / f"poster-source_{evidence_uuid}.txt").write_text(
            "source", encoding="utf-8"
        )
        bundle_path = (
            knowledge_root / "bundles" / "marketing" / "runbooks"
            / f"poster-production_{bundle_uuid}.md"
        )
        bundle_path.parent.mkdir(parents=True)
        bundle_path.write_text(
            render_markdown(
                {
                    "type": "runbook",
                    "id": bundle_id,
                    "bundle_uuid": bundle_uuid,
                    "title": "포스터 이미지 제작",
                    "status": "active",
                    "summary": "포스터 요청을 확인하고 제작 결과를 검증한다.",
                    "updated_at": "2026-07-14T00:00:00+00:00",
                    "owners": ["marketing-owner"],
                    "tags": ["포스터", "이미지", "디자인"],
                    "evidence": [evidence_id],
                    "extensions": {
                        "visibility": "internal",
                        "knowledge_revision": 1,
                        "governance": {
                            "reviewed_at": reviewed_at,
                            "review_due_at": review_due_at,
                            "freshness_policy": "risk_based",
                            "risk_tier": "high",
                            "source_volatility": "periodic",
                            "validity_days": 30,
                            "change_triggers": ["user_requested", "source_change"],
                        },
                        "workflow": {
                            "workflow_id": "poster-production",
                            "version": 1,
                            "execution_mode": "guided",
                            "trigger_intents": ["포스터 이미지를 만들고 싶다"],
                            "applies_to": ["internal-marketing"],
                            "excludes": [],
                            "required_inputs": [
                                {"name": "audience", "description": "대상 고객"},
                                {"name": "channel", "description": "게시 채널"},
                            ],
                            "steps": [
                                {"id": "collect-inputs", "title": "입력 확인", "kind": "action"},
                                {"id": "approve-brief", "title": "브리프 승인", "kind": "approval"},
                                {"id": "validate-output", "title": "결과 검증", "kind": "validation"},
                            ],
                            "approval_gates": ["approve-brief"],
                            "completion_criteria": ["요청 규격과 브랜드 기준을 충족한다"],
                            "examples": {"successful": [], "failed": []},
                            "learning": {
                                "maturity": "pilot",
                                "min_outcomes_for_review": 3,
                                "review_on_failure": True,
                                "review_on_feedback": True,
                            },
                        },
                    },
                },
                "# Procedure\n\nFollow the approved workflow.\n",
            ),
            encoding="utf-8",
        )
        return knowledge_root, bundle_id

    def test_active_runbook_requires_executable_workflow_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            bundle_uuid = str(uuid4())
            evidence_uuid = str(uuid4())
            path = root / "bundles" / "ops" / "runbooks" / f"broken_{bundle_uuid}.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                render_markdown(
                    {
                        "type": "runbook",
                        "id": f"knowledge://example-org/ops/broken_{bundle_uuid}",
                        "bundle_uuid": bundle_uuid,
                        "title": "Broken",
                        "status": "active",
                        "summary": "Missing workflow",
                        "updated_at": "2026-07-14T00:00:00+00:00",
                        "owners": ["ops-owner"],
                        "evidence": [f"evidence://example-org/manual/2026/07/14/{evidence_uuid}"],
                        "extensions": {
                            "governance": {
                                "reviewed_at": "2026-07-14T00:00:00+00:00",
                                "review_due_at": "2026-07-18T00:00:00+00:00",
                                "freshness_policy": "risk_based",
                                "risk_tier": "critical",
                                "source_volatility": "volatile",
                                "validity_days": 4,
                                "change_triggers": ["user_requested"],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            result = validate_document(path, root)
        self.assertIn("active Runbook must define extensions.workflow", result.profile_errors)

    def test_prepares_runtime_task_and_records_outcome_as_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, bundle_id = self._create_repository(directory)
            service = KnowledgeService(knowledge_root)

            matches = service.find_workflow("포스터 이미지를 만들고 싶어")
            query = answer_knowledge_query(service, "포스터 이미지 제작")
            prepared = prepare_channel_workflow(
                service,
                "여름 이벤트 포스터를 만들어줘",
                workflow_id="poster-production",
                inputs={"audience": "가족 캠퍼"},
            )
            task = service.get_task(prepared["task_id"])

            self.assertEqual(matches[0]["id"], bundle_id)
            self.assertEqual(query["mode"], "knowledge_query")
            self.assertEqual(query["answers"][0]["sources"][0]["kind"], "preserved_evidence")
            self.assertEqual(prepared["questions"], [{"input": "channel", "question": "게시 채널"}])
            self.assertEqual(task["status"], "awaiting_input")
            self.assertEqual(task["missing_inputs"], ["channel"])
            self.assertEqual(task["owners"], ["marketing-owner"])
            self.assertEqual(task["applies_to"], ["internal-marketing"])
            self.assertEqual(task["learning"]["maturity"], "pilot")
            self.assertTrue((Path(directory) / ".runtime" / "tasks" / f"{task['task_id']}.json").is_file())
            self.assertFalse((knowledge_root / ".runtime").exists())

            with self.assertRaisesRegex(ValueError, "all workflow steps"):
                service.record_outcome(
                    task["task_id"], status="completed", summary="too early"
                )

            task = service.update_task_inputs(task["task_id"], {"channel": "모바일 앱"})
            self.assertEqual(task["status"], "ready")
            service.record_task_step(
                task["task_id"],
                "collect-inputs",
                status="completed",
                result="필수 입력을 확인했다.",
                actor="hermes",
            )
            with self.assertRaisesRegex(ValueError, "approval actor must differ"):
                service.record_task_step(
                    task["task_id"],
                    "approve-brief",
                    status="approved",
                    result="작업 수행자가 스스로 승인했다.",
                    actor="hermes",
                )
            with self.assertRaisesRegex(ValueError, "not authorized"):
                service.record_task_step(
                    task["task_id"],
                    "approve-brief",
                    status="approved",
                    result="허용 목록에 없는 사용자가 승인했다.",
                    actor="unrelated-user",
                )
            service.record_task_step(
                task["task_id"],
                "approve-brief",
                status="approved",
                result="마케팅 담당자가 브리프를 승인했다.",
                actor="marketing-owner",
            )
            task = service.record_task_step(
                task["task_id"],
                "validate-output",
                status="completed",
                result="규격과 브랜드 기준을 통과했다.",
                actor="hermes",
            )
            self.assertEqual(task["status"], "awaiting_outcome")

            outcome = service.record_outcome(
                task["task_id"],
                status="completed",
                summary="포스터 시안을 생성하고 사용자 승인을 받았다.",
                feedback="모바일 문구 가독성이 좋았다.",
                learnings=["모바일 채널에서는 큰 제목을 우선한다."],
                artifacts=[
                    {
                        "name": "poster.png",
                        "uri": "internal-storage://design/poster.png",
                        "availability": "metadata_only",
                    }
                ],
                decisions=[{
                    "decision": "모바일 포스터 시안을 채택한다.",
                    "decided_by": "marketing-owner",
                    "rationale": "브랜드 기준을 충족했다.",
                    "evidence_ids": [parse_markdown(
                        next((knowledge_root / "bundles" / "marketing" / "runbooks").glob("*.md"))
                    ).frontmatter["evidence"][0]],
                }],
                action_items=[{
                    "title": "다음 캠페인 템플릿 반영", "owner": "marketing-owner",
                    "completion_criteria": "새 템플릿이 Validator를 통과한다.",
                }],
                open_questions=[{
                    "question": "외부 광고 채널에도 적용할 것인가?", "owner": "marketing-owner",
                }],
            )
            self.assertEqual(outcome["workflow_bundle_id"], bundle_id)
            self.assertTrue(outcome["intake_id"].startswith("inbox://example-org/hermes/"))
            inspection = service.inspect_inbox()
            self.assertEqual(inspection["items"][0]["gate_status"], "blocked")
            service.review_inbox_sensitivity(
                outcome["intake_id"], "simulated-human-reviewer", "completed"
            )
            service.accept_inbox(outcome["intake_id"], "simulated-human-approver")
            ingested = service.ingest_accepted()
            outcome_item = ingested["items"][0]
            self.assertTrue(outcome_item["outcome_linked"])
            self.assertTrue(outcome_item["evidence_id"].startswith("evidence/example-org/"))
            proposal = service.propose_update(outcome_item["evidence_id"])
            self.assertEqual(
                [item["target_type"] for item in proposal["promotion_candidates"]],
                ["runbook", "guide", "workflow-example"],
            )
            self.assertEqual(outcome_item["learning_signal"]["triggers"], ["user_feedback"])
            self.assertIn("improvement_task", outcome_item)
            duplicate_refresh = service.prepare_runbook_refresh(
                "poster-production",
                "피드백 반영 여부를 검토해줘",
                requested_by="marketing-user",
            )
            self.assertTrue(duplicate_refresh["task"]["reused"])
            self.assertEqual(
                duplicate_refresh["task"]["task_id"],
                outcome_item["improvement_task"]["task_id"],
            )
            repeated = service.record_outcome(
                task["task_id"], status="completed", summary="duplicate"
            )
            self.assertTrue(repeated["idempotent"])
            self.assertEqual(repeated["evidence_id"], outcome_item["evidence_id"])
            outcome_manifest_path = next(
                path for path in (knowledge_root / "evidence" / "hermes").rglob("*.md")
            )
            capture_context = parse_markdown(outcome_manifest_path).frontmatter["extensions"]["capture_context"]
            self.assertIn("poster-production", capture_context["intended_use"])
            outcome_manifest = parse_markdown(outcome_manifest_path)
            outcome_payload = json.loads(evidence_original_bytes(outcome_manifest).decode("utf-8"))
            self.assertEqual(outcome_payload["decisions"][0]["decided_by"], "marketing-owner")
            self.assertEqual(outcome_payload["action_items"][0]["owner"], "marketing-owner")
            effectiveness = service.measure_runbook_effectiveness("poster-production")
            self.assertEqual(effectiveness["revisions"][0]["completed"], 1)
            self.assertFalse(effectiveness["comparable"])

    def test_expired_runbook_prepares_refresh_task_instead_of_work_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._create_repository(directory)
            bundle_path = next((knowledge_root / "bundles" / "marketing" / "runbooks").glob("*.md"))
            document = parse_markdown(bundle_path)
            data = dict(document.frontmatter)
            extensions = dict(data["extensions"])
            governance = dict(extensions["governance"])
            governance["review_due_at"] = "2000-01-01T00:00:00+00:00"
            extensions["governance"] = governance
            data["extensions"] = extensions
            bundle_path.write_text(render_markdown(data, document.body), encoding="utf-8")
            service = KnowledgeService(knowledge_root)

            matches = service.find_workflow("포스터 이미지를 만들고 싶어")

            self.assertTrue(matches[0]["stale"])
            prepared = service.prepare_task(
                "poster-production",
                "포스터를 만들어줘",
                {"audience": "가족 캠퍼"},
            )

            self.assertEqual(prepared["mode"], "refresh_required")
            self.assertEqual(prepared["task"]["task_type"], "runbook_refresh")
            self.assertEqual(prepared["task"]["inputs"]["refresh_reason"], "expired")
            self.assertEqual(prepared["task"]["target_workflow_id"], "poster-production")
            self.assertEqual(
                prepared["task"]["deferred_work"]["inputs"],
                {"audience": "가족 캠퍼"},
            )

    def test_user_can_request_immediate_refresh_for_valid_runbook(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._create_repository(directory)
            service = KnowledgeService(knowledge_root)

            prepared = service.prepare_runbook_refresh(
                "poster-production",
                "현재 정책 기준으로 최신화해줘",
                requested_by="marketing-user",
            )

            self.assertEqual(prepared["mode"], "runbook_refresh")
            self.assertEqual(prepared["task"]["inputs"]["refresh_reason"], "user_requested")
            self.assertEqual(prepared["task"]["approval_gates"], ["owner-approval"])
            self.assertEqual(
                [step["id"] for step in prepared["task"]["steps"]],
                [
                    "collect-current-evidence",
                    "validate-current-evidence",
                    "compare-runbook",
                    "prepare-refresh-proposal",
                    "independent-agent-review",
                    "validate-proposal",
                    "owner-approval",
                    "publish-revision",
                ],
            )
            task_id = prepared["task"]["task_id"]
            for step in prepared["task"]["steps"][:3]:
                service.record_task_step(
                    task_id,
                    step["id"],
                    status="completed",
                    result="최신 Evidence를 기준으로 검토했다.",
                    actor="hermes-curator",
                )
            evidence_id = parse_markdown(
                next((knowledge_root / "bundles" / "marketing" / "runbooks").glob("*.md"))
            ).frontmatter["evidence"][0]
            decision_task = service.record_refresh_decision(
                task_id,
                decision="no_change",
                rationale="최신 원본과 비교했으나 절차 변경이 없다.",
                evidence_ids=[evidence_id],
                actor="hermes-curator",
            )
            self.assertEqual(decision_task["refresh_decision"]["decision"], "no_change")
            with self.assertRaisesRegex(ValueError, "must differ"):
                service.record_task_step(
                    task_id,
                    "independent-agent-review",
                    status="completed",
                    result="독립 검증 완료",
                    actor="hermes-curator",
                )
            for step in prepared["task"]["steps"][4:7]:
                is_approval = step["kind"] == "approval"
                service.record_task_step(
                    task_id,
                    step["id"],
                    status="approved" if is_approval else "completed",
                    result="최신 Evidence를 기준으로 검토했다.",
                    actor="marketing-owner" if is_approval else "verification-agent",
                )
            with self.assertRaisesRegex(ValueError, "confirm the updated Runbook revision"):
                service.record_task_step(
                    task_id, "publish-revision", status="completed",
                    result="revision 발행", actor="repository-agent",
                )
            bundle_path = next((knowledge_root / "bundles" / "marketing" / "runbooks").glob("*.md"))
            bundle_document = parse_markdown(bundle_path)
            bundle_data = dict(bundle_document.frontmatter)
            bundle_extensions = dict(bundle_data["extensions"])
            bundle_governance = dict(bundle_extensions["governance"])
            now = datetime.now(timezone.utc)
            bundle_governance["reviewed_at"] = now.isoformat(timespec="seconds")
            bundle_governance["review_due_at"] = (now + timedelta(days=30)).isoformat(timespec="seconds")
            bundle_extensions["governance"] = bundle_governance
            bundle_extensions["knowledge_revision"] = 2
            bundle_data["extensions"] = bundle_extensions
            bundle_path.write_text(render_markdown(bundle_data, bundle_document.body), encoding="utf-8")
            confirmed = service.confirm_runbook_revision(task_id, revision_ref="revision:test-2")
            self.assertEqual(confirmed["published_revision"]["knowledge_revision"], 2)
            service.record_task_step(
                task_id, "publish-revision", status="completed",
                result="revision 발행", actor="repository-agent",
            )
            outcome = service.record_outcome(
                task_id,
                status="completed",
                summary="변경 사항을 검토하고 Runbook revision을 발행했다.",
            )
            service.review_inbox_sensitivity(
                outcome["intake_id"], "simulated-human-reviewer", "completed"
            )
            service.accept_inbox(outcome["intake_id"], "simulated-human-approver")
            service.ingest_accepted()
            outcome_manifest = parse_markdown(
                next((knowledge_root / "evidence" / "hermes").rglob("*.md"))
            )

            self.assertFalse(outcome["idempotent"])
            self.assertEqual(
                outcome_manifest.frontmatter["extensions"]["capture_context"]["intended_use"],
                ["poster-production", "runbook-refresh"],
            )

    def test_user_reference_is_merged_into_open_refresh_as_evidence_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._create_repository(directory)
            service = KnowledgeService(knowledge_root)
            first = service.prepare_runbook_refresh(
                "poster-production",
                "현재 자료를 기준으로 검토해줘",
                requested_by="marketing-user",
            )
            source_path = next((knowledge_root / "evidence" / "manual").rglob("*.md"))
            source = parse_markdown(source_path)
            evidence_uuid = str(uuid4())
            evidence_id = f"evidence://example-org/user/2026/07/14/{evidence_uuid}"
            evidence_data = dict(source.frontmatter)
            evidence_data.update({
                "id": evidence_id,
                "source_uuid": evidence_uuid,
                "title": "사용자가 제공한 최신 디자인 가이드",
                "provider": "user",
                "source_ref": {"provider": "user", "captured_from": "user-upload"},
                "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "original_file": f"better-reference_{evidence_uuid}.txt",
                "curated_into": [],
                "checksum": "sha256:" + hashlib.sha256(b"new source").hexdigest(),
            })
            evidence_path = (
                knowledge_root / "evidence" / "user" / "2026" / "07" / "14"
                / f"better-reference_{evidence_uuid}.md"
            )
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text(render_markdown(evidence_data), encoding="utf-8")
            (evidence_path.parent / evidence_data["original_file"]).write_text(
                "new source", encoding="utf-8"
            )

            submitted = service.submit_runbook_reference(
                "poster-production",
                evidence_id,
                submitted_by="marketing-user",
                note="기존 자료보다 최근에 승인된 디자인 가이드입니다.",
            )
            repeated = service.submit_runbook_reference(
                "poster-production",
                evidence_id,
                submitted_by="marketing-user",
                note="동일 자료 재제출",
            )

            self.assertEqual(submitted["mode"], "runbook_reference_review")
            self.assertTrue(submitted["task"]["reused"])
            self.assertEqual(submitted["task"]["task_id"], first["task"]["task_id"])
            self.assertEqual(submitted["task"]["candidate_evidence_ids"], [evidence_id])
            self.assertEqual(len(repeated["task"]["reference_submissions"]), 1)
            self.assertIn("user_reference", repeated["task"]["inputs"]["refresh_reasons"])
            self.assertEqual(submitted["reference"]["context_alignment"], "aligned")

            with self.assertRaisesRegex(ValueError, "must differ"):
                service.record_reference_assessment(
                    submitted["task"]["task_id"], evidence_id=evidence_id,
                    authority="primary", recency="newer", applicability="full",
                    corroboration="corroborated", disposition="accept",
                    rationale="최신 공식 가이드다.", assessed_by="hermes-curator",
                    verified_by="hermes-curator",
                )
            assessed = service.record_reference_assessment(
                submitted["task"]["task_id"], evidence_id=evidence_id,
                authority="primary", recency="newer", applicability="partial",
                corroboration="corroborated", disposition="partial_accept",
                rationale="모바일 규격만 현재 Workflow에 적용된다.",
                assessed_by="hermes-curator", verified_by="verification-agent",
                conflicts=["기존 모바일 규격과 상충"],
            )
            self.assertEqual(
                assessed["reference_assessments"][0]["disposition"], "partial_accept"
            )
            for step in submitted["task"]["steps"][:3]:
                service.record_task_step(
                    submitted["task"]["task_id"], step["id"], status="completed",
                    result="후보 Evidence를 비교했다.", actor="hermes-curator",
                )
            decision = service.record_refresh_decision(
                submitted["task"]["task_id"], decision="update_required",
                rationale="최신 모바일 규격의 부분 반영이 필요하다.",
                evidence_ids=[evidence_id], actor="hermes-curator",
            )
            self.assertEqual(
                decision["refresh_decision"]["assessment_evidence_ids"], [evidence_id]
            )

    def test_refresh_stops_when_current_evidence_is_insufficient(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root, _ = self._create_repository(directory)
            service = KnowledgeService(knowledge_root)
            prepared = service.prepare_runbook_refresh(
                "poster-production",
                "최신 자료로 검토해줘",
                requested_by="marketing-user",
            )
            task_id = prepared["task"]["task_id"]
            for step in prepared["task"]["steps"][:3]:
                service.record_task_step(
                    task_id,
                    step["id"],
                    status="completed",
                    result="접근 가능한 최신 자료의 범위를 확인했다.",
                    actor="hermes-curator",
                )
            evidence_id = parse_markdown(
                next((knowledge_root / "bundles" / "marketing" / "runbooks").glob("*.md"))
            ).frontmatter["evidence"][0]
            evidence_path = next((knowledge_root / "evidence" / "manual").rglob("*.md"))
            evidence_document = parse_markdown(evidence_path)
            evidence_data = dict(evidence_document.frontmatter)
            evidence_extensions = dict(evidence_data["extensions"])
            evidence_extensions["availability"] = "metadata_only"
            evidence_data["extensions"] = evidence_extensions
            evidence_path.write_text(
                render_markdown(evidence_data, evidence_document.body), encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "available Evidence"):
                service.record_refresh_decision(
                    task_id,
                    decision="no_change",
                    rationale="확인 가능한 변화가 없다.",
                    evidence_ids=[evidence_id],
                    actor="hermes-curator",
                )

            task = service.record_refresh_decision(
                task_id,
                decision="insufficient_evidence",
                rationale="외부 정책의 최신 원본에 접근할 수 없다.",
                evidence_ids=[evidence_id],
                actor="hermes-curator",
            )

            self.assertEqual(task["status"], "needs_review")
            with self.assertRaisesRegex(ValueError, "steps must be recorded in order"):
                service.record_task_step(
                    task_id,
                    "independent-agent-review",
                    status="completed",
                    result="검증 시도",
                    actor="verification-agent",
                )


if __name__ == "__main__":
    unittest.main()
