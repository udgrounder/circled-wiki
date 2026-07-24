---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-7b899ed47c13435795103edd9e5c9881
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260722T003809Z-25642944
source_release: v1-dafe663754a3
source_git_revision: 17c7dee6911e95b6ab8a6cb6ddff870daaf301f0
moved_at: '2026-07-23T10:19:55.293012+00:00'
moved_by: codex
requested_by: user
canonical_issue_key: automatic-publication-push
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-24T09:45:21+00:00'
  decision: rejected
  note: >-
    Discarded as an obsolete unconditional-push request. The product supports a separately
    configured push path with remote and branch checks plus retry-safe receipts.
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
  archived_at: '2026-07-24T09:45:21+00:00'
  archived_by: codex
  reason: Obsolete unconditional automatic-push request discarded by user review.
  restore_condition: Reopen only with a new approved push-authorization requirement.
---
# publish-changes에 git push 추가 및 Standard Practice 규칙화

- Issue ID: `issue-20260722T003809Z-25642944`
- Recorded at: 2026-07-22T00:38:09.592299+00:00
- Reported by: user
- Reported from: user
- Area: workflow
- Severity: medium
- Status: open

## Summary

publisher.py의 publish_changes에 commit 후 git push를 추가하고, publication.md에 Standard Practice 섹션을 신설하여 작업 완료 후 commit+push를 필수 규칙으로 명시. dawn-curation.py의 publish 결과 표시도 push 상태를 포함하도록 개선.

## Expected result

모든 작업(자동 파이프라인 + 수동)이 완료 후 자동으로 commit 및 push되어 변경사항이 원격 저장소에 반영되어야 한다.

## Actual result

publish-changes가 commit까지만 수행하고 push는 하지 않아, 원격 저장소에 변경사항이 반영되지 않았다. publication.md에도 push에 대한 명시적 규칙이 없었다.

## Reproduction or context

dawn-curation 실행 → publish-changes → commit만 되고 push 누락

## Related paths or artifacts

- `src/knowledge_os/core/publisher.py`
- `.circled-wiki/agent-rules/publication.md`
- `.hermes/scripts/dawn-curation.py`

## Improvement hint

publisher.py: commit 후 git push 추가 (push 실패 시 오류 포함 반환). publication.md: Standard Practice 섹션 추가. dawn-curation.py: publish 결과에 push 상태 표시.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
