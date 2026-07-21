---
type: template
title: Inquiry Template
description: 공식 지식으로 확정되지 않은 질문을 추적하는 템플릿
tags: [template, inquiry, reference]
timestamp: 2026-07-14T00:00:00+09:00
---

# Inquiry Template

```yaml
---
type: reference
id: knowledge://{organization_id}/{domain}/{slug}_{bundle_uuid}
bundle_uuid: {bundle_uuid}
title: {질문 제목}
status: draft
summary: {확인이 필요한 질문과 영향}
updated_at: {updated_at}
owners:
  - {owner}
evidence:
  - evidence://{organization_id}/{provider}/{yyyy}/{mm}/{dd}/{source_uuid}
extensions:
  knowledge_revision: 1
  visibility: internal
  governance:
    reviewed_at:
    review_due_at:
    freshness_policy: on_change
  inquiry:
    question_id: {question_id}
    status: open
    owner: {owner}
    related_rulebooks: []
    required_evidence: []
    due_at:
    resolution:
---
```

## Question

확인할 질문과 현재 알려진 범위를 작성한다.

## Impact

답이 없을 때 영향을 받는 업무와 Runbook을 작성한다.

## Resolution

해결 시 결론과 Evidence를 기록한다.
