# Workflow Execution Profile

## Trigger

공식 Runbook의 입력·단계·승인·완료 기준에 따라 사용자 업무를 실행한다.

## Input

- 선택된 active Runbook
- 사용자 요청과 Required Input

## Allowed Actions

- Runtime Task 생성과 입력 갱신
- 정의 순서에 따른 Step 기록
- 종료 Outcome을 `pending` Inbox로 기록

## Checks

- `find_workflow` 또는 portable CLI의 `find-workflow`로 active Runbook을 먼저 탐색했는지, Runbook 신선도와 실행 중 관찰 결과
- 직접 파일시스템 탐색은 공식 Workflow 탐색이 실패하거나 결과가 불충분할 때 작업을 계속하기 위한 최후 수단으로 사용한다. 그 결과가 지침 부재·모호성 또는 Runtime 결함인지 개별 판단하고,
  후자로 판단한 경우에만 `system-observation` Profile의 `record-system-issue`로 남긴 뒤 fallback 사유와 사용한 범위를 기록했는지
- 기존 공식 절차로 처리할 수 없는 Runbook 부재·모호성 때문에 사용자 의사 판단을 문의한 경우,
  `system-observation` Profile의 `record-system-issue`로 절차 부재·모호성, 막힌 단계와 안전한 다음 행동을 기록했는지

## Gates

- Required Input 충족
- 이전 Step 완료
- Approval Step의 실제 승인자 확인
- Completion Criteria 충족

## Output

Runtime Task 상태, 단계별 결과, Outcome Inbox Item의 Capture Receipt. Outcome Inbox Item은 Inbox 검사,
Inbox Sensitive Data Review, 승인과 `ingest_accepted`를 거친 후에만 Outcome Evidence가 된다.

## Failure State

`failed` 또는 `needs_review` 결과로 종료하고 재시도 조건을 기록한다. Required Input 누락은
`awaiting_input` 상태를 만들지 않으며, 누락 항목과 안전한 다음 행동을 가진 `needs_review`로 기록한다.

## Prohibited

- Step 생략 또는 순서 변경
- Self-approval
- Outcome으로 공식 Runbook 직접 변경
