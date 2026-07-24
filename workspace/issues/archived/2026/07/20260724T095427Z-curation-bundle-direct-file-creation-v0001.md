---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-3ec16f7dd21b45dda5abf82830db6165
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260722T030134Z-8424fa0f
source_release: v1-dafe663754a3
source_git_revision: d1b36ce04ce9230f39ba9781056b644a3ce7aca4
moved_at: '2026-07-23T10:19:55.542944+00:00'
moved_by: codex
requested_by: user
canonical_issue_key: curation-bundle-direct-file-creation
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-24T09:54:27+00:00'
  decision: rejected
  note: >-
    Discarded because glob-based Evidence resolution, direct YAML Bundle creation, and shortened
    Bundle UUIDs bypass or violate the current repository and curation contracts.
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
  archived_at: '2026-07-24T09:54:27+00:00'
  archived_by: codex
  reason: Direct file-based curation implementation discarded by user review.
  restore_condition: Reopen only with a validated repository API regression.
---
# dawn-curation.py: Bundle 슬러그 생성 개선 및 read_evidence_meta 경로 탐색 수정

- Issue ID: `issue-20260722T030134Z-8424fa0f`
- Recorded at: 2026-07-22T03:01:34.925171+00:00
- Reported by: hermes
- Reported from: agent
- Area: workflow
- Severity: low
- Status: open

## Summary

dawn-curation.py의 Bundle 자동 생성 기능에서 세 가지 문제 수정: (1) read_evidence_meta()가 evidence_id를 파일 경로로 직접 변환하는 방식이 UUID prefix(original_stem) 때문에 파일을 찾지 못해 title이 None으로 반환되는 문제 → glob 검색으로 변경. (2) make_slug()가 title이 None일 때 UUID 기반 slug('evidence-xxxxxxxx')를 생성하여 Bundle 파일명이 비의미적이던 문제 → 정규식으로 특수문자/대괄호 제거 후 한글+영문 기반 slug 생성, 50자 제한. (3) Bundle UUID를 8자리 hex로 단축 (기존: 'a8a5736e-590c-4547-ab35-169f09db0a35' → 개선: '48742a4b'), create-bundle CLI의 "unhashable type: 'dict'" 버그 우회를 위해 CLI 호출 대신 직접 YAML 파일 생성 + evidence 연결 처리로 변경.

## Expected result

Bundle slug가 Evidence title에서 추출한 의미 있는 이름으로 생성되어야 함 (예: '2026-개발팀-작업-및-기술-채무', '피카푸-매출-활성화-tft')

## Actual result

read_evidence_meta가 파일을 찾지 못해 title=None → make_slug가 UUID 기반 fallback slug('evidence-f1b48023') 생성 → Bundle 파일명이 내용을 전혀 유추할 수 없는 상태

## Reproduction or context

Not recorded.

## Related paths or artifacts

- `.hermes/scripts/dawn-curation.py`

## Improvement hint

1. read_evidence_meta: evidence_id의 UUID로 glob 검색하여 prefix 무관하게 파일 찾기 (완료) 2. make_slug: 대괄호/특수문자 제거 → 공백 정규화 → 50자 제한 (완료) 3. 추후 개선: slug 중복 시 UUID suffix 추가 로직 필요

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
