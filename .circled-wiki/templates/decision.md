---
type: template
title: Decision Template
description: 설계 및 운영 판단 기록 템플릿
tags: [template, decision]
timestamp: 2026-07-09T00:00:00+09:00
---

# Decision Template

```yaml
---
type: decision
id: knowledge://{organization_id}/{domain}/{slug}_{bundle_uuid}
bundle_uuid: {bundle_uuid}
title: {title}
description: {description}
status: draft
summary: {summary}
updated_at: {updated_at}
owners:
  - {owner}
tags:
  - decision
evidence:
  - evidence://{organization_id}/{provider}/{yyyy}/{mm}/{dd}/{source_uuid}
links: []
extensions:
  source_uuids:
    - {source_uuid}
  decision_status: proposed
  review_state: pending
  knowledge_revision: 1
  visibility: internal
  pii_masked: false
  review_requested: false
---
```

## Context

결정이 필요한 배경을 작성한다.

## Decision

채택할 결정을 명확히 작성한다.

## Options Considered

검토한 대안을 작성한다.

## Consequences

결정으로 쉬워지는 점과 어려워지는 점을 작성한다.

## Follow-Up

후속 작업은 담당자와 완료 기준을 포함한다.

```yaml
action_items:
  - title: {후속 작업}
    owner: {담당자}
    due_at: {선택적 기한}
    completion_criteria: {완료 기준}
```

## Open Questions

결정 시점에 해결되지 않은 질문과 확인 Owner를 작성한다.
