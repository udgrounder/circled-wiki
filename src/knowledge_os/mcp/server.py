"""Minimal stdio JSON-RPC MCP adapter for Knowledge Service and Workflow tools."""

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from knowledge_os.config.paths import project_root
from knowledge_os.core.publisher import PublishError
from knowledge_os.core.service import KnowledgeService


TOOLS = [
    {"name": "search_knowledge", "description": "Search knowledge Bundles and Evidence manifests.", "inputSchema": {"type": "object", "required": ["query"], "properties": {"query": {"type": "string"}, "filters": {"type": "object"}}}},
    {"name": "read_bundle", "description": "Read one Bundle with frontmatter and Markdown body.", "inputSchema": {"type": "object", "required": ["bundle_id"], "properties": {"bundle_id": {"type": "string"}}}},
    {"name": "prepare_context", "description": "Create a source-preserving context package for a task.", "inputSchema": {"type": "object", "required": ["task_description"], "properties": {"task_description": {"type": "string"}, "bundle_ids": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "propose_update", "description": "Create a non-writing Evidence-based curation proposal.", "inputSchema": {"type": "object", "required": ["evidence_id"], "properties": {"evidence_id": {"type": "string"}}}},
    {"name": "propose_pending", "description": "Batch pending non-restricted Evidence into non-writing curation proposals.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}}}},
    {"name": "ingest_evidence", "description": "Ingest a user, Batch, or Hermes file already placed under knowledge/inbox/.", "inputSchema": {"type": "object", "required": ["inbox_path", "provider", "why_collected", "intended_use"], "properties": {"inbox_path": {"type": "string"}, "provider": {"type": "string"}, "why_collected": {"type": "string"}, "intended_use": {"type": "array", "minItems": 1, "items": {"type": "string"}}, "title": {"type": "string"}, "source_url": {"type": "string"}, "source_locator": {"type": "string"}, "captured_from": {"type": "string", "enum": ["api", "webhook", "manual", "upload", "sync"]}, "reuse_value": {"type": "string", "enum": ["high", "medium", "low"]}, "retention_class": {"type": "string", "enum": ["workflow_reference", "decision_record", "outcome", "general_reference", "ephemeral"]}, "sensitivity_review": {"type": "string", "enum": ["completed", "required", "not_applicable"]}, "idempotency_key": {"type": "string"}, "content_mode": {"type": "string", "enum": ["external_file", "embedded"]}}}},
    {"name": "capture_conversation", "description": "Land a UTF-8 conversation as a pending self-contained Markdown item under inbox/<provider>/ without ingesting it.", "inputSchema": {"type": "object", "required": ["content", "provider", "title", "why_collected", "intended_use", "idempotency_key"], "properties": {"content": {"type": "string", "minLength": 1}, "provider": {"type": "string"}, "title": {"type": "string"}, "why_collected": {"type": "string"}, "intended_use": {"type": "array", "minItems": 1, "items": {"type": "string"}}, "idempotency_key": {"type": "string"}, "thread_ref": {"type": "string"}, "turn_from": {"type": "integer", "minimum": 0}, "turn_to": {"type": "integer", "minimum": 0}, "artifacts": {"type": "array", "items": {"type": "object"}}, "sensitivity_review": {"type": "string", "enum": ["completed", "required", "not_applicable"], "default": "required"}}}},
    {"name": "capture_document", "description": "Land an external source document as a pending Inbox item with provenance; it does not ingest or curate it.", "inputSchema": {"type": "object", "required": ["content", "provider", "title", "why_collected", "intended_use", "idempotency_key"], "properties": {"content": {"type": "string", "minLength": 1}, "provider": {"type": "string"}, "title": {"type": "string"}, "why_collected": {"type": "string"}, "intended_use": {"type": "array", "minItems": 1, "items": {"type": "string"}}, "idempotency_key": {"type": "string"}, "source_url": {"type": "string"}, "source_locator": {"type": "string"}, "captured_from": {"type": "string", "enum": ["api", "webhook", "manual", "upload", "sync"], "default": "sync"}, "sensitivity_review": {"type": "string", "enum": ["completed", "required", "not_applicable"], "default": "required"}}}},
    {"name": "capture_file", "description": "Land a PDF, Word, HTML, or other source file as a pending Inbox item with an original-preserving envelope; it does not ingest or curate it.", "inputSchema": {"type": "object", "required": ["payload_base64", "original_filename", "provider", "title", "why_collected", "intended_use", "idempotency_key"], "properties": {"payload_base64": {"type": "string", "minLength": 1}, "original_filename": {"type": "string"}, "provider": {"type": "string"}, "title": {"type": "string"}, "why_collected": {"type": "string"}, "intended_use": {"type": "array", "minItems": 1, "items": {"type": "string"}}, "idempotency_key": {"type": "string"}, "source_url": {"type": "string"}, "source_locator": {"type": "string"}, "captured_from": {"type": "string", "enum": ["api", "webhook", "manual", "upload", "sync"], "default": "upload"}, "sensitivity_review": {"type": "string", "enum": ["completed", "required", "not_applicable"], "default": "required"}}}},
    {"name": "inspect_inbox", "description": "Read-only validation of pending conversation, document, and file Inbox items against the inspection gate.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}}}},
    {"name": "review_inbox_sensitivity", "description": "Record an identified human sensitivity-review decision before Inbox acceptance.", "inputSchema": {"type": "object", "required": ["intake_id", "actor", "decision"], "properties": {"intake_id": {"type": "string"}, "actor": {"type": "string"}, "decision": {"type": "string", "enum": ["completed", "not_applicable"]}}}},
    {"name": "accept_inbox", "description": "Record an identified inspector acceptance for one pending Inbox item that passes all gates.", "inputSchema": {"type": "object", "required": ["intake_id", "actor"], "properties": {"intake_id": {"type": "string"}, "actor": {"type": "string"}}}},
    {"name": "ingest_accepted", "description": "Convert accepted Inbox items to Evidence without performing curation.", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100}}}},
    {"name": "create_draft_bundle", "description": "Create a new draft Bundle from one existing Evidence item.", "inputSchema": {"type": "object", "required": ["domain", "slug", "title", "bundle_type", "summary", "evidence_id", "body", "actor"], "properties": {"domain": {"type": "string"}, "slug": {"type": "string"}, "title": {"type": "string"}, "bundle_type": {"type": "string"}, "summary": {"type": "string"}, "evidence_id": {"type": "string"}, "body": {"type": "string"}, "actor": {"type": "string"}}}},
    {"name": "apply_bundle_revision", "description": "Apply a validated Bundle revision using optimistic concurrency and Evidence backlink updates.", "inputSchema": {"type": "object", "required": ["bundle_id", "expected_revision", "frontmatter", "body", "actor"], "properties": {"bundle_id": {"type": "string"}, "expected_revision": {"type": "integer", "minimum": 1}, "frontmatter": {"type": "object"}, "body": {"type": "string"}, "actor": {"type": "string"}}}},
    {"name": "publish_changes", "description": "Validate and automatically Git commit knowledge changes.", "inputSchema": {"type": "object", "required": ["commit_message"], "properties": {"commit_message": {"type": "string"}}}},
    {"name": "validate_result", "description": "Validate managed Knowledge documents.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "find_workflow", "description": "Find active executable Runbooks for a user request.", "inputSchema": {"type": "object", "required": ["request"], "properties": {"request": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}}},
    {"name": "prepare_task", "description": "Create a runtime-only task snapshot from an active Workflow.", "inputSchema": {"type": "object", "required": ["workflow_id", "request"], "properties": {"workflow_id": {"type": "string"}, "request": {"type": "string"}, "inputs": {"type": "object"}}}},
    {"name": "prepare_runbook_refresh", "description": "Create a Runbook Refresh Task for an expired or explicitly requested review.", "inputSchema": {"type": "object", "required": ["workflow_id", "request", "requested_by"], "properties": {"workflow_id": {"type": "string"}, "request": {"type": "string"}, "requested_by": {"type": "string"}, "reason": {"type": "string", "enum": ["expired", "user_requested", "user_reference", "owner_requested", "source_change", "outcome_signal", "security_or_compliance"]}}}},
    {"name": "submit_runbook_reference", "description": "Submit user-provided Evidence as a candidate for a Runbook Refresh review.", "inputSchema": {"type": "object", "required": ["workflow_id", "evidence_id", "submitted_by", "note"], "properties": {"workflow_id": {"type": "string"}, "evidence_id": {"type": "string"}, "submitted_by": {"type": "string"}, "note": {"type": "string"}}}},
    {"name": "record_reference_assessment", "description": "Record an independently verified assessment of candidate Runbook Evidence.", "inputSchema": {"type": "object", "required": ["task_id", "evidence_id", "authority", "recency", "applicability", "corroboration", "disposition", "rationale", "assessed_by", "verified_by"], "properties": {"task_id": {"type": "string"}, "evidence_id": {"type": "string"}, "authority": {"type": "string", "enum": ["primary", "official_secondary", "internal_experience", "informal"]}, "recency": {"type": "string", "enum": ["newer", "same_period", "older", "unknown"]}, "applicability": {"type": "string", "enum": ["full", "partial", "out_of_scope"]}, "corroboration": {"type": "string", "enum": ["corroborated", "single_source", "conflicting"]}, "disposition": {"type": "string", "enum": ["accept", "partial_accept", "reject", "needs_more_evidence"]}, "rationale": {"type": "string"}, "assessed_by": {"type": "string"}, "verified_by": {"type": "string"}, "conflicts": {"type": "array", "items": {"type": "string"}}}}},
    {"name": "confirm_runbook_revision", "description": "Confirm a validated official Runbook revision before completing Refresh publication.", "inputSchema": {"type": "object", "required": ["task_id", "revision_ref"], "properties": {"task_id": {"type": "string"}, "revision_ref": {"type": "string"}}}},
    {"name": "audit_knowledge", "description": "Run a read-only governance audit over Bundles, Evidence, links, freshness, and open Tasks.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "list_knowledge_inventory", "description": "List a derived knowledge inventory from Bundle Frontmatter.", "inputSchema": {"type": "object", "properties": {"domain": {"type": "string"}, "document_type": {"type": "string"}, "status": {"type": "string"}, "owner": {"type": "string"}, "freshness_state": {"type": "string", "enum": ["valid", "expired", "unknown"]}}}},
    {"name": "validate_claim_support", "description": "Validate claim-level Evidence support labels before using an Agent answer.", "inputSchema": {"type": "object", "required": ["claims"], "properties": {"claims": {"type": "array", "items": {"type": "object"}}}}},
    {"name": "measure_runbook_effectiveness", "description": "Derive Runbook outcome metrics by knowledge revision.", "inputSchema": {"type": "object", "required": ["workflow_id"], "properties": {"workflow_id": {"type": "string"}}}},
    {"name": "get_task", "description": "Read a runtime task without changing official knowledge.", "inputSchema": {"type": "object", "required": ["task_id"], "properties": {"task_id": {"type": "string"}}}},
    {"name": "update_task_inputs", "description": "Supply missing inputs to an existing runtime Task.", "inputSchema": {"type": "object", "required": ["task_id", "inputs"], "properties": {"task_id": {"type": "string"}, "inputs": {"type": "object"}}}},
    {"name": "record_task_step", "description": "Record ordered Workflow progress. For approval decisions, actor must be an authenticated human identity allowlisted by the Step approvers or Runbook owners; this local API validates the allowlist but does not authenticate the string.", "inputSchema": {"type": "object", "required": ["task_id", "step_id", "status", "result", "actor"], "properties": {"task_id": {"type": "string"}, "step_id": {"type": "string"}, "status": {"type": "string", "enum": ["completed", "failed", "needs_review", "approved", "rejected"]}, "result": {"type": "string"}, "actor": {"type": "string"}}}},
    {"name": "record_refresh_decision", "description": "Record an Evidence-backed update, no-change, or insufficient-evidence Refresh decision.", "inputSchema": {"type": "object", "required": ["task_id", "decision", "rationale", "evidence_ids", "actor"], "properties": {"task_id": {"type": "string"}, "decision": {"type": "string", "enum": ["update_required", "no_change", "insufficient_evidence"]}, "rationale": {"type": "string"}, "evidence_ids": {"type": "array", "minItems": 1, "items": {"type": "string"}}, "actor": {"type": "string"}}}},
    {"name": "record_outcome", "description": "Record a terminal task outcome as a pending Inbox item for human review, Evidence conversion, and curation.", "inputSchema": {"type": "object", "required": ["task_id", "status", "summary"], "properties": {"task_id": {"type": "string"}, "status": {"type": "string", "enum": ["completed", "failed", "needs_review"]}, "summary": {"type": "string"}, "feedback": {"type": "string"}, "learnings": {"type": "array", "items": {"type": "string"}}, "artifacts": {"type": "array", "items": {"type": "object"}}, "decisions": {"type": "array", "items": {"type": "object"}}, "action_items": {"type": "array", "items": {"type": "object"}}, "open_questions": {"type": "array", "items": {"type": "object"}}}}},
]

READ_ONLY_TOOLS = {
    "search_knowledge", "read_bundle", "prepare_context", "propose_update", "propose_pending", "inspect_inbox",
    "validate_result", "find_workflow", "list_knowledge_inventory",
    "validate_claim_support", "measure_runbook_effectiveness", "get_task",
}


def available_tools(access_mode: Optional[str] = None) -> list[Dict[str, Any]]:
    """Expose mutation tools only in an explicitly configured local operator process."""
    mode = access_mode or os.environ.get("KNOWLEDGE_MCP_MODE", "read_only")
    if mode not in {"read_only", "operator"}:
        mode = "read_only"
    return TOOLS if mode == "operator" else [tool for tool in TOOLS if tool["name"] in READ_ONLY_TOOLS]


def handle_request(
    request: Dict[str, Any], service: KnowledgeService, access_mode: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Handle one JSON-RPC message; notifications deliberately return no response."""
    method = request.get("method")
    request_id = request.get("id")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        result: Dict[str, Any] = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "campingtalk-knowledge", "version": "0.1.0"}}
    elif method == "tools/list":
        result = {"tools": available_tools(access_mode)}
    elif method == "tools/call":
        params = request.get("params", {})
        name, arguments = params.get("name"), params.get("arguments", {})
        try:
            allowed = {tool["name"] for tool in available_tools(access_mode)}
            if name not in allowed:
                raise ValueError(f"tool is not available in the current MCP access mode: {name}")
            if name == "search_knowledge": content = service.search_knowledge(arguments["query"], arguments.get("filters"))
            elif name == "read_bundle": content = service.read_bundle(arguments["bundle_id"])
            elif name == "prepare_context": content = service.prepare_context(arguments["task_description"], arguments.get("bundle_ids"))
            elif name == "propose_update": content = service.propose_update(arguments["evidence_id"])
            elif name == "propose_pending": content = service.propose_pending(arguments.get("limit", 100))
            elif name == "ingest_evidence": content = service.ingest_evidence(
                arguments["inbox_path"], arguments["provider"],
                why_collected=arguments["why_collected"],
                intended_use=arguments["intended_use"],
                title=arguments.get("title"), source_url=arguments.get("source_url"),
                source_locator=arguments.get("source_locator"),
                captured_from=arguments.get("captured_from", "manual"),
                reuse_value=arguments.get("reuse_value", "medium"),
                retention_class=arguments.get("retention_class", "general_reference"),
                sensitivity_review=arguments.get("sensitivity_review", "required"),
                idempotency_key=arguments.get("idempotency_key"),
                content_mode=arguments.get("content_mode", "external_file"),
            )
            elif name == "capture_conversation": content = service.capture_conversation(
                arguments["content"], arguments["provider"],
                title=arguments["title"], why_collected=arguments["why_collected"],
                intended_use=arguments["intended_use"],
                idempotency_key=arguments["idempotency_key"],
                thread_ref=arguments.get("thread_ref"),
                turn_from=arguments.get("turn_from"), turn_to=arguments.get("turn_to"),
                artifacts=arguments.get("artifacts"),
                sensitivity_review=arguments.get("sensitivity_review", "required"),
            )
            elif name == "capture_document": content = service.capture_document(
                arguments["content"], arguments["provider"],
                title=arguments["title"], why_collected=arguments["why_collected"],
                intended_use=arguments["intended_use"], idempotency_key=arguments["idempotency_key"],
                source_url=arguments.get("source_url"), source_locator=arguments.get("source_locator"),
                captured_from=arguments.get("captured_from", "sync"),
                sensitivity_review=arguments.get("sensitivity_review", "required"),
            )
            elif name == "capture_file": content = service.capture_file(
                base64.b64decode(arguments["payload_base64"], validate=True),
                arguments["original_filename"], arguments["provider"],
                title=arguments["title"], why_collected=arguments["why_collected"],
                intended_use=arguments["intended_use"], idempotency_key=arguments["idempotency_key"],
                source_url=arguments.get("source_url"), source_locator=arguments.get("source_locator"),
                captured_from=arguments.get("captured_from", "upload"),
                sensitivity_review=arguments.get("sensitivity_review", "required"),
            )
            elif name == "inspect_inbox": content = service.inspect_inbox(arguments.get("limit", 100))
            elif name == "review_inbox_sensitivity": content = service.review_inbox_sensitivity(
                arguments["intake_id"], arguments["actor"], arguments["decision"]
            )
            elif name == "accept_inbox": content = service.accept_inbox(arguments["intake_id"], arguments["actor"])
            elif name == "ingest_accepted": content = service.ingest_accepted(arguments.get("limit", 100))
            elif name == "create_draft_bundle": content = service.create_draft_bundle(
                domain=arguments["domain"], slug=arguments["slug"],
                title=arguments["title"], bundle_type=arguments["bundle_type"],
                summary=arguments["summary"], evidence_id=arguments["evidence_id"],
                body=arguments["body"], actor=arguments["actor"],
            )
            elif name == "apply_bundle_revision": content = service.apply_bundle_revision(
                arguments["bundle_id"], expected_revision=arguments["expected_revision"],
                frontmatter=arguments["frontmatter"], body=arguments["body"],
                actor=arguments["actor"],
            )
            elif name == "publish_changes": content = service.publish_changes(arguments["commit_message"])
            elif name == "validate_result": content = service.validate_result()
            elif name == "find_workflow": content = service.find_workflow(arguments["request"], arguments.get("limit", 5))
            elif name == "prepare_task": content = service.prepare_task(arguments["workflow_id"], arguments["request"], arguments.get("inputs"))
            elif name == "prepare_runbook_refresh": content = service.prepare_runbook_refresh(
                arguments["workflow_id"],
                arguments["request"],
                requested_by=arguments["requested_by"],
                reason=arguments.get("reason", "user_requested"),
            )
            elif name == "submit_runbook_reference": content = service.submit_runbook_reference(
                arguments["workflow_id"],
                arguments["evidence_id"],
                submitted_by=arguments["submitted_by"],
                note=arguments["note"],
            )
            elif name == "record_reference_assessment": content = service.record_reference_assessment(
                arguments["task_id"], evidence_id=arguments["evidence_id"],
                authority=arguments["authority"], recency=arguments["recency"],
                applicability=arguments["applicability"], corroboration=arguments["corroboration"],
                disposition=arguments["disposition"], rationale=arguments["rationale"],
                assessed_by=arguments["assessed_by"], verified_by=arguments["verified_by"],
                conflicts=arguments.get("conflicts"),
            )
            elif name == "confirm_runbook_revision": content = service.confirm_runbook_revision(
                arguments["task_id"], revision_ref=arguments["revision_ref"]
            )
            elif name == "audit_knowledge": content = service.audit_knowledge()
            elif name == "list_knowledge_inventory": content = service.list_knowledge_inventory(
                domain=arguments.get("domain"), document_type=arguments.get("document_type"),
                status=arguments.get("status"), owner=arguments.get("owner"),
                freshness_state=arguments.get("freshness_state"),
            )
            elif name == "validate_claim_support": content = service.validate_claim_support(arguments["claims"])
            elif name == "measure_runbook_effectiveness": content = service.measure_runbook_effectiveness(arguments["workflow_id"])
            elif name == "get_task": content = service.get_task(arguments["task_id"])
            elif name == "update_task_inputs": content = service.update_task_inputs(arguments["task_id"], arguments["inputs"])
            elif name == "record_task_step": content = service.record_task_step(
                arguments["task_id"],
                arguments["step_id"],
                status=arguments["status"],
                result=arguments["result"],
                actor=arguments["actor"],
            )
            elif name == "record_refresh_decision": content = service.record_refresh_decision(
                arguments["task_id"],
                decision=arguments["decision"],
                rationale=arguments["rationale"],
                evidence_ids=arguments["evidence_ids"],
                actor=arguments["actor"],
            )
            elif name == "record_outcome": content = service.record_outcome(
                arguments["task_id"],
                status=arguments["status"],
                summary=arguments["summary"],
                feedback=arguments.get("feedback", ""),
                learnings=arguments.get("learnings"),
                artifacts=arguments.get("artifacts"),
                decisions=arguments.get("decisions"),
                action_items=arguments.get("action_items"),
                open_questions=arguments.get("open_questions"),
            )
            else: raise ValueError(f"unknown tool: {name}")
            result = {"content": [{"type": "text", "text": json.dumps(content, ensure_ascii=False)}]}
        except (KeyError, OSError, PublishError, TypeError, ValueError) as error:
            result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": f"Method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def main() -> int:
    service = KnowledgeService(project_root() / "knowledge")
    for line in sys.stdin:
        try:
            response = handle_request(json.loads(line), service)
        except json.JSONDecodeError as error:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": str(error)}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
