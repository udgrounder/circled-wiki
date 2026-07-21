import tempfile
import unittest
from pathlib import Path

from knowledge_os.config.settings import load_settings, render_settings
from knowledge_os.core.ingest import capture_document, ingest_evidence
from knowledge_os.core.repository import create_bundle
from knowledge_os.core.validator import validate_document


class SettingsTests(unittest.TestCase):
    def test_absent_configuration_uses_legacy_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
        self.assertEqual(settings.organization_id, "example-org")

    def test_configured_namespace_is_used_for_new_intake_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".circled-wiki").mkdir()
            (project / ".circled-wiki" / "config.yaml").write_text(
                render_settings(organization_id="acme", organization_name="Acme"),
                encoding="utf-8",
            )
            result = capture_document(
                project / "knowledge",
                "source text",
                "manual",
                title="Source",
                why_collected="Pilot",
                intended_use=["test"],
                idempotency_key="settings-test-1",
            )
        self.assertTrue(result.intake_id.startswith("inbox://acme/manual/"))

    def test_invalid_namespace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "organization.id"):
            render_settings(organization_id="Acme Corp")

    def test_configured_namespace_is_used_for_evidence_bundle_and_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".circled-wiki").mkdir()
            (project / ".circled-wiki" / "config.yaml").write_text(
                render_settings(organization_id="acme", organization_name="Acme"),
                encoding="utf-8",
            )
            knowledge = project / "knowledge"
            source = knowledge / "inbox" / "manual" / "policy.txt"
            source.parent.mkdir(parents=True)
            source.write_text("policy source", encoding="utf-8")
            evidence = ingest_evidence(
                knowledge,
                source,
                "manual",
                why_collected="Pilot",
                intended_use=["policy"],
                sensitivity_review="not_applicable",
            )
            bundle = create_bundle(
                knowledge,
                domain="operations",
                slug="pilot-policy",
                title="Pilot Policy",
                bundle_type="policy",
                summary="Pilot summary",
                evidence_id=evidence.evidence_id,
            )
            validation = validate_document(bundle.path, knowledge)
        self.assertTrue(evidence.evidence_id.startswith("evidence://acme/manual/"))
        self.assertTrue(bundle.frontmatter["id"].startswith("knowledge://acme/operations/"))
        self.assertTrue(validation.is_valid, validation.profile_errors)


if __name__ == "__main__":
    unittest.main()
