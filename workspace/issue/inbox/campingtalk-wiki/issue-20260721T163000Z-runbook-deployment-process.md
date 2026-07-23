---
type: workspace_issue
status: pending_review
workspace_issue_id: workspace-issue-00307f78532e4d5288c922c809fd521b
source_project_ref: campingtalk-wiki
source_issue_id: issue-20260721T163000Z-runbook-deployment-process
source_release: v1-dafe663754a3
source_git_revision: b3192996e27485c1a589e6a2f6631cbb05bf339b
moved_at: '2026-07-23T10:19:55.129244+00:00'
moved_by: codex
requested_by: user
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
archive:
  archived_at: null
  archived_by: null
  reason: null
  restore_condition: null
---
# runbook 생성 및 배포 작업 미흡 사항

- Issue ID: `issue-20260721T163000Z-runbook-deployment-process`
- Recorded at: 2026-07-21T16:30:00+09:00
- Reported by: hermes
- Reported from: agent
- Area: workflow
- Severity: low
- Status: open

## Summary

홍보용 포스터/팜플렛 AI 이미지 제작 Runbook(`marketing/ai-promotional-image-production`) 생성 및 배포 과정에서 여러 미흡 사항이 발생했다.

## Issues

### 1. Git에 불필요한 파일이 Commit됨

초기 `create-bundle` 및 `publish-changes` 과정에서 아래 파일들이 Git에 포함되었다:

- `src/**/__pycache__/*.cpython-311.pyc` — Python 바이트코드 캐시 (약 20개 파일)
- `.circled-wiki-backups/` — 백업 디렉터리 전체
- `.temp/runbook-body.md` — 임시 작업 파일

**원인**: `git add -A`를 사용했으나 `.gitignore`가 없거나 `__pycache__`와 `.temp`가 제외되지 않음.

**영향**: 저장소 크기 증가, 리뷰 노이즈.

**권장 조치**: `.gitignore`에 `__pycache__/`, `*.pyc`, `.temp/`, `.circled-wiki-backups/` 추가.

### 2. 하위 agent 위임 누락

초기 pipeline 작업(Inbox 수집 → 검사 → Evidence 변환 → Bundle 생성 → Git commit)을 직접 CLI로 실행했다. 사용자 지침에 따라 delegate_task로 하위 agent에게 위임해야 했다.

**원인**: 메모리에 저장된 작업 분배 규칙을 확인하지 않음.

**영향**: 불필요한 컨텍스트 사용, 작업 추적성 저하.

**권장 조치**: Knowledge OS pipeline 작업은 항상 delegate_task 우선.

### 3. 첫 번째 위임에서 owners 설정 오류

처음 위임 시 `owners: ["marketing-team"]`으로 설정했으나, 이후 사용자가 `["dev"]`를 기본값으로 지정하여 두 번째 위임에서 수정 필요.

**원인**: 사전에 owners 기본값을 확인하지 않음.

**영향**: 불필요한 추가 위임 발생.

**권장 조치**: Runbook 생성 시 owners 기본값 `["dev"]`를 항상 사용.

### 4. Runbook 본문에 workflow 프롬프트 미포함

Runbook 본문(섹션 6. 워크플로우)이 단순 텍스트로만 작성되어 있고, `extensions.workflow`의 trigger_intents와 steps 정보가 frontmatter에만 있고 본문 설명이 부족함.

**원인**: 초기 create-bundle 시 body-file에 workflow 실행 절차가 상세히 포함되지 않음.

**영향**: 사람이 읽을 때 workflow 실행 흐름을 파악하기 어려움.

**권장 조치**: 본문 섹션 6을 frontmatter의 workflow 정의와 일치하도록 보강.

### 5. 수동 pipeline 실행으로 인한 자동 curation 우회

새벽 04:00 dawn-curation 파이프라인을 기다리지 않고 수동으로 capture → inspect → accept → ingest → create-bundle → publish를 전부 실행함.

**원인**: 즉시 결과 확인을 위해 파이프라인을 수동으로 진행.

**영향**: 자동화된 검증/거버넌스 프로세스를 우회.

**권장 조치**: 긴급하지 않은 경우 dawn-curation을 통해 자동 처리하고, 긴급한 경우에만 수동 실행.

## Related paths or artifacts

- `knowledge/bundles/marketing/runbooks/ai-promotional-image-production_5a26d6f2-821e-4a9e-a298-ad3db3b42b4c.md`
- `knowledge/evidence/hermes/2026/07/21/ai_3175a0e6-09ea-460c-a1a9-a1e7f3b807ef.md`
- `~/.hermes/skills/creative/promotional-image-prompt/SKILL.md`

## Improvement hint

1. `.gitignore`에 `__pycache__/`, `*.pyc`, `.temp/`, `.circled-wiki-backups/` 추가
2. Knowledge OS pipeline 작업은 항상 delegate_task로 위임
3. owners 기본값 `["dev"]` 준수
4. Runbook 본문과 frontmatter workflow 정의 일치 유지
5. 긴급하지 않은 작업은 dawn-curation 자동 파이프라인 활용

## Review outcome

Pending system-maintainer review.

## Status history

- 2026-07-21T16:30:00+09:00: `open` by `hermes` — 초기 기록