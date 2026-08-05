import unittest
import tempfile
import json
from pathlib import Path

from circled_wiki.core.service import KnowledgeService
from circled_wiki.mcp.server import available_tools, handle_request


class McpServerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.knowledge_root = Path(self.temporary_directory.name) / "knowledge"
        self.knowledge_root.mkdir()

    def test_lists_documented_tools(self):
        service = KnowledgeService(self.knowledge_root)
        response = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, service)
        self.assertEqual(response["result"]["tools"], available_tools("read_only"))

    def test_unknown_tool_returns_tool_error(self):
        service = KnowledgeService(self.knowledge_root)
        response = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "missing", "arguments": {}}}, service)
        self.assertTrue(response["result"]["isError"])

    def test_quality_tools_are_dispatched(self):
        service = KnowledgeService(self.knowledge_root)
        response = handle_request({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "audit_knowledge", "arguments": {}},
        }, service, access_mode="operator")
        self.assertFalse(response["result"].get("isError", False))

    def test_audit_is_available_in_read_only_mode(self):
        names = {tool["name"] for tool in available_tools("read_only")}
        self.assertIn("audit_knowledge", names)
        self.assertIn("list_curation_candidates", names)
        self.assertIn("list_curation_queue", names)
        self.assertNotIn("refresh_curation_queue", names)
        self.assertNotIn("record_evidence_pii_scan", names)
        self.assertNotIn("review_curation_candidate", names)
        operator_names = {tool["name"] for tool in available_tools("operator")}
        self.assertNotIn("record_evidence_pii_scan", operator_names)
        self.assertIn("review_data_protection", operator_names)
        self.assertIn("review_curation_candidate", operator_names)

    def test_initialize_uses_configured_organization_name(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "knowledge").mkdir()
            (project / ".circled-wiki").mkdir()
            (project / ".circled-wiki" / "config.yaml").write_text(
                "schema_version: 1\norganization:\n  id: acme\n  name: Acme\n",
                encoding="utf-8",
            )
            response = handle_request(
                {"jsonrpc": "2.0", "id": 7, "method": "initialize", "params": {}},
                KnowledgeService(project / "knowledge"),
            )
            self.assertEqual(response["result"]["serverInfo"]["name"], "acme-knowledge")

    def test_read_only_mode_blocks_mutation_tools(self):
        service = KnowledgeService(self.knowledge_root)
        response = handle_request({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "prepare_task", "arguments": {
                "workflow_id": "missing", "request": "test",
            }},
        }, service, access_mode="read_only")
        self.assertTrue(response["result"]["isError"])
        self.assertIn("access mode", response["result"]["content"][0]["text"])

    def test_operator_cannot_bypass_inbox_reconciliation_with_direct_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            inbox = knowledge_root / "inbox"
            inbox.mkdir(parents=True)
            (inbox / "reference.txt").write_text("reference", encoding="utf-8")
            service = KnowledgeService(knowledge_root)
            response = handle_request({
                "jsonrpc": "2.0", "id": 5, "method": "tools/call",
                "params": {"name": "ingest_evidence", "arguments": {
                    "inbox_path": "reference.txt", "provider": "user",
                    "why_collected": "사용자 제공 자료", "intended_use": ["pilot"],
                }},
            }, service, access_mode="operator")

            self.assertTrue(response["result"]["isError"])
            self.assertIn("not available", response["result"]["content"][0]["text"])
            self.assertFalse(any((knowledge_root / "evidence").rglob("*.md")))

    def test_operator_capture_only_lands_pending_inbox_item(self):
        with tempfile.TemporaryDirectory() as directory:
            knowledge_root = Path(directory) / "knowledge"
            service = KnowledgeService(knowledge_root)
            response = handle_request({
                "jsonrpc": "2.0", "id": 8, "method": "tools/call",
                "params": {"name": "capture_conversation", "arguments": {
                    "content": "# Transcript\n\n## User\n\n메뉴 이미지를 만들어줘.\n",
                    "provider": "codex",
                    "title": "이미지 생성 대화",
                    "why_collected": "Runbook 개선 근거",
                    "intended_use": ["ai-digital-menu-image-production"],
                    "idempotency_key": "thread-3:turns-1-1",
                    "thread_ref": "thread-3",
                    "turn_from": 1,
                    "turn_to": 1,
                }},
            }, service, access_mode="operator")

            self.assertFalse(response["result"].get("isError", False))
            payload = json.loads(response["result"]["content"][0]["text"])
            self.assertEqual(payload["status"], "pending")
            self.assertNotIn("evidence_id", payload)
            self.assertNotIn("curation_proposal", payload)
            inbox_path = knowledge_root.parent / payload["inbox_path"]
            self.assertTrue(inbox_path.is_file())
            self.assertIn("메뉴 이미지를 만들어줘", inbox_path.read_text(encoding="utf-8"))

            reviewed = handle_request({
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "review_data_protection", "arguments": {
                    "intake_id": payload["intake_id"], "actor": "inspection-agent",
                    "context": "",
                    "checks": ["source_access_scope", "personal_context", "confidential_business_context", "publication_scope"],
                    "rationale": "제한 검토 대상이 없는 일반 업무 대화다.",
                }},
            }, service, access_mode="operator")
            self.assertFalse(reviewed["result"].get("isError", False))

            inspected = handle_request({
                "jsonrpc": "2.0", "id": 9, "method": "tools/call",
                "params": {"name": "inspect_inbox", "arguments": {"limit": 10}},
            }, service, access_mode="operator")
            inspection = json.loads(inspected["result"]["content"][0]["text"])
            self.assertEqual(inspection["items"][0]["gate_status"], "ready_for_acceptance")

            accepted = handle_request({
                "jsonrpc": "2.0", "id": 10, "method": "tools/call",
                "params": {"name": "accept_inbox", "arguments": {
                    "intake_id": payload["intake_id"], "actor": "inspection-agent"
                }},
            }, service, access_mode="operator")
            self.assertFalse(accepted["result"].get("isError", False))
            ingested = handle_request({
                "jsonrpc": "2.0", "id": 12, "method": "tools/call",
                "params": {"name": "ingest_accepted", "arguments": {"limit": 10}},
            }, service, access_mode="operator")
            batch = json.loads(ingested["result"]["content"][0]["text"])
            self.assertEqual(batch["ingested_count"], 1)

            repeated = handle_request({
                "jsonrpc": "2.0", "id": 12, "method": "tools/call",
                "params": {"name": "capture_conversation", "arguments": {
                    "content": "# Transcript\n\n## User\n\n메뉴 이미지를 만들어줘.\n",
                    "provider": "codex",
                    "title": "이미지 생성 대화",
                    "why_collected": "Runbook 개선 근거",
                    "intended_use": ["ai-digital-menu-image-production"],
                    "idempotency_key": "thread-3:turns-1-1",
                    "thread_ref": "thread-3",
                    "turn_from": 1,
                    "turn_to": 1,
                }},
            }, service, access_mode="operator")
            self.assertFalse(repeated["result"].get("isError", False))
            reused = json.loads(repeated["result"]["content"][0]["text"])
            self.assertEqual(reused["status"], "ingested")
            self.assertIsNone(reused["intake_id"])
            self.assertTrue(reused["evidence_id"].startswith("evidence/example-org/"))
