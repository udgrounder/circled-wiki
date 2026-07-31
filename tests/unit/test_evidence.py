import hashlib
import tempfile
import unittest
from pathlib import Path

from circled_wiki.core.evidence import evidence_original_bytes
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.validator import validate_document


class EmbeddedEvidenceCompatibilityTests(unittest.TestCase):
    def test_marker_wrapped_embedded_evidence_remains_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            source_uuid = "550e8400-e29b-41d4-a716-446655440000"
            evidence_path = knowledge_root / "evidence" / "manual" / f"legacy_{source_uuid}.md"
            evidence_path.parent.mkdir(parents=True)
            original = "legacy original\n"
            frontmatter = {
                "type": "evidence",
                "id": f"evidence/example-org/legacy_{source_uuid}.md",
                "title": "Legacy embedded Evidence",
                "source_uuid": source_uuid,
                "provider": "manual",
                "source_ref": {"provider": "manual", "captured_from": "manual", "snapshot_at": "2026-07-31T00:00:00+00:00"},
                "captured_at": "2026-07-31T00:00:00+00:00",
                "checksum": "sha256:" + hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "language": "ko",
                "original_file_git_tracked": True,
                "derived_files": [],
                "extensions": {
                    "availability": "available",
                    "content_mode": "embedded",
                    "checksum_scope": "original_content",
                    "capture_context": {"why_collected": "compatibility", "intended_use": ["test"], "reuse_value": "medium", "retention_class": "general_reference", "sensitivity_review": "not_applicable"},
                    "visibility": "internal",
                    "pii_scanned": False,
                    "pii_masked": False,
                    "storage": {"class": "git"},
                    "ingest": {},
                },
            }
            body = (
                "# Conversation Evidence\n\n"
                "<!-- ORIGINAL_CONTENT_START -->" + original + "<!-- ORIGINAL_CONTENT_END -->\n"
            )
            evidence_path.write_text(render_markdown(frontmatter, body), encoding="utf-8")

            document = parse_markdown(evidence_path)
            self.assertEqual(evidence_original_bytes(document), original.encode("utf-8"))
            validation = validate_document(evidence_path, knowledge_root)
            self.assertTrue(validation.is_valid, validation.okf_errors + validation.profile_errors)
