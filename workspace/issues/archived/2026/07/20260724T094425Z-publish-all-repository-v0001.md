---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-4fba73a59117495f8a9c34839ad495c8
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260722T003352Z-fd9f69d4
source_release: v1-dafe663754a3
source_git_revision: ad2808612d8e28f4bb8a3412e0d64032d7676b0f
moved_at: '2026-07-23T10:19:55.211977+00:00'
moved_by: codex
requested_by: user
canonical_issue_key: publish-all-repository
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-24T09:44:25+00:00'
  decision: rejected
  note: >-
    Discarded as an obsolete operational request. The reported whole-repository publication
    change was already handled in the originating environment; the current product keeps the
    intentional knowledge-only automatic-publication boundary.
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
  archived_at: '2026-07-24T09:44:25+00:00'
  archived_by: codex
  reason: Obsolete whole-repository publication request discarded by user review.
  restore_condition: Reopen only with a new approved publication-boundary requirement.
---
# publish-changes commit 범위가 knowledge/로 제한된 문제 수정

- Issue ID: `issue-20260722T003352Z-fd9f69d4`
- Recorded at: 2026-07-22T00:33:52.131961+00:00
- Reported by: user
- Reported from: user
- Area: cli
- Severity: high
- Status: triaged

## Summary

dawn-curation의 publish-changes가 git add knowledge/만 수행하여 knowledge/ 외부 변경사항이 commit에서 누락됨. git add -A로 변경하여 전체 저장소가 commit되도록 수정함.

## Expected result

publish-changes 호출 시 knowledge/ 외부의 변경사항(.circled-wiki/issues, .hermes/scripts, src/ 등)도 함께 commit되어야 한다.

## Actual result

git add knowledge/만 실행되어 knowledge/ 디렉토리만 commit 대상이었고, 나머지 변경사항은 commit되지 않았다.

## Reproduction or context

dawn-curation.py의 publish-changes 단계 → publisher.py의 _git(project_root, 'add', 'knowledge') 호출

## Related paths or artifacts

- `src/knowledge_os/core/publisher.py`
- `.hermes/scripts/dawn-curation.py`

## Improvement hint

publisher.py의 git add knowledge/ → git add -A로 변경, knowledge/ 경계 검사 로직 제거, docstring 및 skip 메시지도 함께 수정

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.

## Status history

- 2026-07-22T00:37:28.387926+00:00: `open` -> `triaged` by `hermes` — 원인 파악 및 수정 완료. publisher.py: git add -A + git push 추가. publication.md Standard Practice 규칙화. dawn-curation.py push 상태 표시. (fix commit: d933c2b)
