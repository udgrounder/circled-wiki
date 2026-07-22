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
    def test_agents_routing_references_existing_profiles(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        references = {
            reference
            for reference in re.findall(r"`(agent-rules/[^`]+\.md)`", agents)
            if "*" not in reference and reference != "agent-rules/README.md"
        }

        self.assertGreaterEqual(len(references), 8)
        for reference in references:
            self.assertTrue((ROOT / reference).is_file(), reference)

    def test_each_routed_profile_has_the_contract_sections(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        references = {
            reference
            for reference in re.findall(r"`(agent-rules/[^`]+\.md)`", agents)
            if "*" not in reference and reference != "agent-rules/README.md"
        }
        for reference in references:
            text = (ROOT / reference).read_text(encoding="utf-8")
            sections = set(re.findall(r"^## (.+)$", text, flags=re.MULTILINE))
            self.assertEqual(REQUIRED_PROFILE_SECTIONS - sections, set(), reference)

    def test_agent_entrypoints_use_the_same_router(self):
        for filename in ("CLAUDE.md", "HERMES.md"):
            text = (ROOT / filename).read_text(encoding="utf-8")
            self.assertIn("`AGENTS.md` Routing Table", text, filename)

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
