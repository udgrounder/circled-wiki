"""Transport-neutral boundary for scheduled external-source collection.

Provider adapters (for example, a future Notion client) fetch and normalize their
own source records, then hand only source content and provenance to this module.
No credential, HTTP, or schedule implementation belongs in the knowledge core.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Union

from knowledge_os.core.service import KnowledgeService


@dataclass(frozen=True)
class CollectedItem:
    """One source snapshot normalized by a provider-specific collector."""

    external_id: str
    revision: str
    title: str
    content: Union[str, bytes]
    source_url: str = ""
    source_locator: str = ""
    original_filename: Optional[str] = None
    intended_use: Optional[List[str]] = None
    sensitivity_review: str = "required"


def collect_items(
    service: KnowledgeService,
    provider: str,
    items: Iterable[CollectedItem],
    *,
    why_collected: str,
) -> Dict[str, object]:
    """Land changed source snapshots in provider-specific Inbox, idempotently.

    ``external_id`` and source revision form the stable replay key. Text snapshots
    use ``capture_document``; binary snapshots require their original basename and
    use ``capture_file``.  This function deliberately stops at ``pending`` Inbox.
    """
    if not isinstance(provider, str) or not provider.strip():
        raise ValueError("provider must be non-empty")
    if not isinstance(why_collected, str) or not why_collected.strip():
        raise ValueError("why_collected must be non-empty")
    receipts: List[Dict[str, object]] = []
    for item in items:
        if not isinstance(item, CollectedItem):
            raise ValueError("items must contain CollectedItem values")
        if not item.external_id.strip() or not item.revision.strip() or not item.title.strip():
            raise ValueError("external_id, revision, and title must be non-empty")
        intended_use = item.intended_use or ["external-source-review"]
        idempotency_key = f"{provider}:{item.external_id}:{item.revision}"
        if isinstance(item.content, str):
            receipt = service.capture_document(
                item.content,
                provider,
                title=item.title,
                why_collected=why_collected,
                intended_use=intended_use,
                idempotency_key=idempotency_key,
                source_url=item.source_url or None,
                source_locator=item.source_locator or f"external_id={item.external_id}",
                captured_from="sync",
                sensitivity_review=item.sensitivity_review,
                capture_details={
                    "capture_type": "scheduled_source", "external_id": item.external_id,
                    "revision": item.revision,
                },
            )
        elif isinstance(item.content, bytes):
            if not item.original_filename:
                raise ValueError("binary collected items require original_filename")
            receipt = service.capture_file(
                item.content,
                item.original_filename,
                provider,
                title=item.title,
                why_collected=why_collected,
                intended_use=intended_use,
                idempotency_key=idempotency_key,
                source_url=item.source_url or None,
                source_locator=item.source_locator or f"external_id={item.external_id}",
                captured_from="sync",
                sensitivity_review=item.sensitivity_review,
            )
        else:
            raise ValueError("collected content must be text or bytes")
        receipts.append(receipt)
    return {"provider": provider, "captured_count": len(receipts), "receipts": receipts}
