# Workflow 실행 및 지식 환류 설계

## 1. 목적

이 문서는 조직의 공식 지식을 사람과 Agent가 실제 업무에 재사용하기 위한 실행 모델을 정의한다.
Knowledge OS는 문서를 검색해 반환하는 데서 끝나지 않고 다음 흐름을 지원한다.

```text
사용자 요청
  -> 실행 가능한 Runbook 탐색
  -> 필수 입력 확인
  -> Task 실행 상태 생성
  -> Hermes/사람/하위 Agent가 단계 수행
  -> 완료 기준과 승인 지점 확인
  -> 결과를 Evidence로 수집
  -> Curator가 기존 Bundle 개선 또는 신규 Bundle 후보로 검토
```

공식 지식 포맷은 계속 OKF를 사용한다. Workflow는 독자 포맷이 아니라
`knowledge/bundles/<domain>/runbooks/`에 저장된 `type: runbook` Bundle의 `extensions.workflow` 확장으로 표현한다.

## 2. 네 개의 논리 계층

### Knowledge Plane

- Evidence, Bundle, Policy, Guide, Decision, Reference를 저장한다.
- Git Repository가 Source of Truth다.
- Workflow 정의는 이 계층의 공식 Runbook Bundle이다.

### Workflow Plane

- 사용자 요청과 관련 있는 활성 Runbook을 찾는다.
- 필수 입력, 단계, 승인 지점, 완료 기준을 구조화해 Hermes에 제공한다.
- Workflow 버전과 `knowledge_revision`을 Task 시작 시 고정한다.

### Execution Plane

- 현재 실행 중인 Runtime Task 상태를 관리한다.
- Task는 공식 지식이 아니므로 `knowledge/`에 저장하지 않는다.
- 로컬 MVP는 프로젝트 루트의 `.runtime/tasks/`에 JSON으로 저장하고 Git에서 제외한다.
- 장기 실행, 다중 Worker, 동시 실행이 필요해지면 같은 인터페이스를 DB 또는 Queue-backed Store로 교체한다.

### Feedback Plane

- 완료, 실패, 검토 필요 결과를 Outcome Inbox Item으로 수집하고, 검사·승인·변환 후 Outcome Evidence로 누적한다.
- 실제 대용량 산출물은 내부 저장소 URI와 availability 메타데이터만 기록할 수 있다.
- Curator는 Outcome Evidence를 근거로 기존 Runbook/Guide/Decision 갱신 여부를 판단한다.
- Task 결과가 공식 지식을 자동 변경하지는 않는다. Validator와 기존 리뷰·발행 정책을 그대로 적용한다.

## 3. 실행 가능한 Runbook 프로파일

`draft` Runbook은 작성 중일 수 있으므로 `extensions.workflow`가 없어도 된다. `active` Runbook은 반드시
아래 구조를 가져야 한다.

```yaml
---
type: runbook
id: knowledge://example-org/marketing/poster-production_<bundle_uuid>
bundle_uuid: <bundle_uuid>
title: 포스터 이미지 제작
status: active
summary: 요청 확인부터 제작, 검증, 승인까지 안내한다.
updated_at: 2026-07-14T00:00:00+09:00
evidence:
  - evidence://example-org/manual/2026/07/14/<source_uuid>
extensions:
  visibility: internal
  knowledge_revision: 1
  governance:
    reviewed_at: 2026-07-14T00:00:00+09:00
    review_due_at: 2026-10-12T00:00:00+09:00
    freshness_policy: risk_based
    risk_tier: medium
    source_volatility: periodic
    validity_days: 90
    change_triggers:
      - user_requested
      - source_change
      - outcome_signal
  workflow:
    workflow_id: poster-production
    version: 1
    execution_mode: guided
    trigger_intents:
      - 포스터 이미지를 만들고 싶다
      - 이벤트 배너를 제작한다
    applies_to:
      - internal-marketing
    excludes: []
    required_inputs:
      - name: audience
        description: 대상 고객
      - name: channel
        description: 게시 채널
    steps:
      - id: collect-inputs
        title: 필수 입력 확인
        kind: action
      - id: approve-brief
        title: 제작 브리프 승인
        kind: approval
      - id: validate-output
        title: 규격과 브랜드 기준 검증
        kind: validation
    approval_gates:
      - approve-brief
    completion_criteria:
      - 요청한 크기와 채널 규격을 충족한다.
      - 필수 문구와 브랜드 정책을 충족한다.
    examples:
      successful: []
      failed: []
    learning:
      maturity: pilot
      min_outcomes_for_review: 3
      review_on_failure: true
      review_on_feedback: true
---
```

