import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.service import collection_handoff_contract


class CollectionGuidanceTests(unittest.TestCase):
    def test_guidance_exposes_existing_inbox_location_and_raw_fallback_without_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = collection_handoff_contract(Path(directory))
        self.assertEqual(contract["operation"], "collection_guidance")
        self.assertEqual(contract["guidance_version"], "v1")
        self.assertNotIn("release_id", contract)
        self.assertEqual(contract["guidance_document"], ".circled-wiki/contracts/COLLECTION_HANDOFF.md")
        self.assertIn("knowledge/inbox/<provider>/", contract["guidance_markdown"])
        self.assertIn("source_locator", contract["guidance_markdown"])
        self.assertEqual(contract["fallback"]["next_action"], "wiki_agent_capture_file_then_inspect")
        self.assertEqual(contract["next_action"], "collect_to_inbox")
