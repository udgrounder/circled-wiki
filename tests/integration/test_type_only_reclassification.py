from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from . import test_bundle_duplicate_reproduction as fixtures
from circled_wiki.core.candidates import promote_curation_candidate
from circled_wiki.core.curation import materialize_curation_candidate
from circled_wiki.core.curation_contract import validate_curation_output
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.notification_store import acknowledge_user_notification
from circled_wiki.core.repository import (
    apply_bundle_reclassification, create_bundle, find_document_by_id, propose_bundle_reclassification,
)
from circled_wiki.core.taxonomy_proposals import record_taxonomy_change_proposal
from circled_wiki.core.validator import validate_repository


class TypeOnlyReclassificationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        helper = fixtures.BundleDuplicateReproductionTests()
        self.root = helper._project(self.temporary.name).resolve()
        self.evidence_id = helper._evidence(self.root, "type-only", "Synthetic classification", 2026)
        output = helper._output(self.evidence_id)
        output.update(action="report", bundle_type="report", domain="operations", slug="type-only-report")
        created = materialize_curation_candidate(
            self.root, self.evidence_id, validate_curation_output(output, [self.evidence_id]),
            generated_by="curator", curation_receipt="test://classification",
        )
        self.bundle = find_document_by_id(self.root, created["bundle_id"])

    def _approval(self, domain="operations", bundle_type="reference", *, acknowledged=True, impacted=None):
        change = record_taxonomy_change_proposal(
            self.root, evidence_id=self.evidence_id, domain=domain, bundle_type=bundle_type,
            rationale="Explicitly reviewed classification change.",
            impacted_bundle_ids=impacted or [self.bundle.frontmatter["id"]],
        )
        notification = change["reclassification_notification"]["notification_id"]
        if acknowledged:
            acknowledge_user_notification(self.root.parent / "workspace", notification_id=notification, actor="owner")
        return notification

    def _apply(self, notification, *, root=None, domain="operations", bundle_type="reference", revision=None):
        return apply_bundle_reclassification(
            root or self.root, bundle_id=self.bundle.frontmatter["id"],
            expected_revision=revision if revision is not None else self.bundle.frontmatter["extensions"]["knowledge_revision"],
            domain=domain, bundle_type=bundle_type, actor="operator", rationale="Approved type-only reclassification.",
            approval_notification_id=notification,
        )

    def _preserved(self, before, result):
        for field in ("id", "bundle_uuid", "status", "evidence", "evidence_links", "owners"):
            self.assertEqual(result.frontmatter[field], before.frontmatter[field])
        self.assertEqual(result.path, before.path)
        self.assertEqual(result.body, before.body)
        self.assertEqual(result.frontmatter["type"], "reference")
        self.assertEqual(result.frontmatter["extensions"]["knowledge_revision"], before.frontmatter["extensions"]["knowledge_revision"] + 1)
        self.assertIn("reference", result.frontmatter["tags"])
        self.assertEqual(result.frontmatter["tags"][:3], ["bundles", "reference", "operations"])
        self.assertTrue(set(before.frontmatter["tags"]).issubset(result.frontmatter["tags"]))
        history = result.frontmatter["extensions"]["reclassification_history"]
        self.assertEqual(history[-1]["from"]["bundle_type"], "report")
        self.assertEqual(history[-1]["to"]["bundle_type"], "reference")
        self.assertEqual(history[-1]["from"]["path"], history[-1]["to"]["path"])
        self.assertTrue(all(item.is_valid for item in validate_repository(self.root)))

    def test_approved_draft_type_change_keeps_same_path_and_identity(self):
        proposal = propose_bundle_reclassification(self.root, bundle_id=self.bundle.frontmatter["id"], domain="operations", bundle_type="reference")
        self.assertEqual(proposal["from"]["path"], proposal["to"]["path"])
        self._preserved(self.bundle, self._apply(self._approval()))

    def test_approved_active_type_change_preserves_promotion_and_body_whitespace(self):
        promote_curation_candidate(self.root, self.bundle.frontmatter["id"], actor="publisher", security_receipt="test://security", automated=True)
        current = find_document_by_id(self.root, self.bundle.frontmatter["id"])
        body = "\r\n  # Original facts\r\n\r\n  Preserve indentation.\r\n"
        current.path.write_bytes((render_markdown(current.frontmatter, "").replace("\n", "\r\n") + body).encode())
        current = parse_markdown(current.path)
        self.bundle = current
        changed = self._apply(self._approval())
        self._preserved(current, changed)
        self.assertEqual(changed.frontmatter["extensions"]["curation"]["promotion"], current.frontmatter["extensions"]["curation"]["promotion"])

    def test_same_file_under_a_symlink_ancestor_is_not_a_destination_collision(self):
        alias = self.root.parent / "alias-project"
        alias.symlink_to(self.root.parent, target_is_directory=True)
        changed = self._apply(self._approval(), root=alias / "knowledge")
        self._preserved(self.bundle, changed)

    def test_true_noop_and_stale_revision_are_rejected_without_writes(self):
        before = self.bundle.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "must change"):
            self._apply(self._approval(bundle_type="report"), bundle_type="report")
        with self.assertRaisesRegex(ValueError, "revision conflict"):
            self._apply(self._approval(), revision=self.bundle.frontmatter["extensions"]["knowledge_revision"] + 1)
        self.assertEqual(self.bundle.path.read_bytes(), before)

    def test_missing_or_unacknowledged_approval_cannot_change_type(self):
        before = self.bundle.path.read_bytes()
        with self.assertRaises(ValueError):
            self._apply("")
        with self.assertRaises(ValueError):
            self._apply(self._approval(acknowledged=False))
        self.assertEqual(self.bundle.path.read_bytes(), before)

    def test_wrong_route_or_impact_approval_cannot_change_type(self):
        before = self.bundle.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "match"):
            self._apply(self._approval(bundle_type="guide"))
        other = create_bundle(self.root, domain="operations", slug="other", title="Other", bundle_type="report", summary="Other", evidence_id=self.evidence_id, tags=["fixture"])
        with self.assertRaisesRegex(ValueError, "impact list"):
            self._apply(self._approval(impacted=[other.frontmatter["id"]]))
        self.assertEqual(self.bundle.path.read_bytes(), before)

    def test_validator_failure_restores_exact_crlf_bytes(self):
        original = (render_markdown(self.bundle.frontmatter, "").replace("\n", "\r\n") + "\r\n # Original\r\n").encode()
        self.bundle.path.write_bytes(original)
        notification = self._approval()
        module = importlib.import_module(apply_bundle_reclassification.__module__)
        with patch.object(module, "validate_repository", side_effect=ValueError("injected Validator failure")), self.assertRaisesRegex(ValueError, "injected"):
            self._apply(notification)
        self.assertEqual(self.bundle.path.read_bytes(), original)

    def test_partial_write_failure_restores_exact_original_bytes(self):
        original = self.bundle.path.read_bytes()
        write = Path.write_bytes
        failed = []
        def fail_once(path, content):
            if path == self.bundle.path and not failed:
                failed.append(path)
                write(path, content[:16])
                raise OSError("injected write failure")
            return write(path, content)
        notification = self._approval()
        with patch.object(Path, "write_bytes", new=fail_once), self.assertRaisesRegex(OSError, "injected"):
            self._apply(notification)
        self.assertEqual(self.bundle.path.read_bytes(), original)

    def test_path_only_legacy_layout_change_still_moves(self):
        legacy = self.bundle.path.parent / "legacy" / self.bundle.path.name
        legacy.parent.mkdir()
        self.bundle.path.rename(legacy)
        changed = self._apply(self._approval(bundle_type="report"), bundle_type="report")
        self.assertEqual(changed.path, self.bundle.path)
        self.assertFalse(legacy.exists())
        self.assertEqual(changed.frontmatter["type"], "report")

    def test_different_destination_collision_remains_a_noop(self):
        foreign = create_bundle(self.root, domain="engineering", slug=self.bundle.path.stem, title="Foreign", bundle_type="reference", summary="Other", evidence_id=self.evidence_id, tags=["fixture"])
        before = {p: p.read_bytes() for p in (foreign.path, self.bundle.path)}
        notification = self._approval(domain="engineering")
        with self.assertRaisesRegex(ValueError, "destination already exists"):
            self._apply(notification, domain="engineering")
        self.assertTrue(all(p.read_bytes() == data for p, data in before.items()))

    def test_leaf_symlink_cannot_reclassify_a_file_outside_bundles(self):
        notification = self._approval()
        original = self.bundle.path.read_bytes()
        outside = self.root.parent / "outside.md"
        self.bundle.path.rename(outside)
        self.bundle.path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            propose_bundle_reclassification(self.root, bundle_id=self.bundle.frontmatter["id"], domain="operations", bundle_type="reference")
        with self.assertRaisesRegex(ValueError, "symbolic"):
            self._apply(notification)
        self.assertEqual(outside.read_bytes(), original)
        self.assertTrue(self.bundle.path.is_symlink())

    def test_destination_directory_symlink_is_rejected_without_writes(self):
        notification = self._approval(domain="engineering")
        original = self.bundle.path.read_bytes()
        outside = self.root.parent / "outside-directory"
        outside.mkdir()
        (outside / "sentinel.txt").write_text("preserve")
        (self.root / "bundles/engineering").symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            self._apply(notification, domain="engineering")
        self.assertEqual(self.bundle.path.read_bytes(), original)
        self.assertEqual(list(outside.iterdir()), [outside / "sentinel.txt"])