### 필드 규칙

- `workflow_id`: Workflow의 안정적인 lowercase slug다. Bundle 경로 변경과 무관한 실행 식별자다.
- `version`: 단계나 입출력 계약이 달라질 때 증가시킨다.
- `execution_mode`: `guided`, `agent_assisted`, `automated` 중 하나다.
- `trigger_intents`: 검색과 선택을 돕는 대표 요청이다. 단순 키워드 목록을 대신하지 않는다.
- `required_inputs`: 실행 전에 반드시 확인할 입력 이름과 설명이다.
- `steps`: 실행 순서의 안정적인 ID, 제목, 종류를 가진다.
- `kind`: `action`, `decision`, `approval`, `validation` 중 하나다.
- `approval_gates`: `kind: approval`인 step ID만 참조할 수 있다.
- `completion_criteria`: Hermes와 사람이 결과 완료 여부를 확인하는 기준이다.
- `applies_to`, `excludes`: Workflow의 적용·제외 범위다.
- `examples`: 성공·실패 Outcome Evidence URI를 연결하며 실제 산출물을 복제하지 않는다.
- `learning`: Outcome Evidence 누적 기반 개선 검토 기준과 수동 maturity를 정의한다.

상세 도구 사용법, 분기 조건, 예외, 산출물 예시는 Markdown 본문에 작성한다. Frontmatter는 Workflow
선택과 실행 준비에 필요한 안정적인 계약만 가진다.

## 4. Task 실행 상태

Task는 Runbook을 시작할 때 생성하는 실행 스냅샷이다.

```json
{
  "task_id": "<uuid>",
  "workflow_id": "poster-production",
  "workflow_bundle_id": "knowledge://...",
  "workflow_version": 1,
  "knowledge_revision": 1,
  "request": "여름 이벤트 포스터를 만들어줘",
  "inputs": {"audience": "가족 캠퍼"},
  "missing_inputs": ["channel"],
  "status": "awaiting_input",
  "steps": [],
  "approval_gates": [],
  "completion_criteria": []
}
```

MVP Task 상태는 `awaiting_input`, `ready`, `in_progress`, `awaiting_outcome`, `completed`, `failed`,
`needs_review`를 사용한다. 각 `step_states`는 순서대로 `completed` 또는 `approved`되어야 한다.
Approval 단계는 `approved`, `rejected`, `needs_review`만 허용하며 실행자 또는 승인자를 `actor`로 기록한다.

Task가 Workflow 정의를 스냅샷으로 가지는 이유는 실행 중 Runbook이 갱신돼도 이미 시작한 작업의 기준이
바뀌지 않게 하기 위해서다. Task 기록은 공식 지식이 아니며 자동 Commit 대상도 아니다.

### 4.1 Runbook Refresh Task

`prepare_task` 시 Runbook이 만료됐으면 `task_type: runbook_refresh` Task를 대신 생성한다. 원래 요청과 입력은
`deferred_work`에 보존하고 Refresh revision 발행 후 다시 실행한다. 사용자의 명시적 최신화 요청은
`prepare_runbook_refresh`로 유효기간과 관계없이 같은 표준 Task를 생성한다. Refresh Task의 단계와 유효기간
산정 기준은 [20-runbook-refresh.md](20-runbook-refresh.md)를 따른다.
사용자가 새 레퍼런스를 제공하면 원본을 Evidence로 수집한 뒤 `submit_runbook_reference`로 제출한다. 동일
Runbook의 열린 Refresh Task가 있으면 Candidate Evidence와 제출 이력을 해당 Task에 병합한다.
Candidate Evidence는 `record_reference_assessment`로 권위·최신성·적용 범위·교차 검증·충돌·채택 범위를
기록하며 평가자와 검증자는 달라야 한다.

