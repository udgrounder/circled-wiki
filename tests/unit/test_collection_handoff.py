import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from circled_wiki.config.collection_handoff import load_collection_handoff
from circled_wiki.core.service import collection_handoff_contract


class CollectionHandoffTests(unittest.TestCase):
    def test_allowlist_controls_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / ".circled-wiki" / "collection-handoff.yaml"
            path.parent.mkdir()
            path.write_text("schema_version: 1\ncollectors:\n  - collector_id: source\n    providers: [chat]\n    inbox_write: true\n    guidance: [include source context]\n", encoding="utf-8")
            self.assertEqual(load_collection_handoff(project).allows("source"), ("chat",))
            contract = collection_handoff_contract(project, "source")
            self.assertTrue(contract["authorization"]["inbox_write"])
            self.assertEqual(contract["authorization"]["allowed_providers"], ["chat"])
            self.assertEqual(contract["collection_guidance"], ["include source context"])
            self.assertEqual(contract["missing_information_policy"], "preserve_raw_as_pending_normalization")
            self.assertEqual(contract["write_policy"], "new_files_only")
            self.assertEqual(contract["next_action"], "create_new_inbox_file")
            self.assertEqual(contract["fallback"]["next_action"], "wiki_agent_capture_file_then_inspect")

    def test_unlisted_collector_cannot_receive_write_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = collection_handoff_contract(Path(directory), "unknown")
            self.assertFalse(contract["authorization"]["inbox_write"])
            self.assertEqual(contract["next_action"], "external_inbox_handoff_not_enabled")

    def test_schema_failure_returns_raw_preservation_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("circled_wiki.core.service.load_collection_handoff", side_effect=ValueError("schema unavailable")):
                contract = collection_handoff_contract(Path(directory), "source")
            self.assertEqual(contract["guidance_status"], "unavailable")
            self.assertEqual(contract["next_action"], "preserve_raw_in_preconfigured_inbox")
