"""Executable Runbook discovery, task preparation, and outcome feedback."""

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from circled_wiki.config.settings import load_settings

from .frontmatter import parse_markdown
from .ingest import capture_document
from .evidence import evidence_original_bytes
from .repository import find_document_by_id, iter_documents
from .validator import verify_evidence_original


TERMINAL_OUTCOMES = {"completed", "failed", "needs_review"}
ARTIFACT_AVAILABILITY = {
    "available", "metadata_only", "temporarily_unavailable", "access_denied", "missing"
}
STEP_OUTCOMES = {"completed", "failed", "needs_review", "approved", "rejected"}
REFRESH_REASONS = {
    "expired", "user_requested", "user_reference", "owner_requested", "source_change", "outcome_signal",
    "security_or_compliance",
}
REFRESH_DECISIONS = {"update_required", "no_change", "insufficient_evidence"}
REFERENCE_AUTHORITY = {"primary", "official_secondary", "internal_experience", "informal"}
REFERENCE_RECENCY = {"newer", "same_period", "older", "unknown"}
REFERENCE_APPLICABILITY = {"full", "partial", "out_of_scope"}
REFERENCE_CORROBORATION = {"corroborated", "single_source", "conflicting"}
REFERENCE_DISPOSITIONS = {"accept", "partial_accept", "reject", "needs_more_evidence"}
EVIDENCE_ID = re.compile(
    r"^evidence/[a-z0-9][a-z0-9_-]*/[^/]+_[0-9a-fA-F-]{36}\.md$"
)
REFRESH_STEPS = [
    {"id": "collect-current-evidence", "title": "최신 Evidence 수집", "kind": "action"},
    {"id": "validate-current-evidence", "title": "Evidence 최신성·접근성·출처 검증", "kind": "validation"},
    {"id": "compare-runbook", "title": "기존 Runbook 변경점 비교", "kind": "validation"},
    {"id": "prepare-refresh-proposal", "title": "변경·무변경·근거부족 판정", "kind": "decision"},
    {"id": "independent-agent-review", "title": "다른 Agent의 독립 검증", "kind": "validation"},
    {"id": "validate-proposal", "title": "OKF·Profile·보안 검증", "kind": "validation"},
    {"id": "owner-approval", "title": "Runbook Owner 승인", "kind": "approval"},
    {"id": "publish-revision", "title": "새 revision 발행", "kind": "action"},
]


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[0-9a-zA-Z가-힣_-]+", value.casefold()))


