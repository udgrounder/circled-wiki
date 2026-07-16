"""Transport-neutral helpers for Slack-like conversational channels."""

from typing import Dict, List, Optional

from knowledge_os.core.service import KnowledgeService


def answer_knowledge_query(service: KnowledgeService, request: str, limit: int = 5) -> Dict[str, object]:
    """Return official knowledge summaries together with their preserved sources."""
    if not isinstance(request, str) or not request.strip():
        raise ValueError("request must be non-empty")
    answers: List[Dict[str, object]] = []
    for hit in service.search_knowledge(request)[:limit]:
        bundle = service.read_bundle(str(hit["id"]))
        if bundle is None:
            continue
        frontmatter = bundle["frontmatter"]
        answers.append({
            "bundle_id": bundle["id"],
            "title": hit["title"],
            "summary": hit["summary"],
            "status": frontmatter.get("status"),
            "support_status": frontmatter.get("extensions", {}).get("confidence", "needs_review"),
            "sources": bundle["sources"],
        })
    return {
        "mode": "knowledge_query",
        "request": request,
        "answers": answers,
        "response_guidance": (
            "근거가 없는 내용은 추정하지 말고, 각 답변의 sources와 support_status를 함께 제공한다."
        ),
    }


def prepare_channel_workflow(
    service: KnowledgeService,
    request: str,
    *,
    workflow_id: str,
    inputs: Optional[Dict[str, object]] = None,
) -> Dict[str, object]:
    """Prepare a Runbook task and formulate channel questions for missing inputs."""
    prepared = service.prepare_task(workflow_id, request, inputs)
    task = prepared["task"]
    definitions = {
        item.get("name"): item.get("description", item.get("name"))
        for item in task.get("required_inputs", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    questions = [
        {"input": name, "question": definitions.get(name, name)}
        for name in task.get("missing_inputs", [])
    ]
    return {
        "mode": prepared["mode"],
        "task_id": task["task_id"],
        "workflow_id": task["workflow_id"],
        "status": task["status"],
        "questions": questions,
        "context": prepared["context"],
    }
