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