def _workflow_metadata(frontmatter: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    extensions = frontmatter.get("extensions")
    if not isinstance(extensions, dict):
        return None
    workflow = extensions.get("workflow")
    return workflow if isinstance(workflow, dict) else None


def _freshness(frontmatter: Dict[str, Any]) -> Dict[str, Any]:
    extensions = frontmatter.get("extensions")
    governance = extensions.get("governance") if isinstance(extensions, dict) else None
    review_due_at = governance.get("review_due_at") if isinstance(governance, dict) else None
    if isinstance(review_due_at, datetime):
        due = review_due_at
    elif isinstance(review_due_at, str) and review_due_at.strip():
        try:
            due = datetime.fromisoformat(review_due_at.replace("Z", "+00:00"))
        except ValueError:
            return {"state": "unknown", "review_due_at": review_due_at}
    else:
        return {"state": "unknown", "review_due_at": review_due_at}
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    remaining_seconds = (due - now).total_seconds()
    validity_days = governance.get("validity_days") if isinstance(governance, dict) else None
    if remaining_seconds <= 0:
        state = "expired"
    elif isinstance(validity_days, int) and remaining_seconds <= validity_days * 86400 * 0.2:
        state = "due_soon"
    else:
        state = "valid"
    return {
        "state": state,
        "review_due_at": due.isoformat(timespec="seconds"),
        "remaining_days": max(0, int(remaining_seconds // 86400)),
    }


def iter_workflows(knowledge_root: Path) -> Iterable[Dict[str, Any]]:
    """Yield active executable Runbook definitions from the knowledge repository."""
    for path in iter_documents(knowledge_root):
        if path.name in {"index.md", "log.md"} or "bundles" not in path.parts:
            continue
        document = parse_markdown(path)
        data = document.frontmatter
        workflow = _workflow_metadata(data)
        extensions = data.get("extensions", {})
        if data.get("type") != "runbook" or data.get("status") != "active" or workflow is None:
            continue
        if isinstance(extensions, dict) and extensions.get("visibility") == "restricted":
            continue
        freshness = _freshness(data)
        yield {
            "id": str(data.get("id", "")),
            "title": str(data.get("title", "")),
            "summary": str(data.get("summary", "")),
            "tags": list(data.get("tags", []) or []),
            "links": list(data.get("links", []) or []),
            "owners": list(data.get("owners", []) or []),
            "knowledge_revision": data.get("extensions", {}).get("knowledge_revision", 1),
            "governance": data.get("extensions", {}).get("governance", {}),
            "stale": freshness["state"] == "expired",
            "freshness": freshness,
            "workflow": workflow,
            "path": path,
        }


def find_workflows(knowledge_root: Path, request: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Rank executable Runbooks for a user request using deterministic text matching."""
    if not request.strip():
        raise ValueError("request must be a non-empty string")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    request_tokens = _tokens(request)
    request_text = request.casefold().strip()
    matches = []
    for candidate in iter_workflows(knowledge_root):
        workflow = candidate["workflow"]
        searchable = " ".join(
            [
                candidate["title"],
                candidate["summary"],
                " ".join(map(str, candidate["tags"])),
                " ".join(map(str, workflow.get("trigger_intents", []))),
                " ".join(map(str, workflow.get("applies_to", []))),
            ]
        ).casefold()
        overlap = len(request_tokens.intersection(_tokens(searchable)))
        phrase_bonus = 3 if request_text and request_text in searchable else 0
        score = overlap + phrase_bonus
        if score == 0:
            continue
        matches.append(
            {
                "id": candidate["id"],
                "workflow_id": workflow.get("workflow_id"),
                "title": candidate["title"],
                "summary": candidate["summary"],
                "execution_mode": workflow.get("execution_mode"),
                "owners": candidate["owners"],
                "stale": candidate["stale"],
                "freshness": candidate["freshness"],
                "score": score,
                "path": candidate["path"].relative_to(knowledge_root.parent).as_posix(),
            }
        )
    return sorted(matches, key=lambda item: (-item["score"], item["title"]))[:limit]


def get_workflow(knowledge_root: Path, identifier: str) -> Dict[str, Any]:
    """Resolve an executable Runbook by Bundle id or stable workflow_id."""
    for candidate in iter_workflows(knowledge_root):
        if candidate["id"] == identifier or candidate["workflow"].get("workflow_id") == identifier:
            return candidate
    raise ValueError("workflow must refer to an active executable Runbook")


def evaluate_runbook_learning(knowledge_root: Path, identifier: str) -> Dict[str, Any]:
    """Derive learning signals from immutable Outcome Evidence since the last review."""
    workflow = get_workflow(knowledge_root, identifier)
    policy = workflow["workflow"].get("learning", {})
    reviewed_value = workflow.get("governance", {}).get("reviewed_at")
    if isinstance(reviewed_value, datetime):
        reviewed_at = reviewed_value
    elif isinstance(reviewed_value, str):
        try:
            reviewed_at = datetime.fromisoformat(reviewed_value.replace("Z", "+00:00"))
        except ValueError:
            reviewed_at = datetime.min.replace(tzinfo=timezone.utc)
    else:
        reviewed_at = datetime.min.replace(tzinfo=timezone.utc)
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)

    outcomes: List[Dict[str, Any]] = []
    operator_agent = load_settings(knowledge_root.parent).operator_agent
    for path in sorted((knowledge_root / "evidence" / operator_agent).rglob("*.md")):
        try:
            evidence = parse_markdown(path)
            payload_bytes = evidence_original_bytes(evidence)
            if payload_bytes is None:
                continue
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            continue
        if (
            payload.get("type") != "workflow-outcome"
            or payload.get("task_type", "workflow_execution") != "workflow_execution"
            or payload.get("workflow_bundle_id") != workflow["id"]
        ):
            continue
        recorded_value = payload.get("recorded_at")
        try:
            recorded_at = datetime.fromisoformat(str(recorded_value).replace("Z", "+00:00"))
        except ValueError:
            continue
        if recorded_at.tzinfo is None:
            recorded_at = recorded_at.replace(tzinfo=timezone.utc)
        if recorded_at > reviewed_at:
            outcomes.append(payload)

    failure_count = sum(1 for item in outcomes if item.get("status") == "failed")
    feedback_count = sum(1 for item in outcomes if str(item.get("feedback", "")).strip())
    triggers: List[str] = []
    threshold = policy.get("min_outcomes_for_review", 3)
    if isinstance(threshold, int) and len(outcomes) >= threshold:
        triggers.append("outcome_threshold")
    if policy.get("review_on_failure") is True and failure_count:
        triggers.append("failure")
    if policy.get("review_on_feedback") is True and feedback_count:
        triggers.append("user_feedback")
    return {
        "workflow_id": workflow["workflow"]["workflow_id"],
        "maturity": policy.get("maturity"),
        "outcomes_since_review": len(outcomes),
        "failure_count": failure_count,
        "feedback_count": feedback_count,
        "triggers": triggers,
        "improvement_review_required": bool(triggers),
    }


class TaskStore:
    """JSON task instances kept outside the Git-backed knowledge repository."""

    def __init__(self, runtime_root: Path):
        self.tasks_root = runtime_root / "tasks"

    def create(
        self, workflow: Dict[str, Any], request: str, inputs: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if not request.strip():
            raise ValueError("request must be a non-empty string")
        inputs = dict(inputs or {})
        required = workflow["workflow"].get("required_inputs", [])
        missing = [
            item["name"]
            for item in required
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and (inputs.get(item["name"]) is None or inputs.get(item["name"]) == "")
        ]
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task = {
            "task_id": str(uuid4()),
            "task_type": "workflow_execution",
            "workflow_id": workflow["workflow"]["workflow_id"],
            "workflow_bundle_id": workflow["id"],
            "workflow_version": workflow["workflow"]["version"],
            "knowledge_revision": workflow["knowledge_revision"],
            "request": request,
            "inputs": inputs,
            "required_inputs": required,
            "missing_inputs": missing,
            "steps": workflow["workflow"]["steps"],
            "step_states": [
                {
                    "id": step["id"],
                    "title": step["title"],
                    "kind": step["kind"],
                    "approvers": list(step.get("approvers", []))
                    if step["kind"] == "approval" else [],
                    "status": "pending",
                    "result": "",
                    "actor": "",
                    "updated_at": None,
                }
                for step in workflow["workflow"]["steps"]
            ],
            "approval_gates": workflow["workflow"].get("approval_gates", []),
            "completion_criteria": workflow["workflow"]["completion_criteria"],
            "applies_to": workflow["workflow"].get("applies_to", []),
            "excludes": workflow["workflow"].get("excludes", []),
            "examples": workflow["workflow"].get("examples", {}),
            "artifact_profile": workflow["workflow"].get("artifact_profile"),
            "learning": workflow["workflow"].get("learning", {}),
            "owners": workflow.get("owners", []),
            "governance": workflow.get("governance", {}),
            "freshness": workflow.get("freshness", {}),
            "learning": workflow["workflow"].get("learning", {}),
            "related_bundle_ids": [
                link for link in workflow.get("links", [])
                if isinstance(link, str) and link.startswith("bundle/")
            ],
            "status": "awaiting_input" if missing else "ready",
            "created_at": now,
            "updated_at": now,
            "outcome_evidence_id": None,
            "outcome_intake_id": None,
        }
        self._write(task)
        return task

    def create_refresh(
        self,
        workflow: Dict[str, Any],
        request: str,
        *,
        reason: str,
        requested_by: str,
        deferred_inputs: Optional[Dict[str, Any]] = None,
        candidate_evidence_ids: Optional[List[str]] = None,
        reference_note: str = "",
    ) -> Dict[str, Any]:
        if reason not in REFRESH_REASONS:
            raise ValueError("refresh reason is invalid")
        if not request.strip() or not requested_by.strip():
            raise ValueError("refresh request and requested_by must be non-empty strings")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        workflow_id = str(workflow["workflow"]["workflow_id"])
        candidate_ids = list(dict.fromkeys(candidate_evidence_ids or []))
        existing = self.find_open_refresh(workflow_id)
        if existing is not None:
            if candidate_ids:
                existing_ids = list(existing.get("candidate_evidence_ids", []))
                existing["candidate_evidence_ids"] = list(dict.fromkeys([*existing_ids, *candidate_ids]))
                submissions = list(existing.get("reference_submissions", []))
                for evidence_id in candidate_ids:
                    if not any(
                        item.get("evidence_id") == evidence_id and item.get("submitted_by") == requested_by
                        for item in submissions
                    ):
                        submissions.append({
                            "evidence_id": evidence_id,
                            "submitted_by": requested_by,
                            "note": reference_note or request,
                            "submitted_at": now,
                        })
                existing["reference_submissions"] = submissions
                inputs = dict(existing.get("inputs", {}))
                reasons = list(inputs.get("refresh_reasons", [inputs.get("refresh_reason")]))
                inputs["refresh_reasons"] = list(dict.fromkeys(
                    item for item in [*reasons, reason] if isinstance(item, str) and item
                ))
                existing["inputs"] = inputs
                existing["updated_at"] = now
                self._write(existing)
            return dict(existing, reused=True)
        task = {
            "task_id": str(uuid4()),
            "task_type": "runbook_refresh",
            "workflow_id": f"runbook-refresh-{workflow_id}",
            "target_workflow_id": workflow_id,
            "workflow_bundle_id": workflow["id"],
            "workflow_version": workflow["workflow"]["version"],
            "knowledge_revision": workflow["knowledge_revision"],
            "request": request,
            "deferred_work": (
                {"request": request, "inputs": dict(deferred_inputs or {})}
                if reason == "expired" else None
            ),
            "inputs": {"refresh_reason": reason, "requested_by": requested_by},
            "candidate_evidence_ids": candidate_ids,
            "reference_submissions": [
                {
                    "evidence_id": evidence_id,
                    "submitted_by": requested_by,
                    "note": reference_note or request,
                    "submitted_at": now,
                }
                for evidence_id in candidate_ids
            ],
            "reference_assessments": [],
            "required_inputs": [],
            "missing_inputs": [],
            "steps": REFRESH_STEPS,
            "step_states": [
                {
                    "id": step["id"],
                    "title": step["title"],
                    "kind": step["kind"],
                    "status": "pending",
                    "result": "",
                    "actor": "",
                    "updated_at": None,
                }
                for step in REFRESH_STEPS
            ],
            "approval_gates": ["owner-approval"],
            "completion_criteria": [
                "최신 Evidence의 최신성·접근성·출처를 검증한다.",
                "기존 Runbook과의 차이를 update_required, no_change, insufficient_evidence로 판정한다.",
                "제안 작성자와 다른 Agent가 근거·누락·충돌을 검증한다.",
                "OKF·Profile·보안 검증을 통과한다.",
                "Runbook Owner가 새 revision 또는 변경 없음을 승인한다.",
                "reviewed_at과 review_due_at을 갱신한 revision을 발행한다.",
            ],
            "related_bundle_ids": [
                link for link in workflow.get("links", [])
                if isinstance(link, str) and link.startswith("bundle/")
            ],
            "owners": workflow.get("owners", []),
            "governance": workflow.get("governance", {}),
            "freshness": workflow.get("freshness", {}),
            "status": "ready",
            "created_at": now,
            "updated_at": now,
            "outcome_evidence_id": None,
            "outcome_intake_id": None,
            "reused": False,
        }
        self._write(task)
        return task

    def find_open_refresh(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        if not self.tasks_root.is_dir():
            return None
        for path in sorted(self.tasks_root.glob("*.json")):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if (
                task.get("task_type") == "runbook_refresh"
                and task.get("target_workflow_id") == workflow_id
                and task.get("status") not in {"completed", "failed", "needs_review"}
                and not task.get("outcome_evidence_id")
                and not task.get("outcome_intake_id")
            ):
                return task
        return None

    def read(self, task_id: str) -> Dict[str, Any]:
        self._validate_id(task_id)
        path = self.tasks_root / f"{task_id}.json"
        if not path.is_file():
            raise ValueError("task was not found")
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, task: Dict[str, Any]) -> Dict[str, Any]:
        task["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._write(task)
        return task

    def add_inputs(self, task_id: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
        task = self.read(task_id)
        if task.get("outcome_evidence_id") or task.get("outcome_intake_id"):
            raise ValueError("completed task inputs cannot be changed")
        task["inputs"].update(dict(inputs))
        task["missing_inputs"] = [
            item["name"]
            for item in task.get("required_inputs", [])
            if task["inputs"].get(item["name"]) is None
            or task["inputs"].get(item["name"]) == ""
        ]
        if task["missing_inputs"]:
            task["status"] = "awaiting_input"
        elif all(step.get("status") == "pending" for step in task.get("step_states", [])):
            task["status"] = "ready"
        return self.update(task)

    def record_step(
        self, task_id: str, step_id: str, status: str, result: str, actor: str
    ) -> Dict[str, Any]:
        if status not in STEP_OUTCOMES:
            raise ValueError("step status is invalid")
        if not result.strip() or not actor.strip():
            raise ValueError("step result and actor must be non-empty strings")
        task = self.read(task_id)
        if task.get("outcome_evidence_id") or task.get("outcome_intake_id"):
            raise ValueError("completed task steps cannot be changed")
        if task.get("missing_inputs"):
            raise ValueError("required inputs must be supplied before recording steps")
        if task.get("task_type") == "runbook_refresh" and step_id == "prepare-refresh-proposal":
            raise ValueError("use record_refresh_decision for the Refresh proposal step")
        states = task.get("step_states", [])
        index = next((i for i, step in enumerate(states) if step.get("id") == step_id), None)
        if index is None:
            raise ValueError("workflow step was not found")
        state = states[index]
        if state["kind"] == "approval" and status not in {"approved", "rejected", "needs_review"}:
            raise ValueError("approval step must be approved, rejected, or needs_review")
        if state["kind"] != "approval" and status in {"approved", "rejected"}:
            raise ValueError("only an approval step can be approved or rejected")
        incomplete_prior = [
            step for step in states[:index] if step.get("status") not in {"completed", "approved"}
        ]
        if incomplete_prior:
            raise ValueError("workflow steps must be recorded in order")
        if state["kind"] == "approval" and status == "approved":
            prior_actors = {
                str(step.get("actor", "")).strip()
                for step in states[:index]
                if str(step.get("actor", "")).strip()
            }
            if actor.strip() in prior_actors:
                raise ValueError(
                    "approval actor must differ from actors that performed prior workflow steps"
                )
        if state["kind"] == "approval" and status in {"approved", "rejected"}:
            configured = state.get("approvers", [])
            allowed_approvers = configured if isinstance(configured, list) and configured else task.get("owners", [])
            allowed_approvers = [
                str(value).strip() for value in allowed_approvers
                if isinstance(value, str) and value.strip()
            ]
            if not allowed_approvers:
                raise ValueError("approval step has no configured authorized approver")
            if actor.strip() not in allowed_approvers:
                raise ValueError("approval actor is not authorized for this workflow step")
        if task.get("task_type") == "runbook_refresh" and step_id == "independent-agent-review":
            decision = task.get("refresh_decision", {})
            if not isinstance(decision, dict) or decision.get("decision") not in {
                "update_required", "no_change"
            }:
                raise ValueError("a reviewable Refresh decision is required before independent review")
            if actor == decision.get("actor"):
                raise ValueError("independent review actor must differ from the proposal actor")
        if task.get("task_type") == "runbook_refresh" and step_id == "owner-approval":
            owners = task.get("owners", [])
            if owners and actor not in owners:
                raise ValueError("Refresh approval actor must be a Runbook owner")
        if task.get("task_type") == "runbook_refresh" and step_id == "publish-revision":
            if not isinstance(task.get("published_revision"), dict):
                raise ValueError("confirm the updated Runbook revision before publish-revision")
        state.update(
            {
                "status": status,
                "result": result,
                "actor": actor,
                "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )
        if status == "failed":
            task["status"] = "failed"
        elif status in {"needs_review", "rejected"}:
            task["status"] = "needs_review"
        elif all(step.get("status") in {"completed", "approved"} for step in states):
            task["status"] = "awaiting_outcome"
        else:
            task["status"] = "in_progress"
        return self.update(task)

    def record_refresh_decision(
        self,
        task_id: str,
        *,
        decision: str,
        rationale: str,
        evidence_ids: List[str],
        actor: str,
    ) -> Dict[str, Any]:
        if decision not in REFRESH_DECISIONS:
            raise ValueError("Refresh decision is invalid")
        if not rationale.strip() or not actor.strip():
            raise ValueError("Refresh rationale and actor must be non-empty")
        if not isinstance(evidence_ids, list) or not evidence_ids or any(
            not EVIDENCE_ID.match(str(item)) for item in evidence_ids
        ):
            raise ValueError("Refresh decision requires canonical Evidence ID references")
        task = self.read(task_id)
        if task.get("task_type") != "runbook_refresh":
            raise ValueError("task must be a Runbook Refresh Task")
        if task.get("outcome_evidence_id") or task.get("outcome_intake_id"):
            raise ValueError("completed Refresh decision cannot be changed")
        candidate_ids = set(task.get("candidate_evidence_ids", []))
        if candidate_ids:
            assessments = {
                item.get("evidence_id"): item
                for item in task.get("reference_assessments", [])
                if isinstance(item, dict)
            }
            missing_assessments = sorted(candidate_ids.difference(assessments))
            if missing_assessments:
                raise ValueError("every candidate Evidence requires a Reference Assessment")
            if decision != "insufficient_evidence" and any(
                item.get("disposition") == "needs_more_evidence" for item in assessments.values()
            ):
                raise ValueError("needs_more_evidence assessment requires insufficient_evidence decision")
        states = task.get("step_states", [])
        index = next(
            (i for i, state in enumerate(states) if state.get("id") == "prepare-refresh-proposal"),
            None,
        )
        if index is None or any(
            state.get("status") not in {"completed", "approved"} for state in states[:index]
        ):
            raise ValueError("Evidence collection, validation, and comparison must complete first")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        task["refresh_decision"] = {
            "decision": decision,
            "rationale": rationale,
            "evidence_ids": list(evidence_ids),
            "actor": actor,
            "recorded_at": now,
            "assessment_evidence_ids": sorted(candidate_ids),
        }
        states[index].update(
            {
                "status": "needs_review" if decision == "insufficient_evidence" else "completed",
                "result": f"{decision}: {rationale}",
                "actor": actor,
                "updated_at": now,
            }
        )
        task["status"] = "needs_review" if decision == "insufficient_evidence" else "in_progress"
        return self.update(task)

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
    ) -> Dict[str, Any]:
        if authority not in REFERENCE_AUTHORITY:
            raise ValueError("reference authority is invalid")
        if recency not in REFERENCE_RECENCY:
            raise ValueError("reference recency is invalid")
        if applicability not in REFERENCE_APPLICABILITY:
            raise ValueError("reference applicability is invalid")
        if corroboration not in REFERENCE_CORROBORATION:
            raise ValueError("reference corroboration is invalid")
        if disposition not in REFERENCE_DISPOSITIONS:
            raise ValueError("reference disposition is invalid")
        if not rationale.strip() or not assessed_by.strip() or not verified_by.strip():
            raise ValueError("reference rationale and actors must be non-empty")
        if assessed_by == verified_by:
            raise ValueError("reference assessor and verifier must differ")
        if applicability == "out_of_scope" and disposition in {"accept", "partial_accept"}:
            raise ValueError("out-of-scope reference cannot be accepted")
        if corroboration == "conflicting" and disposition == "accept":
            raise ValueError("conflicting reference cannot be fully accepted")
        task = self.read(task_id)
        if task.get("task_type") != "runbook_refresh":
            raise ValueError("reference assessment requires a Runbook Refresh Task")
        if task.get("outcome_evidence_id") or task.get("outcome_intake_id") or task.get("status") in {"completed", "failed"}:
            raise ValueError("closed Refresh Task reference assessment cannot be changed")
        if evidence_id not in task.get("candidate_evidence_ids", []):
            raise ValueError("reference Evidence is not a candidate on this Refresh Task")
        if not isinstance(conflicts or [], list) or any(
            not isinstance(item, str) or not item.strip() for item in conflicts or []
        ):
            raise ValueError("reference conflicts must be a string array")
        assessment = {
            "evidence_id": evidence_id,
            "authority": authority,
            "recency": recency,
            "applicability": applicability,
            "corroboration": corroboration,
            "conflicts": list(conflicts or []),
            "disposition": disposition,
            "rationale": rationale,
            "assessed_by": assessed_by,
            "verified_by": verified_by,
            "assessed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        assessments = [
            item for item in task.get("reference_assessments", [])
            if item.get("evidence_id") != evidence_id
        ]
        assessments.append(assessment)
        task["reference_assessments"] = assessments
        return self.update(task)

    def confirm_revision(
        self,
        task_id: str,
        *,
        bundle_id: str,
        knowledge_revision: int,
        revision_ref: str,
    ) -> Dict[str, Any]:
        task = self.read(task_id)
        if task.get("task_type") != "runbook_refresh":
            raise ValueError("revision confirmation requires a Runbook Refresh Task")
        if task.get("workflow_bundle_id") != bundle_id:
            raise ValueError("confirmed revision must target the Refresh Runbook")
        if knowledge_revision <= int(task.get("knowledge_revision", 0)):
            raise ValueError("confirmed Runbook revision must increase knowledge_revision")
        if not revision_ref.strip():
            raise ValueError("revision_ref must be non-empty")
        task["published_revision"] = {
            "bundle_id": bundle_id,
            "knowledge_revision": knowledge_revision,
            "revision_ref": revision_ref,
            "confirmed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        return self.update(task)

    def _write(self, task: Dict[str, Any]) -> None:
        self._validate_id(str(task["task_id"]))
        self.tasks_root.mkdir(parents=True, exist_ok=True)
        path = self.tasks_root / f"{task['task_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    @staticmethod
    def _validate_id(task_id: str) -> None:
        try:
            UUID(task_id)
        except (ValueError, AttributeError) as error:
            raise ValueError("task_id must be a UUID") from error


def prepare_task(
    knowledge_root: Path,
    task_store: TaskStore,
    workflow_id: str,
    request: str,
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Snapshot an active Workflow into a runtime-only task instance."""
    workflow = get_workflow(knowledge_root, workflow_id)
    if workflow.get("stale"):
        return task_store.create_refresh(
            workflow,
            request,
            reason="expired",
            requested_by="system",
            deferred_inputs=inputs,
        )
    return task_store.create(workflow, request, inputs)


def prepare_runbook_refresh(
    knowledge_root: Path,
    task_store: TaskStore,
    workflow_id: str,
    request: str,
    *,
    requested_by: str,
    reason: str = "user_requested",
    candidate_evidence_ids: Optional[List[str]] = None,
    reference_note: str = "",
) -> Dict[str, Any]:
    """Create a Refresh Task even when the Runbook is still within its validity period."""
    workflow = get_workflow(knowledge_root, workflow_id)
    return task_store.create_refresh(
        workflow,
        request,
        reason=reason,
        requested_by=requested_by,
        candidate_evidence_ids=candidate_evidence_ids,
        reference_note=reference_note,
    )


def update_task_inputs(
    task_store: TaskStore, task_id: str, inputs: Dict[str, Any]
) -> Dict[str, Any]:
    """Supply missing Workflow inputs without creating a second Task."""
    return task_store.add_inputs(task_id, inputs)


def record_task_step(
    task_store: TaskStore,
    task_id: str,
    step_id: str,
    *,
    status: str,
    result: str,
    actor: str,
) -> Dict[str, Any]:
    """Persist ordered action, validation, and human approval progress."""
    return task_store.record_step(task_id, step_id, status, result, actor)


def record_refresh_decision(
    knowledge_root: Path,
    task_store: TaskStore,
    task_id: str,
    *,
    decision: str,
    rationale: str,
    evidence_ids: List[str],
    actor: str,
) -> Dict[str, Any]:
    """Record an Evidence-backed Refresh proposal without forcing a content change."""
    task = task_store.read(task_id)
    reviewed_value = task.get("governance", {}).get("reviewed_at")
    if isinstance(reviewed_value, datetime):
        reviewed_at = reviewed_value
    else:
        try:
            reviewed_at = datetime.fromisoformat(str(reviewed_value).replace("Z", "+00:00"))
        except ValueError:
            reviewed_at = datetime.min.replace(tzinfo=timezone.utc)
    if reviewed_at.tzinfo is None:
        reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
    has_new_snapshot = False
    for evidence_id in evidence_ids:
        evidence = find_document_by_id(knowledge_root, evidence_id)
        if evidence is None or evidence.frontmatter.get("type") != "evidence":
            raise ValueError("Refresh Evidence URI must resolve to an Evidence Record")
        extensions = evidence.frontmatter.get("extensions", {})
        if (
            decision != "insufficient_evidence"
            and (not isinstance(extensions, dict) or extensions.get("availability") != "available")
        ):
            raise ValueError("Refresh decisions require available Evidence originals")
        if decision != "insufficient_evidence":
            integrity_error = verify_evidence_original(evidence)
            if integrity_error:
                raise ValueError(f"Refresh Evidence integrity failed: {integrity_error}")
        captured_value = evidence.frontmatter.get("captured_at")
        if isinstance(captured_value, datetime):
            captured_at = captured_value
        else:
            try:
                captured_at = datetime.fromisoformat(str(captured_value).replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("Refresh Evidence captured_at is invalid") from error
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=timezone.utc)
        has_new_snapshot = has_new_snapshot or captured_at >= reviewed_at
    if decision != "insufficient_evidence" and not has_new_snapshot:
        raise ValueError("Refresh decision requires Evidence captured after the last review")
    return task_store.record_refresh_decision(
        task_id,
        decision=decision,
        rationale=rationale,
        evidence_ids=evidence_ids,
        actor=actor,
    )


def record_outcome(
    knowledge_root: Path,
    task_store: TaskStore,
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
) -> Dict[str, Any]:
    """Capture a task outcome in Inbox; approval and Evidence conversion are separate."""
    if status not in TERMINAL_OUTCOMES:
        raise ValueError("status must be completed, failed, or needs_review")
    if not summary.strip():
        raise ValueError("summary must be a non-empty string")
    artifact_items = list(artifacts or [])
    for artifact in artifact_items:
        if not isinstance(artifact, dict) or not str(artifact.get("name", "")).strip():
            raise ValueError("every artifact must have a non-empty name")
        availability = artifact.get("availability")
        if availability not in ARTIFACT_AVAILABILITY:
            raise ValueError("artifact availability is invalid")
        if availability in {"available", "metadata_only"} and not str(artifact.get("uri", "")).strip():
            raise ValueError("available artifact metadata must include a uri")
    decision_items = list(decisions or [])
    for item in decision_items:
        if not isinstance(item, dict) or not str(item.get("decision", "")).strip():
            raise ValueError("every decision must have a non-empty decision")
        if not str(item.get("decided_by", "")).strip() or not str(item.get("rationale", "")).strip():
            raise ValueError("every decision must include decided_by and rationale")
        evidence_ids = item.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            raise ValueError("every decision must include Evidence URI references")
        for evidence_id in evidence_ids:
            evidence = find_document_by_id(knowledge_root, str(evidence_id))
            if evidence is None or evidence.frontmatter.get("type") != "evidence":
                raise ValueError("decision Evidence must resolve to a manifest")
    action_item_values = list(action_items or [])
    for item in action_item_values:
        if not isinstance(item, dict) or any(
            not str(item.get(field, "")).strip()
            for field in ("title", "owner", "completion_criteria")
        ):
            raise ValueError("every action item must include title, owner, and completion_criteria")
        due_at = item.get("due_at")
        if due_at:
            try:
                datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("action item due_at must be ISO 8601") from error
    question_items = list(open_questions or [])
    for item in question_items:
        if not isinstance(item, dict) or not str(item.get("question", "")).strip() or not str(
            item.get("owner", "")
        ).strip():
            raise ValueError("every open question must include question and owner")
    task = task_store.read(task_id)
    if task.get("outcome_evidence_id") or task.get("outcome_intake_id"):
        return {
            "task_id": task_id,
            "task_type": task.get("task_type", "workflow_execution"),
            "target_workflow_id": task.get("target_workflow_id") or task.get("workflow_id"),
            "status": task["status"],
            "evidence_id": task.get("outcome_evidence_id"),
            "intake_id": task.get("outcome_intake_id"),
            "idempotent": True,
        }
    if status == "completed" and task.get("status") != "awaiting_outcome":
        raise ValueError("all workflow steps and approvals must complete before a completed outcome")
    artifact_profile = task.get("artifact_profile")
    if status == "completed" and isinstance(artifact_profile, dict):
        profile_name = artifact_profile.get("type")
        required_sections = set(artifact_profile.get("required_sections", []))
        matching = [item for item in artifact_items if item.get("profile") == profile_name]
        if not matching:
            raise ValueError("completed outcome requires an artifact matching the Runbook profile")
        if required_sections and not any(
            required_sections.issubset(set(item.get("sections", []))) for item in matching
        ):
            raise ValueError("artifact is missing required profile sections")

    payload = {
        "type": "workflow-outcome",
        "task_type": task.get("task_type", "workflow_execution"),
        "task_id": task_id,
        "workflow_id": task["workflow_id"],
        "workflow_bundle_id": task["workflow_bundle_id"],
        "workflow_version": task["workflow_version"],
        "knowledge_revision": task["knowledge_revision"],
        "target_workflow_id": task.get("target_workflow_id"),
        "refresh_reason": task.get("inputs", {}).get("refresh_reason"),
        "request": task["request"],
        "inputs": task["inputs"],
        "status": status,
        "summary": summary,
        "feedback": feedback,
        "learnings": list(learnings or []),
        "artifacts": artifact_items,
        "decisions": decision_items,
        "action_items": action_item_values,
        "open_questions": question_items,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    is_refresh = task.get("task_type") == "runbook_refresh"
    intended_workflow = str(task.get("target_workflow_id") or task["workflow_id"])
    operator_agent = load_settings(knowledge_root.parent).operator_agent
    capture = capture_document(
        knowledge_root,
        json.dumps(payload, ensure_ascii=False, indent=2),
        operator_agent,
        why_collected=(
            f"Runbook refresh outcome for {intended_workflow}"
            if is_refresh else f"Workflow outcome for {task['workflow_id']}"
        ),
        intended_use=[
            intended_workflow,
            "runbook-refresh" if is_refresh else "workflow-improvement",
        ],
        title=f"Workflow outcome: {task['workflow_id']}",
        source_locator=f"task_id={task_id}",
        captured_from="sync",
        sensitivity_review="required",
        idempotency_key=f"workflow-outcome:{task_id}",
        capture_details={"capture_type": "workflow_outcome", "task_id": task_id},
    )
    task["status"] = status
    task["outcome_intake_id"] = capture.intake_id
    task_store.update(task)
    return {
        "task_id": task_id,
        "task_type": task.get("task_type", "workflow_execution"),
        "target_workflow_id": task.get("target_workflow_id") or task.get("workflow_id"),
        "status": status,
        "intake_id": capture.intake_id,
        "inbox_path": capture.inbox_path.relative_to(knowledge_root.parent.resolve()).as_posix(),
        "workflow_bundle_id": task["workflow_bundle_id"],
        "next_action": "inspect_and_accept_outcome_inbox",
        "idempotent": False,
    }
