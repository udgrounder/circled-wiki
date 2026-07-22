import tempfile
import unittest
from pathlib import Path

from knowledge_os.config.settings import load_settings, render_settings
from knowledge_os.core.ingest import capture_document, capture_file, ingest_evidence
from knowledge_os.core.namespace import inspect_organization_namespace
from knowledge_os.core.repository import create_bundle
from knowledge_os.core.validator import validate_document


class SettingsTests(unittest.TestCase):
    def test_absent_configuration_uses_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(Path(directory))
        self.assertEqual(settings.organization_id, "example-org")
        self.assertEqual(settings.workflow.default_owners, ())
        self.assertEqual(settings.publication.allowed_paths, ("knowledge",))

    def test_partial_legacy_configuration_uses_defaults_for_new_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text("schema_version: 1\n", encoding="utf-8")

            settings = load_settings(project)

        self.assertEqual(settings.workflow.default_owners, ())
        self.assertEqual(settings.publication.allowed_paths, ("knowledge",))

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
                render_settings(
                    organization_id="acme",
                    organization_name="Acme",
                    workflow_default_owners=("knowledge-owner",),
                ),
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
        self.assertEqual(bundle.frontmatter["owners"], ["knowledge-owner"])
        self.assertTrue(validation.is_valid, validation.profile_errors)

    def test_rendered_configuration_contains_explicit_safe_defaults(self):
        rendered = render_settings()

        self.assertIn("default_owners: []", rendered)
        self.assertIn("allowed_paths:\n  - knowledge", rendered)

    def test_invalid_default_owner_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "workflow.default_owners"):
            render_settings(workflow_default_owners=("Project Owner",))

    def test_publication_boundary_cannot_be_broadened_by_configuration(self):
        with self.assertRaisesRegex(ValueError, "publication.allowed_paths"):
            render_settings(publication_allowed_paths=("knowledge", "docs"))

    def test_existing_knowledge_namespace_blocks_config_identity_change(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text(
                render_settings(organization_id="acme", organization_name="Acme"),
                encoding="utf-8",
            )
            capture_document(
                project / "knowledge",
                "first source",
                "manual",
                title="First source",
                why_collected="Namespace test",
                intended_use=["test"],
                idempotency_key="namespace-acme",
            )
            config.write_text(
                render_settings(organization_id="beta", organization_name="Beta"),
                encoding="utf-8",
            )

            report = inspect_organization_namespace(project / "knowledge")
            with self.assertRaisesRegex(ValueError, "organization.id cannot change"):
                capture_document(
                    project / "knowledge",
                    "second source",
                    "manual",
                    title="Second source",
                    why_collected="Namespace test",
                    intended_use=["test"],
                    idempotency_key="namespace-beta",
                )
            with self.assertRaisesRegex(ValueError, "organization.id cannot change"):
                capture_file(
                    project / "knowledge",
                    b"blocked payload",
                    "blocked.txt",
                    "manual",
                    title="Blocked file",
                    why_collected="Namespace test",
                    intended_use=["test"],
                    idempotency_key="namespace-beta-file",
                )
            source = project / "knowledge" / "inbox" / "manual" / "blocked-source.txt"
            source.write_text("blocked source", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "organization.id cannot change"):
                ingest_evidence(
                    project / "knowledge",
                    source,
                    "manual",
                    why_collected="Namespace test",
                    intended_use=["test"],
                )
            inbox_markdown_count = len(
                list((project / "knowledge" / "inbox").rglob("*.md"))
            )
            blocked_payload_exists = any(
                path.name.startswith("blocked-")
                for path in (project / "knowledge" / "inbox").rglob("*")
                if path.is_file() and path != source
            )
            source_preserved = source.is_file()
            raw_exists = (project / "knowledge" / ".raw").exists()

        self.assertFalse(report["compatible"])
        self.assertEqual(report["configured_id"], "beta")
        self.assertEqual(report["observed_ids"], ("acme",))
        self.assertEqual(inbox_markdown_count, 1)
        self.assertFalse(blocked_payload_exists)
        self.assertTrue(source_preserved)
        self.assertFalse(raw_exists)


if __name__ == "__main__":
    unittest.main()
