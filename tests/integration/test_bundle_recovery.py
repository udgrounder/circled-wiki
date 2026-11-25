from copy import deepcopy
import json
import io
import os
import stat
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from . import test_bundle_duplicate_reproduction as fixtures
from circled_wiki.core import bundle_recovery as recovery
from circled_wiki.core.candidates import promote_curation_candidate
from circled_wiki.core.curation import materialize_curation_candidate
from circled_wiki.core.curation_contract import validate_curation_output
from circled_wiki.core.frontmatter import parse_markdown, render_markdown
from circled_wiki.core.repository import find_document_by_id
from circled_wiki.core.search import search_knowledge
from circled_wiki.core.service import KnowledgeService
from circled_wiki.core.validator import validate_repository


class BundleRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        helper = fixtures.BundleDuplicateReproductionTests()
        self.root = helper._project(self.temporary.name)
        self.bundles = []
        for name in ("canonical", "duplicate"):
            evidence_id = helper._evidence(self.root, name, "예약 API 보안 변경", 2026)
            payload = helper._output(evidence_id)
            payload["body"] = "# Details\n\n" + name + " unique content.\n"
            candidate = materialize_curation_candidate(
                self.root, evidence_id, validate_curation_output(payload, [evidence_id]),
                generated_by="generator", curation_receipt="test://recovery",
            )
            promote_curation_candidate(self.root, candidate["bundle_id"], actor="publisher",
                                      security_receipt="test://security", automated=True)
            self.bundles.append(find_document_by_id(self.root, candidate["bundle_id"]))
        self.target, self.source = self.bundles
        self.before = {d.path: d.path.read_bytes() for d in self.bundles}
        self.body = self.target.body + "\n" + self.source.body
        self.plan_args = dict(source_id=self.source.frontmatter["id"], target_id=self.target.frontmatter["id"], merged_body=self.body)
        self.plan = recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)
        self.apply_args = dict(**self.plan_args, expected_source_revision=self.plan["source"]["revision"],
                               expected_target_revision=self.plan["target"]["revision"],
                               approved_plan_checksum=self.plan["plan_checksum"], actor="operator", reviewed_by="reviewer",
                               request_ref="test://user-request", security_receipt="test://security-review")

    def _unchanged(self):
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes(), data)
        self.assertFalse((self.root.parent / self.plan["archive_path"]).exists())

    def test_preview_is_read_only(self):
        before = {p: p.read_bytes() for p in self.root.parent.rglob("*") if p.is_file()}
        self.assertEqual(KnowledgeService(self.root).plan_duplicate_bundle_recovery(**self.plan_args), self.plan)
        after = {p: p.read_bytes() for p in self.root.parent.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.root.parent / ".runtime/bundle-recoveries").exists())
        self.assertFalse((self.root.parent / ".runtime/locks/bundle-recovery.lock").exists())

    def test_active_merge_archive_and_explicit_rollback_preserve_identity_and_bytes(self):
        result = KnowledgeService(self.root).recover_duplicate_bundle(**self.apply_args)
        self.assertEqual(result["status"], "applied", result)
        target = find_document_by_id(self.root, self.target.frontmatter["id"])
        source = find_document_by_id(self.root, self.source.frontmatter["id"])
        self.assertEqual(target.frontmatter["status"], "active")
        self.assertEqual(target.frontmatter["bundle_uuid"], self.target.frontmatter["bundle_uuid"])
        self.assertEqual(target.body, self.body)
        self.assertEqual(set(target.frontmatter["evidence"]), set(self.target.frontmatter["evidence"] + self.source.frontmatter["evidence"]))
        self.assertEqual(source.frontmatter["status"], "archived")
        self.assertEqual(source.body, self.source.body)
        self.assertEqual(source.frontmatter["bundle_uuid"], self.source.frontmatter["bundle_uuid"])
        self.assertEqual(source.frontmatter["extensions"]["curation"]["promotion"], self.source.frontmatter["extensions"]["curation"]["promotion"])
        self.assertEqual(source.frontmatter["extensions"]["review_state"], "merged")
        self.assertEqual(source.path, self.root.parent / self.plan["archive_path"])
        self.assertTrue(all(r.is_valid for r in validate_repository(self.root)))
        self.assertNotIn(source.frontmatter["id"], [h.document_id for h in search_knowledge(self.root, "API")])
        receipt = json.loads((self.root.parent / result["receipt"]).read_text())
        self.assertNotIn("unique content", json.dumps(receipt))
        rollback = KnowledgeService(self.root).rollback_duplicate_bundle_recovery(result["transaction_id"], actor="rollback-operator")
        self.assertEqual(rollback["status"], "rolled_back")
        self._unchanged()
        self.assertEqual(recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id=result["transaction_id"], actor="rollback-operator")["status"], "rolled_back")

    def test_stale_bytes_body_evidence_revision_and_archive_collision_are_rejected(self):
        for change in ("source", "target", "body", "evidence", "revision", "archive"):
            with self.subTest(change=change):
                restoration = None
                args = deepcopy(self.apply_args)
                if change in {"source", "target"}:
                    path = getattr(self, change).path
                    restoration = (path, path.read_bytes())
                    path.write_bytes(path.read_bytes() + b"\nConcurrent body edit\n")
                elif change == "body":
                    args["merged_body"] += "\nDifferent review body\n"
                elif change == "evidence":
                    document = find_document_by_id(self.root, self.source.frontmatter["evidence"][0])
                    restoration = (document.path, document.path.read_bytes())
                    document.frontmatter["title"] += " changed"
                    document.path.write_text(render_markdown(document.frontmatter, document.body))
                elif change == "revision":
                    args["expected_source_revision"] += 1
                else:
                    path = self.root.parent / self.plan["archive_path"]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"existing archive")
                try:
                    with self.assertRaises(ValueError):
                        recovery.recover_duplicate_bundle(self.root, **args)
                finally:
                    if restoration:
                        restoration[0].write_bytes(restoration[1])
                    if change == "archive":
                        self.assertEqual(path.read_bytes(), b"existing archive")
                        path.unlink()
                self._unchanged()

    def test_failure_after_target_write_or_archive_restores_original_bytes(self):
        for fail_call in (2, 3):
            with self.subTest(fail_call=fail_call):
                validate = recovery._validate
                calls = []
                def injected(root):
                    calls.append(root)
                    if len(calls) == fail_call:
                        raise ValueError("injected validation failure")
                    return validate(root)
                with patch.object(recovery, "_validate", side_effect=injected):
                    result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
                self.assertEqual(result["status"], "rolled_back", result)
                self._unchanged()

    def test_archive_move_failure_and_receipt_write_failure_roll_back(self):
        with patch.object(recovery.os, "link", side_effect=OSError("move failure")):
            result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.assertEqual(result["status"], "rolled_back")
        self._unchanged()
        write_json = recovery._json
        failures = []
        def injected(path, value):
            if path.parent.name == "bundle-rebuilds" and not failures:
                failures.append(path)
                raise OSError("receipt failure")
            return write_json(path, value)
        with patch.object(recovery, "_json", side_effect=injected):
            result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.assertEqual(result["status"], "rolled_back")
        self._unchanged()

    def test_interruption_between_archive_link_and_unlink_can_be_recovered(self):
        link = os.link
        def interrupt(source, destination):
            link(source, destination)
            raise KeyboardInterrupt("interruption")
        with patch.object(recovery.os, "link", side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        directory = next((self.root.parent / ".runtime/bundle-recoveries").iterdir())
        result = recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id=directory.name, actor="rollback-operator")
        self.assertEqual(result["status"], "rolled_back")
        self._unchanged()

    def test_late_archive_collision_with_identical_bytes_is_not_deleted(self):
        foreign = []
        def collide(source, destination):
            data = Path(source).read_bytes()
            Path(destination).write_bytes(data)
            foreign.append(data)
            raise FileExistsError("another writer created the archive")
        with patch.object(recovery.os, "link", side_effect=collide):
            result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.assertEqual(result["status"], "partial_rollback")
        self.assertEqual((self.root.parent / self.plan["archive_path"]).read_bytes(), foreign[0])
        for path, data in self.before.items():
            self.assertEqual(path.read_bytes(), data)

    def test_rollback_preserves_another_writers_changes(self):
        validate = recovery._validate
        calls = []
        other = []
        def injected(root):
            calls.append(root)
            if len(calls) == 2:
                data = self.target.path.read_bytes() + b"\nAnother writer\n"
                other.append(data)
                self.target.path.write_bytes(data)
                raise ValueError("failure after concurrent write")
            return validate(root)
        with patch.object(recovery, "_validate", side_effect=injected):
            result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.assertEqual(result["status"], "partial_rollback")
        self.assertTrue(result["rollback_conflicts"])
        self.assertEqual(self.target.path.read_bytes(), other[0])
        self.assertEqual(self.source.path.read_bytes(), self.before[self.source.path])

    def test_explicit_rollback_does_not_resurrect_an_external_target_deletion(self):
        result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.target.path.unlink()
        rollback = recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id=result["transaction_id"], actor="rollback-operator")
        self.assertEqual(rollback["status"], "partial_rollback")
        self.assertFalse(self.target.path.exists())
        self.assertEqual(self.source.path.read_bytes(), self.before[self.source.path])

    def test_rollback_preserves_tightened_permissions(self):
        result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        self.target.path.chmod(0o600)
        rollback = recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id=result["transaction_id"], actor="rollback-operator")
        self.assertEqual(rollback["status"], "partial_rollback")
        self.assertEqual(stat.S_IMODE(self.target.path.stat().st_mode), 0o600)

    def test_archive_only_requires_prior_integration_and_keeps_target_bytes(self):
        with self.assertRaisesRegex(ValueError, "already integrated"):
            recovery.plan_duplicate_bundle_recovery(self.root, **dict(self.plan_args, archive_only=True))
        data = deepcopy(self.target.frontmatter)
        data["evidence"] += self.source.frontmatter["evidence"]
        self.target.path.write_text(render_markdown(data, self.body))
        target_before = self.target.path.read_bytes()
        body = parse_markdown(self.target.path).body
        plan_args = dict(self.plan_args, merged_body=body, archive_only=True)
        plan = recovery.plan_duplicate_bundle_recovery(self.root, **plan_args)
        args = dict(self.apply_args, **plan_args)
        args["approved_plan_checksum"] = plan["plan_checksum"]
        result = recovery.recover_duplicate_bundle(self.root, **args)
        self.assertEqual(result["status"], "applied", result)
        self.assertEqual(self.target.path.read_bytes(), target_before)

    def test_reviewer_separation_references_and_path_traversal_are_rejected(self):
        args = dict(self.apply_args, reviewed_by="operator")
        with self.assertRaisesRegex(ValueError, "reviewer"):
            recovery.recover_duplicate_bundle(self.root, **args)
        task = self.root.parent / "workspace/task/linked.md"
        task.parent.mkdir(parents=True, exist_ok=True)
        task.write_text("See " + self.source.path.name)
        args = dict(self.apply_args, approved_plan_checksum=recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)["plan_checksum"])
        with self.assertRaisesRegex(ValueError, "path references"):
            recovery.recover_duplicate_bundle(self.root, **args)
        with self.assertRaises(ValueError):
            recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id="../../outside", actor="rollback-operator")
        self._unchanged()

    def test_cli_plan_apply_and_rollback(self):
        from circled_wiki.cli.__main__ import main
        body_file = self.root.parent / "merged-body.txt"
        body_file.write_text(self.body)
        common = ["--source", self.plan_args["source_id"], "--target", self.plan_args["target_id"], "--merged-body-file", str(body_file)]
        def command(args):
            output = io.StringIO()
            with patch("circled_wiki.cli.__main__.project_root", return_value=self.root.parent), patch.object(sys, "argv", ["circled-wiki", *args]), patch("sys.stdout", output):
                status = main()
            return status, json.loads(output.getvalue())
        status, plan = command(["plan-duplicate-bundle-recovery", *common])
        self.assertEqual(status, 0)
        status, applied = command(["recover-duplicate-bundle", *common,
            "--expected-source-revision", str(plan["source"]["revision"]),
            "--expected-target-revision", str(plan["target"]["revision"]),
            "--approved-plan-checksum", plan["plan_checksum"], "--actor", "operator", "--reviewed-by", "reviewer",
            "--request-ref", "test://request", "--security-receipt", "test://security"])
        self.assertEqual(status, 0, applied)
        status, rolled_back = command(["rollback-duplicate-bundle-recovery", "--transaction", applied["transaction_id"], "--actor", "rollback-operator"])
        self.assertEqual(status, 0, rolled_back)
        receipt = json.loads((self.root.parent / rolled_back["receipt"]).read_text())
        self.assertEqual(receipt["rollback_attempts"][-1]["actor"], "rollback-operator")
        self._unchanged()

    def test_target_frontmatter_path_references_are_not_silently_preserved(self):
        data = deepcopy(self.target.frontmatter)
        data["extensions"]["related_path"] = self.source.path.relative_to(self.root).as_posix()
        self.target.path.write_text(render_markdown(data, self.target.body))
        plan = recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)
        self.assertIn(self.target.path.relative_to(self.root.parent).as_posix(), plan["path_references"])
        args = dict(self.apply_args, approved_plan_checksum=plan["plan_checksum"])
        with self.assertRaisesRegex(ValueError, "path references"):
            recovery.recover_duplicate_bundle(self.root, **args)

    def test_same_bundle_restricted_and_symlink_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            recovery.plan_duplicate_bundle_recovery(self.root, **dict(self.plan_args, source_id=self.plan_args["target_id"]))
        data = deepcopy(self.source.frontmatter)
        data["extensions"]["visibility"] = "restricted"
        self.source.path.write_text(render_markdown(data, self.source.body))
        with self.assertRaisesRegex(ValueError, "unrestricted"):
            recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)
        self.source.path.write_bytes(self.before[self.source.path])
        relocated = self.source.path.with_suffix(".saved")
        self.source.path.rename(relocated)
        self.source.path.symlink_to(relocated)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)

    def test_active_duplicate_cannot_be_replaced_by_an_unpublished_draft(self):
        data = deepcopy(self.target.frontmatter)
        data["status"] = "draft"
        self.target.path.write_text(render_markdown(data, self.target.body))
        with self.assertRaisesRegex(ValueError, "active canonical"):
            recovery.plan_duplicate_bundle_recovery(self.root, **self.plan_args)

    def test_rollback_rejects_a_symbolic_journal_file(self):
        result = recovery.recover_duplicate_bundle(self.root, **self.apply_args)
        directory = self.root.parent / ".runtime/bundle-recoveries" / result["transaction_id"]
        journal = directory / "journal.json"
        relocated = directory / "other.json"
        journal.rename(relocated)
        journal.symlink_to(relocated)
        with self.assertRaisesRegex(ValueError, "symbolic"):
            recovery.rollback_duplicate_bundle_recovery(self.root, transaction_id=result["transaction_id"], actor="rollback-operator")
