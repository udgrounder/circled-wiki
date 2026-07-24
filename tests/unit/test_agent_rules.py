import re
import unittest
from pathlib import Path


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

    def test_pipeline_delegation_is_preferred_without_transferring_gates(self):
        profiles = (ROOT / "agent-rules" / "README.md").read_text(encoding="utf-8")
        bootstrap = (ROOT / ".circled-wiki" / "AGENT_BOOTSTRAP.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("위임을 우선 검토", profiles)
        self.assertIn("Gate·승인·최종 책임을 이전하지 않으며", profiles)
        self.assertIn("위임을 우선\n   검토", bootstrap)
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
        self.assertIn("자동으로 만들지 않는다", policy)

    def test_content_processing_profiles_require_direct_masking_rechecks(self):
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
        self.assertIn("직접 다시 읽어", profiles["evidence-ingest.md"])
        self.assertIn("다시 확인", profiles["knowledge-curation.md"])
        self.assertIn("응답 전 최종 마스킹 확인", profiles["knowledge-query.md"])
        for name, content in profiles.items():
            self.assertIn("PII", content, name)

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
