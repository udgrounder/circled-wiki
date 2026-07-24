import tempfile
import unittest
import uuid
from pathlib import Path

from circled_wiki.core.frontmatter import render_markdown
from circled_wiki.core.validator import validate_repository


class ReferenceIntegrityTests(unittest.TestCase):
    def test_accepts_bundle_evidence_reference_without_backlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            bundle_uuid, evidence_uuid = str(uuid.uuid4()), str(uuid.uuid4())
            evidence_id = f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"
            bundle_id = f"knowledge://example-org/cs/refund_{bundle_uuid}"
            evidence_path = root / "evidence" / "manual" / "2026" / "07" / "10" / f"refund_{evidence_uuid}.md"
            bundle_path = root / "bundles" / "cs" / f"refund_{bundle_uuid}.md"
            evidence_path.parent.mkdir(parents=True); bundle_path.parent.mkdir(parents=True)
            evidence_path.write_text(render_markdown({"type": "evidence", "id": evidence_id, "title": "Refund", "source_uuid": evidence_uuid, "provider": "manual", "source_ref": {"provider": "manual", "captured_from": "manual"}, "captured_at": "2026-07-10T00:00:00+00:00", "status": "new", "checksum": "sha256:" + "0" * 64, "original_file": "refund.txt", "original_file_git_tracked": True, "extensions": {"availability": "available", "capture_context": {"why_collected": "참조 무결성 검증", "intended_use": ["refund-policy"]}, "storage": {"class": "git"}}}), encoding="utf-8")
            bundle_path.write_text(render_markdown({"type": "policy", "id": bundle_id, "bundle_uuid": bundle_uuid, "title": "Refund", "status": "draft", "summary": "Refund", "updated_at": "2026-07-10T00:00:00+00:00", "evidence": [evidence_id]}), encoding="utf-8")

            results = validate_repository(root)

            self.assertFalse(any(
                "Evidence Record does not reference this Bundle" in warning
                for result in results for warning in result.warnings
            ))
