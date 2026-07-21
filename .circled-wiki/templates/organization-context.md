---
type: template
title: Organization Context Template
description: Runtime Agent가 사용할 조직 목적·용어·판단 원칙 Bundle 템플릿
tags: [template, organization, context]
timestamp: 2026-07-14T00:00:00+09:00
---

# Organization Context Template

```yaml
---
type: guide
id: knowledge://{organization_id}/company/{slug}_{bundle_uuid}
bundle_uuid: {bundle_uuid}
title: {조직 맥락 제목}
status: draft
summary: {조직 목적과 판단 기준 요약}
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
    freshness_policy: quarterly
---
```

## Purpose

조직의 목적과 고객 가치를 작성한다.

## Priorities

업무와 의사결정 우선순위를 작성한다.

## Decision Principles

Agent와 사람이 공통으로 적용할 판단 원칙을 작성한다.

## Terminology

조직 내부 용어와 정의를 작성한다.

실제 조직 내용은 승인된 Evidence 없이 작성하거나 `active`로 발행하지 않는다.
