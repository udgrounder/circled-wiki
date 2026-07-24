---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-e6b43c6a32924001a51b0f1e46338876
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260722T100925Z-7a91af0d
source_release: v1-dafe663754a3
source_git_revision: 85651af758dc0160ad04c7d2a07915f61d823de7
moved_at: '2026-07-23T10:19:55.639664+00:00'
moved_by: codex
requested_by: user
canonical_issue_key: upgrade-existing-knowledge-validator
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-24T09:56:17.095201+00:00'
  decision: accepted
  note: 사용자 요청으로 현 시점 기록을 폐기한다. 운영본 migration 및 검증 필요성이 재발하면 새 Issue로 수집한다.
processing:
  classification: installation_config
  disposition: rejected
  history_relation: new
  similar_history: []
  linked_work: []
  linked_release: null
  linked_deployment_receipt: null
  linked_verification_receipt: null
archive:
  archived_at: '2026-07-24T09:56:24.949200+00:00'
  archived_by: codex
  reason: 사용자 요청에 따른 현 시점 폐기
  restore_condition: 대상 운영 설치본의 migration 및 Validator 검증이 다시 필요한 경우 새 Issue로 수집
---
# 업그레이드 후 기존 지식 Validator 부적합

- Issue ID: `issue-20260722T100925Z-7a91af0d`
- Recorded at: 2026-07-22T10:09:25.729799+00:00
- Reported by: codex
- Reported from: agent
- Area: bootstrap
- Severity: high
- Status: open

## Summary

Circled Wiki Runtime 업그레이드 후 기존 지식 82건 중 50건이 새 검증 규칙을 통과하지 못했다. 업그레이드는 knowledge 내용을 수정하지 않았으며 전후 tree checksum은 동일하다.

## Expected result

업그레이드 후 기존 지식이 Validator를 통과하거나 호환성 마이그레이션 경로가 제공되어야 한다.

## Actual result

ID namespace 및 UUID 형식, PII scan receipt, Evidence 참조와 일부 checksum 검증 오류로 invalid=50이 발생했다.

## Reproduction or context

프로젝트 루트에서 python3 .circled-wiki/bin/knowledge-os.py validate 실행

## Related paths or artifacts

- `knowledge`

## Improvement hint

기존 지식을 자동 수정하지 말고 namespace 및 ID 마이그레이션, PII scan 재검토, 참조 무결성 복구를 별도 검토 작업으로 제공한다.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
