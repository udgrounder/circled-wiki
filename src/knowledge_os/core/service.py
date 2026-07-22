"""Structured application service shared by CLI, MCP, and future workers."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from .repository import apply_bundle_revision, create_bundle, find_document_by_id
from .curator import propose_update
from .ingest import (
    CaptureResult,
    accept_conversation_intake,
    capture_conversation,
    capture_document,
    capture_file,
    complete_inbox_sensitivity_review,
    ingest_evidence,
)
from .publisher import publish_changes
from .pii import record_pii_scan_receipt
from .search import search_knowledge
from .validator import validate_repository
from .governance import (
    audit_knowledge,
    list_knowledge_inventory,
    measure_runbook_effectiveness,
    validate_claim_support,
)
from .workflow import (
    TaskStore,
    evaluate_runbook_learning,
    find_workflows,
    prepare_runbook_refresh,
    prepare_task,
    record_outcome,
    record_refresh_decision,
    record_task_step,
    update_task_inputs,
)


class KnowledgeService:
    """The only Core facade that transport adapters should need."""

    def __init__(self, knowledge_root: Path):
        self.knowledge_root = knowledge_root
        self.task_store = TaskStore(knowledge_root.parent / ".runtime")

    def search_knowledge(self, query: str, filters: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
        results = []
        for hit in search_knowledge(self.knowledge_root, query, filters):
            document = find_document_by_id(self.knowledge_root, hit.document_id)
            if document is not None and _is_restricted(document.frontmatter):
                continue
            results.append({
                "id": hit.document_id,
                "title": hit.title,
                "type": hit.document_type,
                "summary": hit.summary,
                "path": hit.path.relative_to(self.knowledge_root.parent).as_posix(),
            })
        return results

    def read_bundle(self, bundle_id: str) -> Optional[Dict[str, object]]:
        document = find_document_by_id(self.knowledge_root, bundle_id)
        if document is None or "bundles" not in document.path.parts or _is_restricted(document.frontmatter):
            return None
        return {
            "id": document.frontmatter.get("id"),
            "frontmatter": document.frontmatter,
            "body": document.body,
            "path": document.path.relative_to(self.knowledge_root.parent).as_posix(),
            "sources": _sources_for_bundle(self.knowledge_root, document.frontmatter),
        }

    def prepare_context(self, task_description: str, bundle_ids: Optional[List[str]] = None, limit: int = 5) -> Dict[str, object]:
        """Return a compact, source-preserving context package for an Agent task."""
        documents = []
        if bundle_ids:
            for bundle_id in bundle_ids:
                document = self.read_bundle(bundle_id)
                if document is not None and document["frontmatter"].get("status") == "active":
                    documents.append(document)
        else:
            for hit in self.search_knowledge(task_description)[:limit]:
                document = self.read_bundle(str(hit["id"]))
                if document is not None and document["frontmatter"].get("status") == "active":
                    documents.append(document)
        return {
            "task_description": task_description,
            "bundles": documents,
            "claim_support_contract": {
                "statuses": ["verified", "limited", "inferred", "needs_review"],
                "required_fields": ["claim", "support_status", "evidence_ids", "limitations"],
                "verified_requires_available_evidence": True,
            },
            "warnings": [
                f"review requested: {document['id']}"
                for document in documents
                if bool(document["frontmatter"].get("extensions", {}).get("review_requested"))
            ],
        }

    def validate_result(self) -> Dict[str, object]:
        results = validate_repository(self.knowledge_root)
        return {"valid": all(result.is_valid for result in results), "results": [result.as_dict() for result in results]}

    def record_evidence_pii_scan(
        self, evidence_id: str, *, scanner: str, scanner_version: str,
        result: str, reviewed_by: str, receipt: str,
        scanned_at: Optional[str] = None,
    ) -> Dict[str, object]:
        """Record a supplied scan receipt without claiming to execute the scanner."""
        return record_pii_scan_receipt(
            self.knowledge_root, evidence_id, scanner=scanner,
            scanner_version=scanner_version, result=result,
            reviewed_by=reviewed_by, receipt=receipt, scanned_at=scanned_at,
        )

    def propose_update(self, evidence_id: str) -> Dict[str, object]:
        return propose_update(self.knowledge_root, evidence_id)

    def propose_pending(self, limit: int = 100) -> Dict[str, object]:
        from knowledge_os.worker.jobs import run_curation_batch

        return run_curation_batch(self.knowledge_root, limit=limit)

    def inspect_inbox(self, limit: int = 100) -> Dict[str, object]:
        from knowledge_os.worker.jobs import inspect_inbox

        return inspect_inbox(self.knowledge_root, limit=limit)

    def accept_inbox(self, intake_id: str, actor: str) -> Dict[str, object]:
        return accept_conversation_intake(self.knowledge_root, intake_id, actor)

    def review_inbox_sensitivity(
        self, intake_id: str, actor: str, decision: str
    ) -> Dict[str, object]:
        return complete_inbox_sensitivity_review(
            self.knowledge_root, intake_id, actor, decision
        )

    def ingest_accepted(self, limit: int = 100) -> Dict[str, object]:
        from knowledge_os.worker.jobs import ingest_accepted_inbox

        result = ingest_accepted_inbox(self.knowledge_root, limit=limit)
        for item in result["items"]:
            if not item.get("outcome_linked"):
                continue
            # The worker preserves the task linkage; resolve the workflow from its
            # task ID in the outcome intake metadata rather than from Evidence text.
            evidence = find_document_by_id(self.knowledge_root, str(item["evidence_id"]))
            source_ref = evidence.frontmatter.get("source_ref", {}) if evidence else {}
            locator = source_ref.get("locator", "") if isinstance(source_ref, dict) else ""
            task_id = str(locator).removeprefix("task_id=")
            try:
                task = self.task_store.read(task_id)
            except ValueError:
                continue
            if task.get("task_type") != "workflow_execution":
                continue
            workflow_id = str(task.get("target_workflow_id") or task["workflow_id"])
            learning_signal = evaluate_runbook_learning(self.knowledge_root, workflow_id)
            item["learning_signal"] = learning_signal
            if learning_signal["improvement_review_required"]:
                improvement_task = prepare_runbook_refresh(
                    self.knowledge_root, self.task_store, workflow_id,
                    "승인된 실행 Outcome 신호를 근거로 Runbook 개선 여부를 검토한다.",
                    requested_by="system", reason="outcome_signal",
                )
                item["improvement_task"] = {
                    "task_id": improvement_task["task_id"],
                    "reused": improvement_task.get("reused", False),
                    "triggers": learning_signal["triggers"],
                }
        return result

    def ingest_evidence(
        self,
        inbox_path: str,
        provider: str,
        *,
        why_collected: str,
        intended_use: List[str],
        title: Optional[str] = None,
        source_url: Optional[str] = None,
        source_locator: Optional[str] = None,
        captured_from: str = "manual",
        reuse_value: str = "medium",
        retention_class: str = "general_reference",
        sensitivity_review: str = "required",
        idempotency_key: Optional[str] = None,
        content_mode: str = "external_file",
    ) -> Dict[str, object]:
        """Ingest only an inbox-relative file for user, Batch, or Hermes collection."""
        if not isinstance(inbox_path, str) or not inbox_path.strip():
            raise ValueError("inbox_path must be non-empty")
        inbox_root = (self.knowledge_root / "inbox").resolve()
        source_path = (inbox_root / inbox_path).resolve()
        if inbox_root not in source_path.parents:
            raise ValueError("inbox_path must stay inside knowledge/inbox/")
        result = ingest_evidence(
            self.knowledge_root,
            source_path,
            provider,
            why_collected=why_collected,
            intended_use=intended_use,
            title=title,
            source_url=source_url,
            source_locator=source_locator,
            captured_from=captured_from,
            reuse_value=reuse_value,
            retention_class=retention_class,
            sensitivity_review=sensitivity_review,
            idempotency_key=idempotency_key,
            content_mode=content_mode,
            # A completed Inbox review is not an Evidence PII Scan receipt.
            pii_scanned=False,
        )
        response = {
            "evidence_id": result.evidence_id,
            "source_uuid": result.source_uuid,
            "original_path": result.original_path.relative_to(
                self.knowledge_root.parent.resolve()
            ).as_posix(),
            "manifest_path": result.manifest_path.relative_to(
                self.knowledge_root.parent.resolve()
            ).as_posix(),
            "reused": result.reused,
        }
        response["curation_proposal"] = propose_update(
            self.knowledge_root, result.evidence_id
        )
        return response

    def capture_conversation(
        self,
        content: str,
        provider: str,
        *,
        title: str,
        why_collected: str,
        intended_use: List[str],
        idempotency_key: str,
        thread_ref: Optional[str] = None,
        turn_from: Optional[int] = None,
        turn_to: Optional[int] = None,
        artifacts: Optional[List[Dict[str, object]]] = None,
        sensitivity_review: str = "required",
    ) -> Dict[str, object]:
        """Capture one conversation in Inbox without running downstream processing."""
        result = capture_conversation(
            self.knowledge_root,
            content,
            provider,
            title=title,
            why_collected=why_collected,
            intended_use=intended_use,
            idempotency_key=idempotency_key,
            thread_ref=thread_ref,
            turn_from=turn_from,
            turn_to=turn_to,
            artifacts=artifacts,
            sensitivity_review=sensitivity_review,
        )
        return _capture_result_payload(self.knowledge_root, result)

    def capture_document(
        self,
        content: str,
        provider: str,
        *,
        title: str,
        why_collected: str,
        intended_use: List[str],
        idempotency_key: str,
        source_url: Optional[str] = None,
        source_locator: Optional[str] = None,
        captured_from: str = "sync",
        sensitivity_review: str = "required",
        capture_details: Optional[Dict[str, object]] = None,
    ) -> Dict[str, object]:
        """Land an external source document in Inbox without processing it."""
        result = capture_document(
            self.knowledge_root,
            content,
            provider,
            title=title,
            why_collected=why_collected,
            intended_use=intended_use,
            idempotency_key=idempotency_key,
            source_url=source_url,
            source_locator=source_locator,
            captured_from=captured_from,
            sensitivity_review=sensitivity_review,
            capture_details=capture_details,
        )
        return _capture_result_payload(self.knowledge_root, result)

    def capture_file(
        self,
        payload: bytes,
        original_filename: str,
        provider: str,
        *,
        title: str,
        why_collected: str,
        intended_use: List[str],
        idempotency_key: str,
        source_url: Optional[str] = None,
        source_locator: Optional[str] = None,
        captured_from: str = "upload",
        sensitivity_review: str = "required",
    ) -> Dict[str, object]:
        """Land a binary or arbitrary source file in Inbox without processing it."""
        result = capture_file(
            self.knowledge_root, payload, original_filename, provider,
            title=title, why_collected=why_collected, intended_use=intended_use,
            idempotency_key=idempotency_key, source_url=source_url,
            source_locator=source_locator, captured_from=captured_from,
            sensitivity_review=sensitivity_review,
        )
        return _capture_result_payload(self.knowledge_root, result)

    def create_draft_bundle(
        self,
        *,
        domain: str,
        slug: str,
        title: str,
        bundle_type: str,
        summary: str,
        evidence_id: str,
        body: str,
        actor: str,
    ) -> Dict[str, object]:
        evidence = find_document_by_id(self.knowledge_root, evidence_id)
        if evidence is not None and _is_restricted(evidence.frontmatter):
            raise ValueError("restricted Evidence cannot be used through this interface")
        document = create_bundle(
            self.knowledge_root,
            domain=domain,
            slug=slug,
            title=title,
            bundle_type=bundle_type,
            summary=summary,
            evidence_id=evidence_id,
            body=body,
            curated_by=actor,
        )
        return self.read_bundle(str(document.frontmatter["id"])) or {}

    def apply_bundle_revision(
        self,
        bundle_id: str,
        *,
        expected_revision: int,
        frontmatter: Dict[str, Any],
        body: str,
        actor: str,
    ) -> Dict[str, object]:
        document = apply_bundle_revision(
            self.knowledge_root,
            bundle_id=bundle_id,
            expected_revision=expected_revision,
            proposed_frontmatter=frontmatter,
            body=body,
            actor=actor,
        )
        return self.read_bundle(str(document.frontmatter["id"])) or {}

    def find_workflow(self, request: str, limit: int = 5) -> List[Dict[str, object]]:
        return find_workflows(self.knowledge_root, request, limit)

    def prepare_task(
        self, workflow_id: str, request: str, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, object]:
        task = prepare_task(self.knowledge_root, self.task_store, workflow_id, request, inputs)
        context_ids = [str(task["workflow_bundle_id"]), *task.get("related_bundle_ids", [])]
        context = self.prepare_context(request, context_ids)
        mode = "refresh_required" if task.get("task_type") == "runbook_refresh" else "workflow_execution"
        return {"mode": mode, "task": task, "context": context}

    def prepare_runbook_refresh(
        self,
        workflow_id: str,
        request: str,
        *,
        requested_by: str,
        reason: str = "user_requested",
    ) -> Dict[str, object]:
        task = prepare_runbook_refresh(
            self.knowledge_root,
            self.task_store,
            workflow_id,
            request,
            requested_by=requested_by,
            reason=reason,
        )
        context_ids = [str(task["workflow_bundle_id"]), *task.get("related_bundle_ids", [])]
        return {
            "mode": "runbook_refresh",
            "task": task,
            "context": self.prepare_context(request, context_ids),
        }

    def submit_runbook_reference(
        self,
        workflow_id: str,
        evidence_id: str,
        *,
        submitted_by: str,
        note: str,
    ) -> Dict[str, object]:
        """Attach a user-supplied Evidence candidate to a deduplicated Refresh Task."""
        evidence = find_document_by_id(self.knowledge_root, evidence_id)
        if evidence is None or evidence.frontmatter.get("type") != "evidence":
            raise ValueError("reference must resolve to an Evidence Record")
        if _is_restricted(evidence.frontmatter):
            raise ValueError("restricted Evidence cannot be submitted through this interface")
        extensions = evidence.frontmatter.get("extensions", {})
        availability = extensions.get("availability") if isinstance(extensions, dict) else None
        capture_context = extensions.get("capture_context", {}) if isinstance(extensions, dict) else {}
        intended_use = capture_context.get("intended_use", []) if isinstance(capture_context, dict) else []
        context_alignment = "aligned" if workflow_id in intended_use else "needs_review"
        task = prepare_runbook_refresh(
            self.knowledge_root,
            self.task_store,
            workflow_id,
            note,
            requested_by=submitted_by,
            reason="user_reference",
            candidate_evidence_ids=[evidence_id],
            reference_note=note,
        )
        context_ids = [str(task["workflow_bundle_id"]), *task.get("related_bundle_ids", [])]
        return {
            "mode": "runbook_reference_review",
            "task": task,
            "reference": {
                "evidence_id": evidence_id,
                "availability": availability,
                "context_alignment": context_alignment,
                "warning": (
                    "Evidence intended_use에 대상 workflow_id가 없어 적용 범위를 검토해야 합니다."
                    if context_alignment == "needs_review" else None
                ),
            },
            "context": self.prepare_context(note, context_ids),
        }

    def record_reference_assessment(
        self,
        task_id: str,
        *,
        evidence_id: str,
        authority: str,
        recency: str,
        applicability: str,
        corroboration: str,
        disposition: str,
        rationale: str,
        assessed_by: str,
        verified_by: str,
        conflicts: Optional[List[str]] = None,
    ) -> Dict[str, object]:
        evidence = find_document_by_id(self.knowledge_root, evidence_id)
        if evidence is None or evidence.frontmatter.get("type") != "evidence":
            raise ValueError("reference assessment Evidence must resolve")
        return self.task_store.record_reference_assessment(
            task_id,
            evidence_id=evidence_id,
            authority=authority,
            recency=recency,
            applicability=applicability,
            corroboration=corroboration,
            disposition=disposition,
            rationale=rationale,
            assessed_by=assessed_by,
            verified_by=verified_by,
            conflicts=conflicts,
        )

    def confirm_runbook_revision(
        self, task_id: str, *, revision_ref: str
    ) -> Dict[str, object]:
        """Confirm that the official Runbook changed before closing a Refresh Task."""
        task = self.task_store.read(task_id)
        if task.get("task_type") != "runbook_refresh":
            raise ValueError("revision confirmation requires a Runbook Refresh Task")
        bundle_id = str(task.get("workflow_bundle_id", ""))
        document = find_document_by_id(self.knowledge_root, bundle_id)
        if document is None or document.frontmatter.get("type") != "runbook":
            raise ValueError("Refresh Runbook Bundle does not resolve")
        extensions = document.frontmatter.get("extensions", {})
        revision = extensions.get("knowledge_revision") if isinstance(extensions, dict) else None
        governance = extensions.get("governance", {}) if isinstance(extensions, dict) else {}
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise ValueError("Runbook knowledge_revision is invalid")
        if not isinstance(governance, dict) or not governance.get("reviewed_at") or not governance.get("review_due_at"):
            raise ValueError("Runbook governance review timestamps must be updated")
        results = validate_repository(self.knowledge_root)
        matching = [result for result in results if result.path == document.path]
        if not matching or not matching[0].is_valid:
            raise ValueError("updated Runbook must pass repository validation")
        return self.task_store.confirm_revision(
            task_id,
            bundle_id=bundle_id,
            knowledge_revision=revision,
            revision_ref=revision_ref,
        )

    def audit_knowledge(self) -> Dict[str, object]:
        return audit_knowledge(self.knowledge_root, self.task_store.tasks_root.parent)

    def list_knowledge_inventory(
        self,
        *,
        domain: Optional[str] = None,
        document_type: Optional[str] = None,
        status: Optional[str] = None,
        owner: Optional[str] = None,
        freshness_state: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        return list_knowledge_inventory(
            self.knowledge_root,
            self.task_store.tasks_root.parent,
            domain=domain,
            document_type=document_type,
            status=status,
            owner=owner,
            freshness_state=freshness_state,
        )

    def validate_claim_support(self, claims: List[Dict[str, Any]]) -> Dict[str, object]:
        return validate_claim_support(self.knowledge_root, claims)

    def measure_runbook_effectiveness(self, workflow_id: str) -> Dict[str, object]:
        return measure_runbook_effectiveness(self.knowledge_root, workflow_id)

    def get_task(self, task_id: str) -> Dict[str, object]:
        return self.task_store.read(task_id)

    def update_task_inputs(self, task_id: str, inputs: Dict[str, Any]) -> Dict[str, object]:
        return update_task_inputs(self.task_store, task_id, inputs)

    def record_task_step(
        self,
        task_id: str,
        step_id: str,
        *,
        status: str,
        result: str,
        actor: str,
    ) -> Dict[str, object]:
        return record_task_step(
            self.task_store,
            task_id,
            step_id,
            status=status,
            result=result,
            actor=actor,
        )

    def record_refresh_decision(
        self,
        task_id: str,
        *,
        decision: str,
        rationale: str,
        evidence_ids: List[str],
        actor: str,
    ) -> Dict[str, object]:
        return record_refresh_decision(
            self.knowledge_root,
            self.task_store,
            task_id,
            decision=decision,
            rationale=rationale,
            evidence_ids=evidence_ids,
            actor=actor,
        )

    def record_outcome(
        self,
        task_id: str,
        *,
        status: str,
        summary: str,
        feedback: str = "",
        learnings: Optional[List[str]] = None,
        artifacts: Optional[List[Dict[str, Any]]] = None,
        decisions: Optional[List[Dict[str, Any]]] = None,
        action_items: Optional[List[Dict[str, Any]]] = None,
        open_questions: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, object]:
        return record_outcome(
            self.knowledge_root,
            self.task_store,
            task_id,
            status=status,
            summary=summary,
            feedback=feedback,
            learnings=learnings,
            artifacts=artifacts,
            decisions=decisions,
            action_items=action_items,
            open_questions=open_questions,
        )

    def publish_changes(self, commit_message: str) -> Dict[str, object]:
        return publish_changes(self.knowledge_root.parent, commit_message)


def _is_restricted(frontmatter: Dict[str, object]) -> bool:
    return isinstance(frontmatter.get("extensions"), dict) and frontmatter["extensions"].get("visibility") == "restricted"


def _capture_result_payload(
    knowledge_root: Path, result: CaptureResult
) -> Dict[str, object]:
    """Serialize either a pending Inbox receipt or an already-ingested reuse."""
    project_root = knowledge_root.parent.resolve()
    if result.evidence_id and result.evidence_path:
        return {
            "intake_id": None,
            "inbox_path": None,
            "evidence_id": result.evidence_id,
            "evidence_path": result.evidence_path.relative_to(project_root).as_posix(),
            "status": "ingested",
            "checksum": result.checksum,
            "reused": True,
        }
    if not result.intake_id or not result.inbox_path:
        raise ValueError("capture result is missing its Inbox receipt")
    return {
        "intake_id": result.intake_id,
        "inbox_path": result.inbox_path.relative_to(project_root).as_posix(),
        "status": "pending",
        "checksum": result.checksum,
        "reused": result.reused,
    }


def _sources_for_bundle(knowledge_root: Path, bundle: Dict[str, object]) -> List[Dict[str, str]]:
    """Return the authoritative external source first, then the preserved local Evidence."""
    sources: List[Dict[str, str]] = []
    for evidence_id in bundle.get("evidence", []):
        evidence = find_document_by_id(knowledge_root, str(evidence_id))
        if evidence is None or _is_restricted(evidence.frontmatter):
            continue
        source_ref = evidence.frontmatter.get("source_ref", {})
        provider_url = source_ref.get("provider_url") if isinstance(source_ref, dict) else None
        locator = source_ref.get("locator") if isinstance(source_ref, dict) else None
        if isinstance(provider_url, str) and provider_url:
            sources.append({"kind": "original_source", "uri": provider_url, "locator": str(locator or ""), "evidence_id": str(evidence_id)})
        extensions = evidence.frontmatter.get("extensions", {})
        embedded = isinstance(extensions, dict) and extensions.get("content_mode") == "embedded"
        evidence_locator = "#original-conversation" if embedded else evidence.frontmatter.get("original_file", "")
        sources.append({"kind": "preserved_evidence", "uri": str(evidence_id), "locator": evidence_locator, "evidence_id": str(evidence_id)})
    return sorted(sources, key=lambda source: 0 if source["kind"] == "original_source" else 1)
