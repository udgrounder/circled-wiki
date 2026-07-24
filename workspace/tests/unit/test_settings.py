import tempfile
import unittest
from pathlib import Path

from circled_wiki.config.settings import load_settings, render_settings, settings_semantic_checksum
from circled_wiki.core.ingest import capture_document, capture_file, ingest_evidence
from circled_wiki.core.namespace import inspect_organization_namespace
from circled_wiki.core.repository import (
    backfill_evidence_links, create_bundle, find_document_by_id, migrate_document_ids,
)
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.validator import validate_document


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

    def test_unversioned_legacy_config_migrates_without_identity_change(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text("organization:\n  id: acme\n  name: Acme\n", encoding="utf-8")

            settings = load_settings(project)

            self.assertEqual(settings.organization_id, "acme")
            self.assertEqual(settings.organization_name, "Acme")
            self.assertNotIn("schema_version", config.read_text(encoding="utf-8"))

    def test_approval_owner_is_install_local_and_defaults_to_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text("schema_version: 1\napproval:\n  knowledge_owner: alice\n", encoding="utf-8")
            self.assertEqual(load_settings(project).approval.knowledge_owner, "alice")
            self.assertEqual(load_settings(Path(directory) / "other").approval.knowledge_owner, "")

    def test_enabled_push_requires_remote_and_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            config = project / ".circled-wiki" / "config.yaml"
            config.parent.mkdir()
            config.write_text("schema_version: 1\npublication:\n  push_enabled: true\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "push requires"):
                load_settings(project)

    def test_two_installations_keep_identity_and_inbox_uris_isolated(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            alpha = base / "alpha"; beta = base / "beta"
            for project, organization_id in ((alpha, "alpha"), (beta, "beta")):
                config = project / ".circled-wiki" / "config.yaml"
                config.parent.mkdir(parents=True)
                config.write_text(render_settings(organization_id=organization_id, organization_name=organization_id.title()), encoding="utf-8")
            alpha_item = capture_document(alpha / "knowledge", "alpha source", "manual", title="Alpha", why_collected="test", intended_use=["isolation"], idempotency_key="alpha-1")
            beta_item = capture_document(beta / "knowledge", "beta source", "manual", title="Beta", why_collected="test", intended_use=["isolation"], idempotency_key="beta-1")
            self.assertTrue(alpha_item.intake_id.startswith("inbox://alpha/"))
            self.assertTrue(beta_item.intake_id.startswith("inbox://beta/"))
            self.assertNotEqual(alpha_item.intake_id, beta_item.intake_id)

    def test_semantic_checksum_ignores_omitted_safe_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            explicit = base / "explicit"; legacy = base / "legacy"
            for project in (explicit, legacy):
                (project / ".circled-wiki").mkdir(parents=True)
            (explicit / ".circled-wiki" / "config.yaml").write_text(render_settings(), encoding="utf-8")
            (legacy / ".circled-wiki" / "config.yaml").write_text("schema_version: 1\n", encoding="utf-8")
            self.assertEqual(settings_semantic_checksum(explicit), settings_semantic_checksum(legacy))

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
        self.assertTrue(evidence.evidence_id.startswith("evidence/acme/"))
        self.assertTrue(bundle.frontmatter["id"].startswith("bundle/acme/"))
        self.assertEqual(len(bundle.frontmatter["evidence_links"]), 1)
        self.assertTrue(bundle.frontmatter["evidence_links"][0].startswith("["))
        self.assertIn("](evidence/manual/", bundle.frontmatter["evidence_links"][0])
        self.assertTrue(bundle.frontmatter["evidence_links"][0].endswith(".md)"))
        self.assertEqual(bundle.frontmatter["owners"], ["knowledge-owner"])
        self.assertTrue(validation.is_valid, validation.profile_errors)

    def test_rendered_configuration_contains_explicit_safe_defaults(self):
        rendered = render_settings()

        self.assertIn("default_owners: []", rendered)
        self.assertIn("curation:", rendered)
        self.assertIn("enabled: false", rendered)
        self.assertIn("allowed_paths:\n  - knowledge", rendered)

    def test_enabled_curation_requires_explicit_adapter_identity(self):
        with self.assertRaisesRegex(ValueError, "enabled curation requires"):
            render_settings(curation_enabled=True)

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

    def test_evidence_link_backfill_is_dry_run_then_repairs_existing_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            root = project / "knowledge"
            source = root / "inbox" / "manual" / "source.txt"
            source.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            evidence = ingest_evidence(
                root, source, "manual", why_collected="test", intended_use=["test"],
            )
            bundle = create_bundle(
                root, domain="test", slug="backfill", title="Backfill", bundle_type="guide",
                summary="Backfill test.", evidence_id=evidence.evidence_id,
            )
            data = dict(bundle.frontmatter)
            data.pop("evidence_links")
            bundle.path.write_text(render_markdown(data, bundle.body), encoding="utf-8")

            dry_run = backfill_evidence_links(root)
            self.assertEqual(dry_run["mode"], "dry_run")
            self.assertEqual(dry_run["change_count"], 1)
            self.assertNotIn("evidence_links", parse_markdown(bundle.path).frontmatter)

            applied = backfill_evidence_links(root, apply=True)
            repaired = parse_markdown(bundle.path)
            self.assertEqual(applied["applied_count"], 1)
            self.assertEqual(repaired.frontmatter["evidence"], [evidence.evidence_id])
            evidence_document = find_document_by_id(root, evidence.evidence_id)
            self.assertEqual(
                repaired.frontmatter["evidence_links"],
                [f"[{evidence_document.frontmatter['title']}]({evidence_document.path.relative_to(root).as_posix()})"],
            )

    def test_evidence_link_backfill_does_not_write_unresolved_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "knowledge"
            bundle_path = root / "bundles" / "test" / "broken_00000000-0000-4000-8000-000000000000.md"
            bundle_path.parent.mkdir(parents=True)
            bundle_path.write_text(
                "---\n"
                "type: guide\n"
                "id: knowledge://example-org/test/broken_00000000-0000-4000-8000-000000000000\n"
                "bundle_uuid: 00000000-0000-4000-8000-000000000000\n"
                "title: Broken\n"
                "status: draft\n"
                "summary: Broken reference.\n"
                "evidence:\n  - evidence://example-org/manual/2026/07/22/missing\n"
                "extensions:\n  knowledge_revision: 1\n"
                "---\n\n# Broken\n",
                encoding="utf-8",
            )
            original = bundle_path.read_text(encoding="utf-8")

            report = backfill_evidence_links(root, apply=True)

            self.assertEqual(report["blocked_count"], 1)
            self.assertEqual(report.get("applied_count", 0), 0)
            self.assertEqual(bundle_path.read_text(encoding="utf-8"), original)

    def test_id_migration_replaces_legacy_ids_and_all_bundle_references(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            root = project / "knowledge"
            source = root / "inbox" / "manual" / "source.txt"
            source.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            evidence = ingest_evidence(root, source, "manual", why_collected="test", intended_use=["test"])
            bundle = create_bundle(
                root, domain="test", slug="legacy", title="Legacy", bundle_type="guide",
                summary="Legacy migration.", evidence_id=evidence.evidence_id,
            )
            evidence_document = find_document_by_id(root, evidence.evidence_id)
            legacy_evidence_id = f"evidence://example-org/manual/2026/07/22/{evidence_document.frontmatter['source_uuid']}"
            legacy_bundle_id = f"knowledge://example-org/test/{bundle.path.stem}"
            evidence_data = dict(evidence_document.frontmatter)
            evidence_data["id"] = legacy_evidence_id
            evidence_data["curated_into"] = [legacy_bundle_id]
            evidence_document.path.write_text(render_markdown(evidence_data, evidence_document.body), encoding="utf-8")
            bundle_data = dict(bundle.frontmatter)
            bundle_data["id"] = legacy_bundle_id
            bundle_data["evidence"] = [legacy_evidence_id]
            bundle.path.write_text(render_markdown(bundle_data, bundle.body), encoding="utf-8")

            dry_run = migrate_document_ids(root)
            self.assertEqual(dry_run["change_count"], 2)
            self.assertEqual(bundle_data["id"], legacy_bundle_id)

            applied = migrate_document_ids(root, apply=True)
            migrated_bundle = parse_markdown(bundle.path)
            migrated_evidence = parse_markdown(evidence_document.path)
            self.assertEqual(applied["applied_count"], 2)
            self.assertEqual(migrated_bundle.frontmatter["id"], f"bundle/example-org/{bundle.path.name}")
            self.assertEqual(migrated_evidence.frontmatter["id"], f"evidence/example-org/{evidence_document.path.name}")
            self.assertEqual(migrated_bundle.frontmatter["evidence"], [migrated_evidence.frontmatter["id"]])
            self.assertEqual(migrated_evidence.frontmatter["curated_into"], [migrated_bundle.frontmatter["id"]])


if __name__ == "__main__":
    unittest.main()
