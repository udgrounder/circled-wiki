---
type: template
title: Business Rulebook Template
description: Policy·Guide·Runbook을 하나의 업무 기준으로 연결하는 템플릿
tags: [template, rulebook, guide]
timestamp: 2026-07-14T00:00:00+09:00
---

# Business Rulebook Template

Business Rulebook은 별도 Bundle type이 아니다. `type: guide`와 `extensions.rulebook`으로 Policy·Guide·Runbook을
연결하는 업무 진입점을 표현한다.

```yaml
---
type: guide
id: bundle/{organization_id}/{slug}_{bundle_uuid}.md
bundle_uuid: {bundle_uuid}
title: {업무명} Rulebook
status: draft
summary: {업무 적용 기준과 관련 절차의 진입점}
updated_at: {updated_at}
owners:
  - {owner}
tags: [bundles, guide, rulebook]
evidence:
  - evidence/{organization_id}/{name}_{source_uuid}.md
evidence_links:
  - "[{name}_{source_uuid}.md](evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.md)"
links: []
extensions:
  knowledge_revision: 1
  visibility: internal
  governance:
    reviewed_at:
    review_due_at:
    freshness_policy: on_change
  rulebook:
    rulebook_id: {rulebook_id}
    policies: []
    runbooks: []
    guides: []
---
```

## Scope

적용 업무, 대상, 제외 범위를 작성한다.

## Rules

필수·금지·승인 기준을 관련 Policy 링크와 함께 작성한다.

## Workflows

`knowledge/bundles/<domain>/runbooks/`의 실행 Runbook을 링크한다.

## Exceptions

예외 처리와 Reviewer Escalation 조건을 작성한다.
