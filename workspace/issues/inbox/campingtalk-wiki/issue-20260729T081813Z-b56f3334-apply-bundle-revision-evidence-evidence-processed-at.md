---
type: workspace_issue
status: pending_review
workspace_issue_id: workspace-issue-ff55527e45b24bb1a01075c53c9daF84
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260729T081813Z-b56f3334
source_release: v1-498700edf231
source_git_revision: 2c61b43e90d1c89f46bec616c1bbdc6a828b2260
moved_at: '2026-07-29T08:24:47+00:00'
moved_by: codex
requested_by: kjkim
canonical_issue_key: null
occurrence: 1
review:
  reviewed_by: null
  reviewed_at: null
  decision: null
  note: null
processing:
  classification: null
  disposition: null
  history_relation: null
  similar_history: []
  linked_work: []
  linked_release: null
  linked_deployment_receipt: null
  linked_verification_receipt: null
  current_release_verification: null
  source_commit_verification: null
archive:
  archived_at: null
  archived_by: null
  reason: null
  restore_condition: null
---
# apply_bundle_revision이 Evidence 목록 변경 여부와 무관하게 참조 Evidence 전체를 매번 processed_at 갱신함

- Issue ID: `issue-20260729T081813Z-b56f3334`
- Recorded at: 2026-07-29T08:18:13.387548+00:00
- Reported by: claude-code
- Reported from: agent
- Area: cli
- Severity: low
- Release observed: v1-498700edf231
- Status: open

## Summary

apply_bundle_revision은 Bundle의 어떤 필드를 바꾸든(예: tags만 수정) 항상 evidence_ids에 있는 모든 Evidence의 status를 'processed'로, processed_at을 이번 revision 시각으로 무조건 다시 씀. Evidence 참조 목록 자체가 바뀌지 않은 revision(예: 태그만 수정)에서도 관련 Evidence 파일 전부가 diff에 찍혀 불필요한 변경 노이즈가 발생함.

## Expected result

Bundle revision에서 evidence 참조 목록이 실제로 바뀌지 않았다면, 기존에 이미 processed 상태인 Evidence의 processed_at을 불필요하게 갱신하지 않아야 함

## Actual result

Bundle 22건의 tags만 수정하는 apply-bundle-revision 호출에서, 관련 Evidence 90여 건의 processed_at이 모두 현재 시각으로 갱신되어 121개 파일이 diff에 잡힘(Evidence 원문·checksum은 변경되지 않음)

## Impact

실제 내용 변경이 없는 Evidence까지 Git diff·history에 반복적으로 나타나 변경 이력 추적과 리뷰가 불필요하게 번잡해짐

## Reproduction or context

이미 status: processed인 Evidence를 참조하는 Bundle에서, evidence 목록은 그대로 두고 tags 등 다른 필드만 바꿔 apply-bundle-revision을 호출하면 재현됨. repository.py의 apply_bundle_revision에서 'for evidence_id in selected_ids: ... evidence_data["processed_at"] = proposed["updated_at"]' 부분이 원인

## Related paths or artifacts

- None recorded.

## Improvement hint

evidence_ids가 기존 existing.frontmatter.get('evidence', [])와 동일하면(참조 목록에 변화가 없으면) 이미 processed 상태인 Evidence의 status/processed_at 갱신을 건너뛰도록 수정

## Cause hypothesis

Not recorded.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