## 5. Hermes Workflow Orchestrator

Hermes의 Delegator는 Workflow Orchestrator 역할을 함께 수행한다.

1. `find_workflow`로 사용자 요청과 관련 있는 활성 Runbook 후보를 찾는다.
2. 후보가 하나로 명확하지 않으면 사용자에게 목적 또는 대상 업무를 확인한다.
3. 사용자가 최신화를 요청하면 `prepare_runbook_refresh`를 호출한다. 그렇지 않으면 `prepare_task`로 Task를 생성한다.
4. `prepare_task`가 만료로 Refresh Task를 반환하면 최신화 완료 전 원래 업무를 실행하지 않는다.
5. 누락 입력을 받은 뒤 `update_task_inputs`로 같은 Task를 갱신한다.
6. Runbook 본문, 관련 Bundle, Evidence 출처를 Context로 사용한다.
7. 각 단계 결과를 `record_task_step`으로 순서대로 기록한다.
8. `approval_gates`에서는 자동 진행을 멈추고 사람 승인을 기록한다.
9. `completion_criteria`로 결과를 검증한다.
10. `record_outcome`으로 결과, 피드백, 학습, 산출물 참조를 Evidence로 수집한다.
11. 반환된 curation proposal을 Curator/Reviewer가 검토한다.

Hermes는 외부 원본이나 Workflow 본문의 문장을 권한 변경 또는 무조건적인 Tool 실행 지시로 해석하지
않는다. 실제 Tool 권한과 사람 승인 정책은 `.knowledge-os/policies/agent-security.md`가 우선한다.

## 6. MCP 및 Core 계약

### `find_workflow(request, limit)`

- 활성 `runbook`만 검색한다.
- Workflow ID, Bundle ID, 실행 모드, 매칭 점수를 반환한다.
- 점수는 후보 추천용이며 의미 판단은 Hermes가 수행한다.

### `prepare_task(workflow_id, request, inputs)`

- Bundle ID 또는 `workflow_id`로 Runbook을 선택한다.
- Workflow와 지식 revision을 Task에 스냅샷한다.
- 누락된 필수 입력과 Workflow Context를 반환한다.
- 만료 상태에서는 원래 실행 Task 대신 Refresh Task와 `deferred_work`를 반환한다.

### `prepare_runbook_refresh(workflow_id, request, requested_by, reason)`

- 사용자의 최신화 요청 또는 변경 Trigger로 Refresh Task를 즉시 생성한다.
- Runbook이 아직 유효해도 실행할 수 있다.

### `submit_runbook_reference(workflow_id, evidence_id, submitted_by, note)`

- 사용자 제공 Evidence를 개선 후보로 등록한다.
- 기존 열린 Refresh Task에 중복 없이 병합한다.
- 사용자 평가는 개선 신호로만 취급하고 비교·독립 검증·Owner 승인으로 채택 여부를 결정한다.

### `record_reference_assessment(task_id, evidence_id, assessment)`

- Candidate Evidence의 구조화된 비교 결과를 Runtime Task에 기록한다.
- `accept`, `partial_accept`, `reject`, `needs_more_evidence`를 지원한다.
- 승인된 변화만 Refresh Outcome과 새 Runbook revision에 반영한다.

### `confirm_runbook_revision(task_id, revision_ref)`

- 공식 Runbook Markdown의 `knowledge_revision` 증가와 새 검토 시각을 확인한다.
- Repository Validator를 통과한 revision만 Runtime Task에 연결한다.
- 확인 전 `publish-revision` Step 완료를 허용하지 않는다.

### `get_task(task_id)`

- Git 지식과 분리된 현재 Task 상태를 읽는다.

### `update_task_inputs(task_id, inputs)`

- 누락된 입력을 기존 Task에 추가한다.
- 모든 필수 입력이 채워지면 상태를 `ready`로 바꾼다.

