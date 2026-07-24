---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-4d7d75ca95e944b3817e87bb106f3c9c
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260721T092405Z-23629b38
source_release: v1-dafe663754a3
source_git_revision: 7ce60e60fce4f1e179618881c1d9512636b0b993
moved_at: '2026-07-23T10:19:55.048446+00:00'
moved_by: codex
requested_by: user
canonical_issue_key: runbook-frontmatter-language
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-24T09:17:17+00:00'
  decision: rejected
  note: >-
    Current Korean Frontmatter values are covered by Workflow and knowledge-search regression
    tests. required_inputs.description is not part of the search index, so translating it to
    English would not address the reported behavior.
processing:
  classification: null
  disposition: rejected
  history_relation: new
  similar_history: []
  linked_work: []
  linked_release: null
  linked_deployment_receipt: null
  linked_verification_receipt: null
archive:
  archived_at: '2026-07-24T09:17:17+00:00'
  archived_by: codex
  reason: Rejected after Korean Workflow and knowledge-search regression tests passed.
  restore_condition: Reopen with a reproducible Korean Frontmatter search failure.
---
# Runbook Frontmatter 필드 한글 사용 — 검색/운영 비효율

- Issue ID: `issue-20260721T092405Z-23629b38`
- Recorded at: 2026-07-21T09:24:05.557422+00:00
- Reported by: user
- Reported from: user
- Area: workflow
- Severity: low
- Status: open

## Summary

ai-promotional-image-production Runbook의 required_inputs 항목(name: output_format, orientation 등)의 description과 일부 메타데이터가 한글로 작성되어 있어, CLI 검색 및 자동화 운영에서 비효율 발생. 검색 키워드 불일치, 스크립트 처리 어려움, 국제화 제약 등 운영 편의성을 위해 frontmatter 필드는 영어로 통일 필요.

## Expected result

Runbook frontmatter의 모든 필드(name, description, tags, title 등)는 영어로 작성되어 검색/파싱/자동화 운영에 일관성을 제공해야 함.

## Actual result

required_inputs의 description, tags, summary 등에 한글이 혼용되어 있어 검색 및 CLI 처리 시 일관성 부족.

## Reproduction or context

1. knowledge/bundles/marketing/runbooks/ai-promotional-image-production_*.md 열기 2. frontmatter에서 한글 description 확인 (예: '출력 형태 (포스터/팜플렛/배너/카탈로그/인스타그램)') 3. search/find-workflow CLI에서 키워드 불일치 발생

## Related paths or artifacts

- `knowledge/bundles/marketing/runbooks/ai-promotional-image-production_5a26d6f2-821e-4a9e-a298-ad3db3b42b4c.md`

## Improvement hint

Runbook frontmatter 규약: title=영문(괄호 안에 한글 별칭 선택), description=영문, tags=영문, summary=영문. 본문 마크다운은 한글 자유. draft→active 전환 전 frontmatter 영어 리뷰 필수.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
