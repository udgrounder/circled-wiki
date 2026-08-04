import re
import unittest
from pathlib import Path

from circled_wiki.runtime.core.bootstrap import RUNTIME_PROFILE_ALLOWLIST


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PROFILE_SECTIONS = {
    "Trigger",
    "Input",
    "Allowed Actions",
    "Checks",
    "Gates",
    "Output",
    "Failure State",
    "Prohibited",
}


class AgentRuleProfileTests(unittest.TestCase):
    def _routed_profiles(self, router: Path, prefix: str):
        content = router.read_text(encoding="utf-8")
        return {
            reference
            for reference in re.findall(rf"`({re.escape(prefix)}/[^`]+\.md)`", content)
            if "*" not in reference and not reference.endswith("/README.md")
        }

    def test_product_router_references_existing_profiles(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        references = self._routed_profiles(ROOT / "AGENTS.md", "product-agent-rules")

        self.assertIn("PRODUCT_ENGINEERING_RULES.md", agents)
        self.assertGreaterEqual(len(references), 5)
        for reference in references:
            self.assertTrue((ROOT / reference).is_file(), reference)

    def test_runtime_router_references_every_runtime_profile(self):
        router = ROOT / ".circled-wiki" / "AGENT_ROUTER.md"
        references = self._routed_profiles(router, "agent-rules")
        runtime_profiles = {
            f"agent-rules/{path.name}"
            for path in (ROOT / "agent-rules").glob("*.md")
            if path.name != "README.md"
        }

        self.assertEqual(references, runtime_profiles)
        self.assertIn("agent-rules/system-observation.md", references)

    def test_runtime_router_profiles_are_packaged_in_the_runtime_allowlist(self):
        references = self._routed_profiles(
            ROOT / ".circled-wiki" / "AGENT_ROUTER.md", "agent-rules"
        )
        packaged = {f"agent-rules/{path}" for path in RUNTIME_PROFILE_ALLOWLIST}

        self.assertTrue(references <= packaged, references - packaged)
        self.assertIn("agent-rules/inbox-sensitivity-review.md", packaged)

    def test_each_routed_profile_has_the_contract_sections(self):
        references = (
            self._routed_profiles(ROOT / "AGENTS.md", "product-agent-rules")
            | self._routed_profiles(
                ROOT / ".circled-wiki" / "AGENT_ROUTER.md", "agent-rules"
            )
        )
        for reference in references:
            text = (ROOT / reference).read_text(encoding="utf-8")
            sections = set(re.findall(r"^## (.+)$", text, flags=re.MULTILINE))
            self.assertEqual(REQUIRED_PROFILE_SECTIONS - sections, set(), reference)

    def test_product_entrypoints_use_the_product_router(self):
        for filename in ("CLAUDE.md", "HERMES.md"):
            text = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("`AGENTS.md` Routing Table", text, filename)
            self.assertIn("`PRODUCT_ENGINEERING_RULES.md`", text, filename)

    def test_product_router_does_not_route_runtime_content_operations(self):
        references = self._routed_profiles(ROOT / "AGENTS.md", "agent-rules")
        self.assertEqual(references, set())

    def test_runtime_profiles_exclude_product_engineering_authority(self):
        runtime_profiles = {
            path.name
            for path in (ROOT / "agent-rules").glob("*.md")
        }
        self.assertNotIn("repository-engineering.md", runtime_profiles)
        self.assertNotIn("bootstrap-circled-wiki.md", runtime_profiles)

    def test_runtime_guidance_does_not_require_removed_operational_preflight(self):
        runtime_guides = (
            ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md",
            ROOT / ".circled-wiki" / "AUTONOMOUS_AGENT_STARTUP.md",
            ROOT / "OPERATING_RULES.md",
            ROOT / "agent-rules" / "contracts" / "README.md",
        )
        for guide in runtime_guides:
            self.assertNotIn(
                "circled-wiki.py operational-preflight",
                guide.read_text(encoding="utf-8"),
                guide,
            )

        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        self.assertIn("config·namespace 검증", operating)

    def test_pipeline_delegation_is_preferred_without_transferring_gates(self):
        profiles = (ROOT / "agent-rules" / "README.md").read_text(encoding="utf-8")
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("위임을 권장", profiles)
        self.assertIn("위임 여부만으로 작업을 차단하지 않는다", profiles)
        self.assertIn("Gate·승인·최종 책임을 이전하지 않으며", profiles)
        self.assertIn("위임을 권장", bootstrap)
        self.assertIn("위임 여부만으로 작업을 차단하지 않는다", bootstrap)
        self.assertIn("Gate·승인·최종 책임을 유지", bootstrap)

    def test_legacy_issue_is_runtime_read_only_but_product_intake_can_move_it(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        intake = (
            ROOT / "product-agent-rules" / "operational-issue-intake.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Runtime Agent는 운영 중 legacy", operating)
        self.assertIn("Product Agent는 사용자가 특정 Issue", operating)
        self.assertIn("명시적 수집 요청에서만 이동", intake)

    def test_inbox_profiles_require_two_pass_masking_without_false_scan_attestation(self):
        capture = (ROOT / "agent-rules" / "inbox-capture.md").read_text(encoding="utf-8")
        inspection = (ROOT / "agent-rules" / "inbox-inspection.md").read_text(
            encoding="utf-8"
        )
        policy = (
            ROOT / ".circled-wiki" / "policies" / "sensitive-data-masking.md"
        ).read_text(encoding="utf-8")

        self.assertIn("1차 마스킹", capture)
        self.assertIn("2차 확인", inspection)
        self.assertIn("불변 파일 원본", capture)
        self.assertIn("pii_scanned: true", inspection)
        self.assertIn("PII Scan Receipt를 대신하지 않는다", policy)

    def test_pii_receipt_contract_is_canonical_and_ingest_references_it(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        ingest = (ROOT / "agent-rules" / "evidence-ingest.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("후보 checksum", operating)
        self.assertIn("Evidence 최초 생성 입력", operating)
        self.assertIn("needs_review", operating)
        self.assertIn("RB-EVD-020·RB-SEC-005", ingest)
        self.assertNotIn("scanner·version·시각·결과·검토자", ingest)

    def test_content_processing_profiles_keep_pii_handling_explicit(self):
        profiles = {
            name: (ROOT / "agent-rules" / name).read_text(encoding="utf-8")
            for name in (
                "inbox-inspection.md",
                "evidence-ingest.md",
                "knowledge-curation.md",
                "knowledge-query.md",
            )
        }

        self.assertIn("2차 마스킹 확인", profiles["inbox-inspection.md"])
        self.assertIn("Receipt의 후보 checksum", profiles["evidence-ingest.md"])
        self.assertIn("다시 확인", profiles["knowledge-curation.md"])
        self.assertIn("응답 전 최종 마스킹 확인", profiles["knowledge-query.md"])
        for name, content in profiles.items():
            self.assertIn("PII", content, name)

    def test_curation_references_canonical_pii_and_publication_gates(self):
        curation = (ROOT / "agent-rules" / "knowledge-curation.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("RB-SEC-001·005", curation)
        self.assertIn("RB-PUB-002", curation)
        self.assertIn("Draft와 active 전환의 차이는 RB-CUR-006", curation)

    def test_evidence_contract_is_owned_by_operating_rules(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        profiles = {
            name: (ROOT / "agent-rules" / name).read_text(encoding="utf-8")
            for name in ("README.md", "evidence-ingest.md", "knowledge-curation.md")
        }
        policies = {
            name: (ROOT / ".circled-wiki" / "policies" / name).read_text(
                encoding="utf-8"
            )
            for name in ("agent-security.md", "sensitive-data-masking.md")
        }

        evidence_section = operating.index("## 4. Evidence Invariants")
        workflow_section = operating.index("## 5. Workflow State Machine")
        queue_contract = operating.index("**RB-EVD-023**")
        self.assertLess(evidence_section, queue_contract)
        self.assertLess(queue_contract, workflow_section)
        self.assertIn("다시 서술하지 않고", profiles["README.md"])
        for name in ("evidence-ingest.md", "knowledge-curation.md"):
            self.assertIn("## Applicable Global Rules", profiles[name])
            self.assertIn("RB-EVD-023", profiles[name])
            self.assertNotIn("workspace/task/curation-queue", profiles[name])
        for content in policies.values():
            self.assertIn("OPERATING_RULES.md", content)
            self.assertNotIn("04-evidence-model.md", content)

    def test_embedded_evidence_format_versions_are_defined_in_runtime_rules(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")

        self.assertIn("extensions.embedded_format_version", operating)
        self.assertIn("버전이 없는 기존 문서는 v1", operating)
        self.assertIn("embedded_format_version: 2", operating)
        self.assertIn("checksum_scope: document_body", operating)
        self.assertIn("미지원 버전", operating)
        self.assertIn("Ingest는 Inbox 원문을 최신 지원 포맷", operating)
        self.assertIn("자동 보정하지 않고 Validator 오류", operating)

    def test_contract_reconciliation_preserves_inbox_stage_gates(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        router = (ROOT / ".circled-wiki" / "AGENT_ROUTER.md").read_text(
            encoding="utf-8"
        )
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )
        rules = (ROOT / "agent-rules" / "README.md").read_text(encoding="utf-8")
        contract = (ROOT / "agent-rules" / "contracts" / "inbox.yaml").read_text(
            encoding="utf-8"
        )

        self.assertIn("세부 전이·차단 사유·재처리는 등록된 Inbox 계약", operating)
        self.assertIn("`awaiting_user`", operating)
        self.assertIn("`review_handoff`", operating)
        self.assertIn("Evidence 직전 PII Scan·Receipt 확정", operating)
        self.assertIn("`needs_review` 뒤 안전 처리", operating)
        self.assertIn("on_blocked:", contract)
        self.assertIn("Block reasons are", contract)
        self.assertIn("reasons:", contract)
        self.assertIn("sensitivity_review_required", contract)
        self.assertIn("pii_needs_review", contract)
        self.assertIn("Capture starts with sensitivity_review: required", contract)
        self.assertIn("Scan processes policy-target PII including mobile phone", contract)
        self.assertIn("`agent-rules/contracts/inbox.yaml`", router)
        self.assertIn("`agent-rules/contracts/curation.yaml`", router)
        self.assertIn("자동 PII Scan은 전화번호를 포함한 정책 대상 PII를 실제 후보에서 검사·마스킹해 `passed` 또는 `masked` Receipt", bootstrap)
        self.assertIn("`needs_review` 뒤 안전 처리", bootstrap)
        self.assertIn("전화번호를 포함한 정책 대상 PII", rules)
        self.assertIn("`needs_review`는 단계별 판정", rules)

    def test_curation_contract_preserves_review_and_revision_gates(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        contract = (ROOT / "agent-rules" / "contracts" / "curation.yaml").read_text(encoding="utf-8")

        self.assertIn("RB-ROUTE-016", operating)
        self.assertIn("`runbook`·`manual`을 제외한 기존 Bundle의 갱신", operating)
        self.assertIn("자동 갱신 Receipt", operating)
        self.assertIn("run_configured_curation_batch", contract)
        self.assertIn("api_version: circled-wiki.reconciliation-contract/v1", contract)
        self.assertIn("kind: reconciliation_contract", contract)
        self.assertIn("metadata:", contract)
        self.assertIn("spec:", contract)
        self.assertIn("no_bundle_recorded", contract)
        self.assertIn("review_handoff", contract)
        self.assertIn("retryable_block", contract)
        self.assertIn("reason_categories", contract)
        self.assertNotIn("apply_approved_curation_update", contract)

    def test_contract_readme_explains_schema_and_rule_boundaries(self):
        readme = (ROOT / "agent-rules" / "contracts" / "README.md").read_text(
            encoding="utf-8"
        )

        for field in (
            "`api_version`", "`kind`", "`metadata.name`", "`metadata.version`",
            "`metadata.description`", "`spec`", "`stages.<state>.next_stage`",
            "`outcomes.<name>.queue_disposition`", "`outcomes.<name>.terminal`",
            "`stages.<state>.on_blocked.reasons.<reason>`",
            "`RB-ROUTE-015~016`", "`RB-CUR-001~010`",
        ):
            self.assertIn(field, readme)
        self.assertIn("전체 업무가 끝났다는 뜻이 아니라", readme)
        self.assertIn("자동 실행 권한을 추가하지 않는다", readme)

    def test_runtime_repository_boundary_keeps_product_and_installation_mutations_separate(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")

        self.assertIn("제품 source repository", operating)
        self.assertIn("설치본의 `knowledge/`와 `workspace/` 변경", operating)
        self.assertIn("선택한 Runtime Profile과 해당 Gate", operating)

    def test_source_docs_cannot_be_mistaken_for_runtime_rules(self):
        docs_readme = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        evidence_model = (ROOT / "docs" / "04-evidence-model.md").read_text(
            encoding="utf-8"
        )
        agent_guide = (ROOT / "docs" / "18-agent-guide.md").read_text(
            encoding="utf-8"
        )
        reference_contract = (ROOT / "docs" / "26-reference-contract.md").read_text(
            encoding="utf-8"
        )
        historical_source = (
            ROOT / "docs" / "source" / "chatgpt-llm-wiki-conversation-2026-07-08.md"
        ).read_text(encoding="utf-8")

        self.assertIn("Runtime release에 포함되지 않으며", docs_readme)
        self.assertIn("Runtime 전역 규칙의 유일한 정본", docs_readme)
        self.assertIn("RB-EVD-002~023", docs_readme)
        self.assertIn("Runtime에 배포되지 않는다", evidence_model)
        self.assertIn("직접 로드하거나 권한 근거로 사용하지 않는다", agent_guide)
        self.assertIn("source-only design reference", reference_contract)
        self.assertIn("과거 문구는 폐기되었다", historical_source[:500])

    def test_runtime_discovery_uses_official_tools_before_raw_filesystem_search(self):
        query = (ROOT / "agent-rules" / "knowledge-query.md").read_text(encoding="utf-8")
        workflow = (ROOT / "agent-rules" / "workflow-execution.md").read_text(encoding="utf-8")
        startup = (ROOT / ".circled-wiki" / "AUTONOMOUS_AGENT_STARTUP.md").read_text(
            encoding="utf-8"
        )
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("작업을 계속하기\n  위한 최후 수단", query)
        self.assertIn("작업을 계속하기 위한 최후 수단", workflow)
        self.assertIn("`record-system-issue`", query)
        self.assertIn("`record-system-issue`", workflow)
        self.assertIn("직접 `find`, `grep`, `rg` 탐색은", startup)
        self.assertIn("`record-system-issue`", startup)
        self.assertIn("직접 `find`,\n   `grep`, `rg` 탐색은", bootstrap)
        self.assertIn("`record-system-issue`", bootstrap)

    def test_unhandled_procedure_ambiguity_that_requires_user_judgment_is_recorded(self):
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        observation = (ROOT / "agent-rules" / "system-observation.md").read_text(
            encoding="utf-8"
        )
        workflow = (ROOT / "agent-rules" / "workflow-execution.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("기존 공식 절차로 처리할 수 없는", operating)
        self.assertIn("사용자 의사 판단", operating)
        self.assertIn("향후 그런 실시간 판단을 줄이기", observation)
        self.assertIn("기존 절차를 변경·차단하거나", observation)
        self.assertIn("기존 공식 절차로 처리할 수 없는", workflow)

    def test_bundle_identity_contract_is_directly_discoverable_to_runtime_agents(self):
        router = (ROOT / ".circled-wiki" / "AGENT_ROUTER.md").read_text(
            encoding="utf-8"
        )
        operating = (ROOT / "OPERATING_RULES.md").read_text(encoding="utf-8")
        curation = (ROOT / "agent-rules" / "knowledge-curation.md").read_text(
            encoding="utf-8"
        )
        publication = (ROOT / "agent-rules" / "publication.md").read_text(
            encoding="utf-8"
        )

        for content in (router, curation, publication):
            self.assertIn("RB-KNW-026", content)
        self.assertIn("파일명: {slug}.md", router)
        self.assertIn("bundle/{organization_id}/{slug}--{bundle_uuid}", router)
        self.assertIn("사용자와 소통하는 언어", router)
        self.assertIn("판단할 수 없으면 한국어", router)
        self.assertIn("**RB-KNW-026**", operating)
        self.assertIn("사용자와 소통하는 언어", operating)
        self.assertIn("판단할 수 없으면 한국어", operating)

    def test_bundle_identity_router_requires_rule_first_read_only_audit(self):
        router = (ROOT / ".circled-wiki" / "AGENT_ROUTER.md").read_text(
            encoding="utf-8"
        )
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Bundle Identity Routing", router)
        self.assertIn("Fallback 탐색", router)
        self.assertIn("제한된 `rg` 탐색을 허용", router)
        self.assertIn("저장소 전체 검색은 이 제한 탐색으로도 해결되지 않을 때만", router)
        self.assertIn("변경 전에는 `agent-rules/knowledge-curation.md`", router)
        self.assertIn("승인 전에는 rename·frontmatter 변경을 하지 않는다", router)
        self.assertIn("Bundle Identity Routing", bootstrap)
        self.assertIn("shell 검색하지 않는다", bootstrap)
        self.assertIn("제한 검색으로\n   fallback", bootstrap)

    def test_runtime_router_redirects_version_deployment_to_product_profiles(self):
        router = (ROOT / ".circled-wiki" / "AGENT_ROUTER.md").read_text(
            encoding="utf-8"
        )
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )
        product_router = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

        self.assertIn("Circled Wiki OS version 준비·배포·rollback", router)
        self.assertIn("Runtime mutation 금지", router)
        self.assertIn("release-preparation", router)
        self.assertIn("deployment-coordination", router)
        self.assertIn("Runtime Agent 권한이 아니다", bootstrap)
        self.assertIn("rollback", product_router)
