import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.service import collection_handoff_contract


class CollectionGuidanceTests(unittest.TestCase):
    def test_handoff_exposes_only_version_and_document_paths_without_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = collection_handoff_contract(Path(directory))
        self.assertEqual(contract["handoff_version"], "v1")
        self.assertNotIn("release_id", contract)
        self.assertEqual(set(contract), {
            "handoff_version", "method_spec_document", "collection_guide_document",
        })
        self.assertEqual(contract["method_spec_document"], ".circled-wiki/contracts/INBOX_INPUT_METHODS.md")
        self.assertEqual(contract["collection_guide_document"], ".circled-wiki/contracts/COLLECTION_HANDOFF.md")

    def test_handoff_guide_is_an_optional_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            contract = collection_handoff_contract(Path(directory))
        self.assertEqual(contract["collection_guide_document"], ".circled-wiki/contracts/COLLECTION_HANDOFF.md")
