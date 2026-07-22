---
type: template
title: Runbook Template
description: 반복 운영 절차 템플릿
tags: [template, runbook]
timestamp: 2026-07-09T00:00:00+09:00
---

# Runbook Template

```yaml
---
type: runbook
id: bundle/{organization_id}/{slug}_{bundle_uuid}.md
bundle_uuid: {bundle_uuid}
title: {title}
description: {description}
status: draft
summary: {summary}
updated_at: {updated_at}
owners:
  - {owner}
tags:
  - bundles
  - runbook
evidence:
  - evidence/{organization_id}/{name}_{source_uuid}.md
evidence_links:
  - "[{name}_{source_uuid}.md](evidence/{provider}/{yyyy}/{mm}/{dd}/{name}_{source_uuid}.md)"
links: []
extensions:
  source_uuids:
    - {source_uuid}
  review_state: pending
  knowledge_revision: 1
  visibility: internal
  pii_masked: false
  review_requested: false
  governance:
    reviewed_at: {reviewed_at}
    review_due_at: {review_due_at}
    freshness_policy: risk_based
    risk_tier: {critical|high|medium|low}
    source_volatility: {volatile|periodic|stable}
    validity_days: {positive_integer}
    change_triggers:
      - user_requested
      - user_reference
      - source_change
      - outcome_signal
    supersedes: []
    superseded_by:
  workflow:
    workflow_id: {workflow_id}
    version: 1
    execution_mode: guided
    trigger_intents:
      - {사용자 요청 예시}
    applies_to:
      - {적용 범위}
    excludes: []
    required_inputs:
      - name: {input_name}
        description: {입력 설명}
    steps:
      - id: collect-inputs
        title: 필수 입력 확인
        kind: action
      - id: human-approval
        title: 사람 승인
        kind: approval
        approvers:
          - {authorized_human_approver}
      - id: validate-output
        title: 결과 검증
        kind: validation
    approval_gates:
      - human-approval
    completion_criteria:
      - {완료 판정 기준}
    artifact_profile:
      type: {decision_report|work_guide|registration_package|design_brief|review_report|comparison_report}
      required_sections:
        - purpose
        - conclusion
        - evidence
        - risks
        - next_actions
        - open_questions
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

## When To Use

이 절차를 사용하는 상황을 작성한다.

## Prerequisites

필요 권한, 도구, 사전 조건을 작성한다.

## Procedure

`extensions.workflow.steps`와 같은 ID와 순서로 각 단계의 입력, 실행 주체, 사용할 Tool,
조건 분기, 산출물을 설명한다.

1. `collect-inputs`: 첫 번째 단계를 작성한다.
2. `human-approval`: 승인자가 확인할 내용을 작성한다.
3. `validate-output`: 완료 기준을 검사한다.

## Validation

성공 여부를 확인하는 방법을 작성한다.

## Failure Handling

실패 시 조치와 에스컬레이션 기준을 작성한다.

## Outcome Capture

완료·실패 결과에서 보존할 산출물 참조, 사용자 피드백, 학습 내용을 작성한다. 실행 중 Runtime Task 상태는
Bundle에 쓰지 않고 `.runtime/tasks/`에 보관한다. 종료 시 먼저 Outcome Inbox Item으로 수집하고, 검사·승인과
`ingest_accepted` 이후에만 Outcome Evidence가 된다.

Outcome은 `decisions`, `action_items`, `open_questions`를 본문 요약과 분리해 구조화한다. Action Item은
`title`, `owner`, `completion_criteria`를 필수로 하고 필요하면 `due_at`과 Evidence URI를 추가한다.

Runbook 파일은 `knowledge/bundles/<domain>/runbooks/`에 저장한다. 성공·실패 사례는 실제 산출물을
복제하지 않고 `extensions.workflow.examples`에 Outcome Evidence URI로 연결한다.
