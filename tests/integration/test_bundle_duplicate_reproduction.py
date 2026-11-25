"""Independent synthetic reproduction of cross-domain duplicate Bundle reports."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from circled_wiki.core.curation import materialize_curation_candidate, run_configured_curation, run_configured_curation_batch
from circled_wiki.core.curation_contract import validate_curation_output
from circled_wiki.core.curator import propose_update
from circled_wiki.core.ingest import ingest_evidence
from circled_wiki.core.pii import build_pii_scan_receipt
from circled_wiki.core.repository import create_bundle, find_document_by_id
from circled_wiki.core.validator import validate_repository


class BundleDuplicateReproductionTests(unittest.TestCase):
    def _project(self, directory):
        project = Path(directory)
        config = project / ".circled-wiki"
        config.mkdir()
        (config / "config.yaml").write_text(
            "schema_version: 1\ncuration:\n  enabled: true\n"
            "  provider: test\n  model: independent\n  command: duplicate-test-adapter\n",
            encoding="utf-8",
        )
        (config / "curation-taxonomy.yaml").write_text(
            "schema_version: 1\ndomains:\n"
            "  - id: operations\n    description: Existing operational knowledge.\n"
            "  - id: engineering\n    description: API integration knowledge.\n"
            "routing_rules:\n  - match_terms: [API, 보안]\n"
            "    description: API security integration guidance.\n"
            "    domain: engineering\n    bundle_type: guide\n    auto_create: true\n",
            encoding="utf-8",
        )
        contracts = project / "agent-rules/contracts"
        contracts.mkdir(parents=True)
        originals = Path(__file__).resolve().parents[2] / "agent-rules/contracts"
        for name in ("index.yaml", "curation.yaml"):
            shutil.copyfile(originals / name, contracts / name)
        return project / "knowledge"

    def _evidence(self, root, name, title, year):
        source = root / "inbox/manual" / (name + ".txt")
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(title + "\n" + name + " source details", encoding="utf-8")
        checksum = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
        return ingest_evidence(
            root, source, "manual", title=title,
            why_collected="Independent duplicate reproduction",
            intended_use=["예약 API 보안 변경"],
            captured_at=datetime(year, 1, 1, tzinfo=timezone.utc),
            pii_scan_receipt=build_pii_scan_receipt(
                checksum, scanner="test", scanner_version="1", result="passed",
                reviewed_by="security-test", receipt="test://independent-duplicate",
            ),
        ).evidence_id

    def _existing_and_new(self, root):
        old = self._evidence(root, "first", "예약·주문 API 2026 하반기 보안 변경", 2025)
        target = create_bundle(
            root, domain="operations", slug="reservation-api-security",
            title="예약·주문 API 2026 하반기 보안 변경", bundle_type="guide",
            summary="예약 및 주문 API의 하반기 보안 강화 안내.", evidence_id=old,
            tags=["예약", "API", "보안"], body="# 기존 보안 안내\n\n기존 상세 내용.\n",
        )
        new = self._evidence(root, "second", "예약 API 2026H2 보안 강화", 2026)
        return target, new

    def _output(self, evidence_id):
        return {
            "action": "guide", "domain": "engineering", "bundle_type": "guide",
            "title": "예약 API 2026H2 보안 강화", "summary": "추가된 보안 변경 안내.",
            "body": "# 추가 안내\n\n새로 접수된 보안 변경 사항.\n",
            "evidence_ids": [evidence_id], "existing_bundle_candidates": [],
            "tags": ["예약", "API", "보안"], "rationale": "Independent fixture.",
        }

    def _adapter(self, output, requests):
        original = subprocess.run

        def run(command, *args, **kwargs):
            if command[0] != "duplicate-test-adapter":
                return original(command, *args, **kwargs)
            requests.append(json.loads(kwargs["input"]))
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(output), stderr="")
        return run

    def test_normal_proposal_discovers_other_domain_and_updates_without_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._project(directory)
            target, evidence_id = self._existing_and_new(root)
            proposal = propose_update(root, evidence_id)
            self.assertIn(target.frontmatter["id"], [x["id"] for x in proposal["candidate_bundles"]])
            self.assertFalse(proposal["creation_authorized"])
            output = self._output(evidence_id)
            output.update(
                domain="operations", existing_bundle_candidates=[target.frontmatter["id"]],
                update_mode="append",
                base_body_checksum="sha256:" + hashlib.sha256(target.body.encode()).hexdigest(),
            )
            requests = []
            with patch("circled_wiki.core.curation.subprocess.run", side_effect=self._adapter(output, requests)):
                result = run_configured_curation(root, evidence_id)
            self.assertEqual(result["bundle_id"], target.frontmatter["id"])
            self.assertEqual(len(list((root / "bundles").rglob("*.md"))), 1)
            updated = find_document_by_id(root, target.frontmatter["id"])
            self.assertIn("기존 상세 내용", updated.body)
            self.assertIn("새로 접수된 보안 변경 사항", updated.body)
            self.assertIn(evidence_id, updated.frontmatter["evidence"])
            self.assertIn(target.frontmatter["id"], [x["id"] for x in requests[0]["proposal"]["candidate_bundles"]])
            self.assertTrue(all(r.is_valid for r in validate_repository(root)))

    def test_adapter_cannot_create_new_bundle_by_ignoring_discovered_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._project(directory)
            target, evidence_id = self._existing_and_new(root)
            requests = []
            with patch("circled_wiki.core.curation.subprocess.run", side_effect=self._adapter(self._output(evidence_id), requests)):
                result = run_configured_curation(root, evidence_id)
            self.assertFalse(requests[0]["proposal"]["creation_authorized"])
            self.assertEqual(result["action"], "needs_review")
            self.assertIn(result["reason"], {"taxonomy_creation_not_authorized", "contract_or_gate_rejected"})
            self.assertEqual(len(list((root / "bundles").rglob("*.md"))), 1)
            self.assertEqual(find_document_by_id(root, target.frontmatter["id"]).body, target.body)

    def test_same_evidence_materialization_retry_is_idempotent_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._project(directory)
            evidence_id = self._evidence(root, "retry", "예약 API 보안 변경", 2026)
            output = validate_curation_output(self._output(evidence_id), [evidence_id])
            first = materialize_curation_candidate(root, evidence_id, output, generated_by="test", curation_receipt="test://retry")
            retry = materialize_curation_candidate(root, evidence_id, output, generated_by="test", curation_receipt="test://retry")
            self.assertEqual(first["action"], "created")
            self.assertEqual(retry["action"], "reused")
            self.assertEqual(first["bundle_id"], retry["bundle_id"])
            self.assertEqual(len(list((root / "bundles").rglob("*.md"))), 1)

    def test_shared_cache_drops_misses_even_if_promotion_fails_after_draft_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._project(directory)
            title = "예약 API 2026H2 보안 강화"
            first = self._evidence(root, "failure-one", title, 2026)
            second = self._evidence(root, "failure-two", title, 2026)
            cache = {}
            requests = []
            with patch("circled_wiki.core.curation.subprocess.run", side_effect=self._adapter(self._output(first), requests)), patch(
                "circled_wiki.core.curation._auto_promote_materialized_candidate", side_effect=OSError("promotion failed after write"),
            ):
                result = run_configured_curation(root, first, search_cache=cache)
            self.assertEqual(result["action"], "needs_review")
            self.assertEqual(len(list((root / "bundles").rglob("*.md"))), 1)
            proposal = propose_update(root, second, search_cache=cache)
            self.assertEqual(len(proposal["candidate_bundles"]), 1)
            self.assertFalse(proposal["creation_authorized"])
            self.assertTrue(all(item.is_valid for item in validate_repository(root)))

    def test_batch_discovers_bundle_created_by_previous_evidence_and_updates_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self._project(directory)
            title = "예약 API 2026H2 보안 강화"
            evidence_ids = [self._evidence(root, name, title, 2026) for name in ("batch-one", "batch-two", "batch-three")]
            requests = []
            original = subprocess.run

            def adapter(command, *args, **kwargs):
                if command[0] != "duplicate-test-adapter":
                    return original(command, *args, **kwargs)
                request = json.loads(kwargs["input"])
                requests.append(request)
                output = self._output(request["evidence_id"])
                candidates = request["proposal"]["candidate_bundles"]
                if candidates:
                    target = candidates[0]
                    output.update(
                        domain=target["domain"], existing_bundle_candidates=[target["id"]],
                        update_mode="append", base_body_checksum=target["body_checksum"],
                    )
                return subprocess.CompletedProcess(command, 0, stdout=json.dumps(output), stderr="")

            with patch("circled_wiki.core.curation.subprocess.run", side_effect=adapter):
                result = run_configured_curation_batch(root)
            self.assertEqual(result["attempted"], 3)
            self.assertEqual(len(requests), 3)
            self.assertEqual(requests[0]["proposal"]["candidate_bundles"], [])
            second = requests[1]["proposal"]["candidate_bundles"]
            third = requests[2]["proposal"]["candidate_bundles"]
            self.assertEqual(len(second), 1)
            self.assertEqual(len(third), 1)
            self.assertEqual(second[0]["id"], third[0]["id"])
            self.assertNotEqual(second[0]["body_checksum"], third[0]["body_checksum"])
            self.assertFalse(requests[1]["proposal"]["creation_authorized"])
            self.assertFalse(requests[2]["proposal"]["creation_authorized"])
            self.assertEqual(len(list((root / "bundles").rglob("*.md"))), 1)
            self.assertEqual(result["counts"]["auto_promoted"], 1)
            self.assertEqual(result["counts"]["auto_updated"], 2)
            bundle = find_document_by_id(root, second[0]["id"])
            self.assertEqual(set(bundle.frontmatter["evidence"]), set(evidence_ids))
            self.assertTrue(all(item.is_valid for item in validate_repository(root)))
