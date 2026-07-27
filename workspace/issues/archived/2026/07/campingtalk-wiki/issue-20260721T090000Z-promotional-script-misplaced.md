---
type: workspace_issue
status: archived
workspace_issue_id: workspace-issue-3914b4eb1cdd4c45a342c56c404bdbe4
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260721T090000Z-promotional-script-misplaced
source_release: v1-f2d9efab126c
source_git_revision: f5e26d4ed5cb04d0dd86d075f1ecff2e1699d42f
moved_at: '2026-07-27T11:16:35.213158+00:00'
moved_by: product-agent
requested_by: user
canonical_issue_key: issue-20260721t090000z-promotional-script-misplaced
occurrence: 1
review:
  reviewed_by: user
  reviewed_at: '2026-07-27T11:30:17.916193+00:00'
  decision: accepted
  note: User confirmed this legacy operational item is resolved.
processing:
  classification: operational_procedure
  disposition: resolved
  history_relation: new
  similar_history:
  - archive_ref: 2026/07/20260727T085929Z-issue-20260724t115949z-11f5d177-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests: []
  - archive_ref: 2026/07/20260727T091510Z-issue-20260721t092130z-c1efeac9-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests:
    - commit:76c0a768eb415ef59ffad48820ad40653a4c02aa
    - workspace/tests/integration/test_workflow.py
    - workspace/tests/unit/test_cli.py
  - archive_ref: 2026/07/20260727T091510Z-issue-20260721t092140z-8fcc31ae-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests:
    - agent-rules/knowledge-query.md
    - agent-rules/workflow-execution.md
    - .circled-wiki/AUTONOMOUS_AGENT_STARTUP.md
    - workspace/tests/unit/test_agent_rules.py
  - archive_ref: 2026/07/20260727T091510Z-issue-20260724t085356z-1729a4ec-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests:
    - workspace/receipts/releases/v1-204d0cebbab1.json
  - archive_ref: 2026/07/20260727T091918Z-issue-20260724t084616z-3e4439b9-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests:
    - '651749e: agent-rules/knowledge-curation.md'
  - archive_ref: 2026/07/20260727T091918Z-issue-20260724t122239z-4b684443-v0001.md
    similarity_reasons:
    - 'same area: agent_rules'
    previous_resolution: resolved
    previous_fixed_release: null
    previous_verification: null
    previous_regression_tests:
    - '651749e: src/circled_wiki/core/candidates.py'
  linked_work: []
  linked_release: null
  linked_deployment_receipt: null
  linked_verification_receipt: null
  current_release_verification:
    release: v1-f2d9efab126c
    verified_by: product-agent
    evidence: '2026-07-27: CampingTalk preflight is ready and validate returned validated=163
      invalid=0; user confirmed the associated operational procedure is functioning.'
    verified_at: '2026-07-27T11:30:18.030420+00:00'
  source_commit_verification: null
archive:
  archived_at: '2026-07-27T11:30:18.083206+00:00'
  archived_by: product-agent
  reason: User confirmed the legacy operational procedure is resolved; current representative
    Wiki validation is clean.
  restore_condition: Reopen if the recorded operational behavior fails again in the
    representative Wiki.
---
# cpt-wiki 루트에 비표준 파일 배치 문제

- Issue ID: `issue-20260721T090000Z-promotional-script-misplaced`
- Recorded at: 2026-07-21T09:00:00+09:00
- Reported by: hermes
- Reported from: user feedback
- Area: agent_rules
- Severity: low
- Status: open

## Summary

홍보용 이미지 제작 스크립트(`promotional-image-script.md`)를 cpt-wiki 저장소 루트에 직접 생성했다. cpt-wiki는 Knowledge OS 저장소로서 루트 디렉터리는 README.md, AGENTS.md, CLAUDE.md, HERMES.md, OPERATING_RULES.md 등 구조 정의 파일만 허용한다. 비예약 `.md` 파일은 YAML Frontmatter에 `type` 필드가 있어야 하며 (RB-KNW-003), 지식 콘텐츠는 `knowledge/` 아래 적절한 도메인 번들로 배치되어야 한다.

## Expected result

- 스크립트/워크플로우 성격의 파일은 cpt-wiki 외부(Hermes 스킬 등)에 저장하거나, cpt-wiki Knowledge OS 구조에 맞게 `knowledge/bundles/marketing/` 아래 정식 Bundle로 등록해야 한다.
- 루트 디렉터리는 구조 정의 파일 외의 임시/작업 파일을 두지 않아야 한다.

## Actual result

- `promotional-image-script.md`가 cpt-wiki 루트에 생성됨 (Frontmatter 없음, type 없음, 구조 위반)
- RB-KNW-003 위반: 비예약 `.md` 파일에 파싱 가능한 Frontmatter와 non-empty `type` 없음
- 루트 디렉터리 오염: Knowledge OS 구조 정의 파일만 있어야 하는 공간에 작업 파일이 침범

## Reproduction or context

- Hermes가 `promotional-image-script.md`를 `/home/cpt/work/cpt-wiki/` 루트에 write_file
- cpt-wiki의 README.md는 루트 구조를 `AGENTS.md, OPERATING_RULES.md, agent-rules/, README.md, docs/, knowledge/`로 명시

## Related paths or artifacts

- (삭제됨) `/home/cpt/work/cpt-wiki/promotional-image-script.md` → Hermes 스킬 `promotional-image-script`로 이전
- `/home/cpt/.hermes/skills/creative/promotional-image-script/SKILL.md` (정상 위치)
- `/home/cpt/.hermes/skills/creative/pikafu-promotional-image-prompt/SKILL.md` (정상 위치)

## Improvement hint

1. **Agent 규칙 추가**: cpt-wiki 루트에 파일을 생성할 때는 반드시 README.md의 구조 정의를 확인하고, 허용된 위치만 사용하도록 agent-rules에 명시
2. **스킬 우선 사용**: 반복 사용이 필요한 워크플로우/스크립트는 cpt-wiki 대신 Hermes 스킬로 저장하는 것이 적절
3. **지식 콘텐츠만 cpt-wiki**: 회사 지식/정책/런북에 해당하는 내용만 cpt-wiki의 `knowledge/bundles/`에 배치. 작업 도구/스크립트는 스킬로 분리
4. **Validator 경고**: cpt-wiki 루트에 비표준 `.md` 파일이 생성되면 validate에서 경고를 출력하도록 개선

## Review outcome

Pending system-maintainer review.

## Status history

- 2026-07-21T09:00:00+09:00: `open` by `hermes` — 초기 기록