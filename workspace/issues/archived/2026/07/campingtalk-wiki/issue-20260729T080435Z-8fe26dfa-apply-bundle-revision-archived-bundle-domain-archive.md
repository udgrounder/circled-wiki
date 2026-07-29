---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-1d560abd16dd4214a57aafd0bf60d961
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260729T080435Z-8fe26dfa
source_release: v1-498700edf231
source_git_revision: 2c61b43e90d1c89f46bec616c1bbdc6a828b2260
moved_at: '2026-07-29T08:24:47+00:00'
moved_by: codex
requested_by: kjkim
canonical_issue_key: archived-bundle-domain-tags
occurrence: 1
review:
  reviewed_by: kjkim
  reviewed_at: '2026-07-29T08:28:31.444938+00:00'
  decision: accepted
  note: '사용자 승인: archived Bundle revision의 실제 domain 태그 보정.'
processing:
  classification: product_defect
  disposition: resolved
  history_relation: new
  similar_history: []
  linked_work:
  - repository.apply_bundle_revision archived domain regression test
  linked_release: null
  linked_deployment_receipt: null
  linked_verification_receipt: null
  current_release_verification: null
  source_commit_verification: null
  worktree_verification:
    revision: ef41c92ce6d536bc5c62c7a1ffd7d2dc22df9586
    diff_checksum: sha256:a69849500656eceb6362be90e5f6e97b057c7eb5a1a37b6aa462770ffcf0703a
    verified_by: codex
    evidence: 226 pytest passed; repository validator validated=19 invalid=0; archived
      Bundle revision regression test passed.
    verified_at: '2026-07-29T08:30:34.358949+00:00'
archive:
  archived_at: '2026-07-29T08:30:34.491991+00:00'
  archived_by: codex
  reason: Archived Bundle revisions now derive the original domain instead of .archive.
  restore_condition: Reopen if an archived Bundle revision adds .archive to its tags.
---
# apply_bundle_revision이 archived Bundle의 domain을 '.archive'로 잘못 계산함

- Issue ID: `issue-20260729T080435Z-8fe26dfa`
- Recorded at: 2026-07-29T08:04:35.767183+00:00
- Reported by: claude-code
- Reported from: agent
- Area: cli
- Severity: medium
- Release observed: v1-498700edf231
- Status: open

## Summary

apply_bundle_revision은 domain을 relative.parts[0]으로 계산하는데, archived Bundle 경로는 knowledge/bundles/.archive/<domain>/<slug>.md 형태라 parts[0]이 '.archive'가 된다. 그 결과 _normalized_bundle_tags가 항상 domain 값을 구조 태그로 주입하면서 '.archive'가 Bundle tags에 그대로 섞여 들어간다.

## Expected result

archived Bundle에 apply-bundle-revision을 적용해도 domain은 실제 도메인(예: marketing)으로 계산되어야 하고, tags에 '.archive' 같은 경로 구조 값이 섞이지 않아야 함

## Actual result

knowledge/bundles/.archive/marketing/ai-promotional-image-sns-case-study-refinement.md에 revision을 적용하니 tags에 '.archive'가 추가됨(수동으로 제거함)

## Impact

archived Bundle을 revision할 때마다 tags에 '.archive'가 재삽입될 수 있음(현재는 수동으로 제거해 회피)

## Reproduction or context

archived 상태인 Bundle에 apply-bundle-revision을 실행하고 결과 tags 확인. repository.py의 apply_bundle_revision에서 'relative = existing.path.relative_to(knowledge_root / "bundles"); ... domain=relative.parts[0]' 부분이 원인

## Related paths or artifacts

- None recorded.

## Improvement hint

domain 계산 시 parts[0]이 '.archive'면 parts[1]을 실제 domain으로 사용하도록 수정

## Cause hypothesis

Not recorded.

## Review outcome

Pending system-maintainer review. This record is not an approval to change the OS.
