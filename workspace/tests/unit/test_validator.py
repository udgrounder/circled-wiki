import tempfile
import unittest
import uuid
from pathlib import Path

from circled_wiki.core.frontmatter import render_markdown
from circled_wiki.core.validator import validate_document, validate_repository


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        (self.root / "bundles" / "cs").mkdir(parents=True)

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_okf_and_profile_errors_are_separate(self):
        path = self.root / "bundles" / "cs" / "broken.md"
        path.write_text(render_markdown({"title": "Broken"}), encoding="utf-8")

        result = validate_document(path, self.root)

        self.assertIn("type must be a non-empty string", result.okf_errors)
        self.assertIn("missing required Bundle field: id", result.profile_errors)

    def test_repository_validation_includes_control_plane_documents(self):
        project = self.root / "isolated-project"
        knowledge_root = project / "knowledge"
        path = project / ".circled-wiki" / "templates" / "broken.md"
        path.parent.mkdir(parents=True)
        path.write_text(render_markdown({"title": "Missing type"}), encoding="utf-8")

        results = validate_repository(knowledge_root)

        control_result = next(result for result in results if result.path == path)
        self.assertIn("type must be a non-empty string", control_result.okf_errors)

    def test_valid_bundle_passes_profile_validation(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"refund_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "policy",
                    "id": f"bundle/example-org/refund_{bundle_uuid}.md",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund",
                    "status": "draft",
                    "summary": "Refund policy",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "evidence": [f"evidence/example-org/refund-source_{evidence_uuid}.md"],
                    "extensions": {"knowledge_revision": 1},
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertTrue(result.is_valid, result.as_dict())

    def test_repository_validation_reports_malformed_bundle_evidence_without_crashing(self):
        bundle_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"broken-evidence_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "guide",
                    "id": f"knowledge://example-org/cs/broken-evidence_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Broken Evidence",
                    "status": "draft",
                    "summary": "Malformed reference test",
                    "updated_at": "2026-07-22T00:00:00+00:00",
                    "evidence": [{"unexpected": "object"}],
                }
            ),
            encoding="utf-8",
        )

        results = validate_repository(self.root)

        result = next(item for item in results if item.path == path)
        self.assertIn("every evidence item must use organization 'example-org'", result.profile_errors)

    def test_runbook_must_use_domain_runbooks_directory(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"refund_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "runbook",
                    "id": f"knowledge://example-org/cs/refund_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund Runbook",
                    "status": "draft",
                    "summary": "Refund procedure",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "evidence": [f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"],
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertIn(
            "Runbook must be stored in bundles/<domain>/runbooks/ or bundles/archive/<domain>/runbooks/",
            result.profile_errors,
        )

    def test_active_bundle_requires_owner_and_governance(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"refund_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "policy",
                    "id": f"knowledge://example-org/cs/refund_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund",
                    "status": "active",
                    "summary": "Refund policy",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "evidence": [f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"],
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertIn("active Bundle owners must be a non-empty string array", result.profile_errors)
        self.assertIn("active Bundle must define extensions.governance", result.profile_errors)

    def test_rulebook_extension_is_only_valid_for_guide(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"refund-rulebook_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "policy",
                    "id": f"knowledge://example-org/cs/refund-rulebook_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund Rulebook",
                    "status": "draft",
                    "summary": "Refund work entry point",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "evidence": [f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"],
                    "extensions": {
                        "rulebook": {
                            "rulebook_id": "refund-processing",
                            "policies": [],
                            "runbooks": [],
                            "guides": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertIn("extensions.rulebook is only allowed on type guide", result.profile_errors)

    def test_resolved_inquiry_requires_resolution(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"refund-question_{bundle_uuid}.md"
        path.write_text(
            render_markdown(
                {
                    "type": "reference",
                    "id": f"knowledge://example-org/cs/refund-question_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund Question",
                    "status": "draft",
                    "summary": "Unresolved refund question",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "evidence": [f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"],
                    "extensions": {
                        "inquiry": {
                            "question_id": "refund-window",
                            "status": "resolved",
                            "owner": "cs-owner",
                            "resolution": "",
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertIn("resolved inquiry must include a resolution", result.profile_errors)

    def test_runbook_validity_cannot_exceed_risk_tier_maximum(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / "runbooks" / f"refund_{bundle_uuid}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            render_markdown(
                {
                    "type": "runbook",
                    "id": f"knowledge://example-org/cs/refund_{bundle_uuid}",
                    "bundle_uuid": bundle_uuid,
                    "title": "Refund Runbook",
                    "status": "active",
                    "summary": "Refund workflow",
                    "updated_at": "2026-07-10T10:00:00+09:00",
                    "owners": ["cs-owner"],
                    "evidence": [f"evidence://example-org/manual/2026/07/10/{evidence_uuid}"],
                    "extensions": {
                        "governance": {
                            "reviewed_at": "2026-07-01T00:00:00+00:00",
                            "review_due_at": "2026-08-01T00:00:00+00:00",
                            "freshness_policy": "risk_based",
                            "risk_tier": "high",
                            "source_volatility": "periodic",
                            "validity_days": 31,
                            "change_triggers": ["user_requested"],
                        },
                        "workflow": {
                            "workflow_id": "refund-processing",
                            "version": 1,
                            "execution_mode": "guided",
                            "required_inputs": [],
                            "steps": [{"id": "review", "title": "Review", "kind": "validation"}],
                            "approval_gates": [],
                            "completion_criteria": ["Review completed"],
                        },
                    },
                }
            ),
            encoding="utf-8",
        )

        result = validate_document(path, self.root)

        self.assertIn(
            "extensions.governance.validity_days exceeds risk and volatility maximum",
            result.profile_errors,
        )

    def test_archived_bundle_requires_lifecycle_metadata(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / f"old-policy_{bundle_uuid}.md"
        path.write_text(render_markdown({
            "type": "policy", "id": f"knowledge://example-org/cs/old-policy_{bundle_uuid}",
            "bundle_uuid": bundle_uuid, "title": "Old Policy", "status": "archived",
            "summary": "Old policy", "updated_at": "2026-07-14T00:00:00+00:00",
            "evidence": [f"evidence://example-org/manual/2026/07/14/{evidence_uuid}"],
            "extensions": {},
        }), encoding="utf-8")

        result = validate_document(path, self.root)

        self.assertIn("archived Bundle must define extensions.archive", result.profile_errors)

    def test_artifact_profile_requires_supported_type_and_sections(self):
        bundle_uuid = str(uuid.uuid4())
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "bundles" / "cs" / "runbooks" / f"artifact_{bundle_uuid}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown({
            "type": "runbook", "id": f"knowledge://example-org/cs/artifact_{bundle_uuid}",
            "bundle_uuid": bundle_uuid, "title": "Artifact Runbook", "status": "draft",
            "summary": "Artifact workflow", "updated_at": "2026-07-14T00:00:00+00:00",
            "evidence": [f"evidence://example-org/manual/2026/07/14/{evidence_uuid}"],
            "extensions": {"workflow": {
                "workflow_id": "artifact-workflow", "version": 1, "execution_mode": "guided",
                "required_inputs": [],
                "steps": [{"id": "review", "title": "Review", "kind": "validation"}],
                "approval_gates": [], "completion_criteria": ["Reviewed"],
                "artifact_profile": {"type": "unknown", "required_sections": []},
            }},
        }), encoding="utf-8")

        result = validate_document(path, self.root)

        self.assertIn("extensions.workflow.artifact_profile.type is invalid", result.profile_errors)
        self.assertIn(
            "extensions.workflow.artifact_profile.required_sections must be non-empty",
            result.profile_errors,
        )

    def test_available_evidence_requires_matching_original_checksum(self):
        evidence_uuid = str(uuid.uuid4())
        path = self.root / "evidence" / "manual" / "2026" / "07" / "14" / f"source_{evidence_uuid}.md"
        path.parent.mkdir(parents=True)
        (path.parent / "source.txt").write_text("actual", encoding="utf-8")
        path.write_text(render_markdown({
            "type": "evidence", "id": f"evidence://example-org/manual/2026/07/14/{evidence_uuid}",
            "title": "Source", "source_uuid": evidence_uuid, "provider": "manual",
            "source_ref": {"provider": "manual", "captured_from": "manual"},
            "captured_at": "2026-07-14T00:00:00+00:00", "status": "processed",
            "checksum": "sha256:" + "0" * 64, "original_file": "source.txt",
            "original_file_git_tracked": True, "extensions": {
                "availability": "available", "capture_context": {
                    "why_collected": "checksum test", "intended_use": ["test"],
                }
            },
        }), encoding="utf-8")

        result = validate_document(path, self.root)

        self.assertIn("Evidence original checksum does not match manifest", result.profile_errors)