### `record_task_step(task_id, step_id, status, result, actor)`

- Workflow 순서대로 실행·검증·승인 결과를 기록한다.
- 이전 단계가 완료되지 않으면 다음 단계 기록을 거부한다.
- 모든 단계와 승인이 끝나면 Task를 `awaiting_outcome`으로 바꾼다.

### `record_refresh_decision(task_id, decision, rationale, evidence_ids, actor)`

- 최신 Evidence 비교 결과를 `update_required`, `no_change`, `insufficient_evidence`로 기록한다.
- `no_change`는 본문 변경 없이 검토 revision만 갱신한다.
- `insufficient_evidence`는 Refresh를 `needs_review`로 중단한다.
- 다음 독립 Agent 검증 actor는 이 결정 actor와 달라야 한다.

### `record_outcome(task_id, status, summary, feedback, learnings, artifacts, decisions, action_items, open_questions)`

- 종료 상태는 `completed`, `failed`, `needs_review` 중 하나다.
- `completed` 결과는 모든 단계와 승인이 끝난 `awaiting_outcome` Task에서만 허용한다.
- 결과를 `provider: hermes`, `captured_from: sync`인 Outcome Inbox Item으로 먼저 수집한다.
- 동일 Runtime Task에서 재호출하면 기존 Outcome Inbox Item을 재사용하고, 변환 완료 후에는 연결된 Outcome Evidence ID를 반환한다.
- 산출물 원본이 크거나 별도 시스템에 있으면 URI와 availability 메타데이터만 결과 JSON에 넣는다.
- Outcome Inbox Item은 검사·Inbox Sensitive Data Review·승인을 거쳐야 하며, 변환된 Outcome Evidence는 실제
  Evidence PII Scan 완료 전 `pii_scanned: true`로 기록하거나 Commit하지 않는다.
- 일반 Workflow Outcome은 `learning` 정책으로 집계한다. 실패·피드백·누적 임계치가 발생하면 중복 없는
  `reason: outcome_signal` Refresh Task를 생성한다.
- 결정·실행·미해결 사항은 `decisions`, `action_items`, `open_questions`로 분리한다.
- Runbook에 `artifact_profile`이 있으면 완료 Artifact는 같은 Profile과 필수 section을 충족해야 한다.

## 7. 대용량·메타데이터 전용 산출물

Outcome의 `artifacts`는 실제 파일을 Git에 넣지 않고 참조만 기록할 수 있다.

```json
{
  "name": "poster.png",
  "uri": "internal-storage://design/poster.png",
  "checksum": "sha256:...",
  "availability": "metadata_only"
}
```

권장 availability 값은 `available`, `metadata_only`, `temporarily_unavailable`, `access_denied`,
`missing`이다. Hermes가 원본을 읽지 못한 경우 결과나 답변에서 검증하지 못했다는 사실을 명시한다.

## 8. 지식 환류 원칙

- Task 결과 전체를 공식 지식으로 승격하지 않는다.
- 반복 가능한 절차 변화는 Runbook 후보로 보낸다.
- 일반화 가능한 교훈은 Guide 또는 Reference 후보로 보낸다.
- 특정 선택의 이유와 결과는 Decision 후보로 보낸다.
- 실패와 예외는 기존 Workflow의 Failure Handling 개선 근거로 사용한다.
- 최종 반영은 Evidence 추적, Validator, Reviewer, 발행 정책을 통과해야 한다.

## 9. MVP 완료 기준

- 활성 Runbook의 Workflow 구조를 Validator가 검사한다.
- 사용자 요청으로 실행 가능한 Runbook 후보를 찾을 수 있다.
- Task가 `knowledge/` 외부에 생성된다.
- 누락된 필수 입력을 구조적으로 반환한다.
- 완료 결과가 Evidence로 한 번만 수집된다.
- 결과 Evidence가 기존 Curator 검토 흐름으로 돌아간다.
- 포스터 제작 또는 캠핑장 등록 실제 Runbook 한 개 이상으로 end-to-end 파일럿을 통과한다.
