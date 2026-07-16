---
type: template
title: Bundle Template
description: 정제된 공식 지식 Bundle 템플릿
tags: [template, bundle]
timestamp: 2026-07-09T00:00:00+09:00
---

# Bundle Template

```yaml
---
type: {policy|guide|runbook|decision|spec|reference}
id: knowledge://campingtalk/{domain}/{slug}_{bundle_uuid}
bundle_uuid: {bundle_uuid}
title: {title}
description: {description}
status: draft
summary: {summary}
updated_at: {updated_at}
owners:
  - {owner}
tags:
  - {tag}
evidence:
  - evidence://campingtalk/{provider}/{yyyy}/{mm}/{dd}/{source_uuid}
links: []
extensions:
  source_uuids:
    - {source_uuid}
  curated_by: hermes
  review_state: pending
  confidence: draft
  knowledge_revision: 1
  visibility: internal
  pii_masked: false
  review_requested: false
  governance:
    reviewed_at:
    review_due_at:
    freshness_policy: on_change
    supersedes: []
    superseded_by:
  archive:
    archived_at:
    archived_by:
    reason:
    restore_condition:
---
```

## Summary

핵심 내용을 3-5문장으로 정리한다.

## Details

정제된 지식 내용을 작성한다.

## Exceptions

예외, 주의사항, 적용 제외 조건을 작성한다.

## Evidence

근거 Evidence와 원본 참조를 설명한다.

## Related

관련 Bundle 링크를 작성한다.

`active`로 전환하기 전에 `owners`, `governance.reviewed_at`, `governance.review_due_at`을 채운다.
`status: archived`로 전환할 때만 `extensions.archive`를 채우며 파일 경로와 ID는 유지한다.
