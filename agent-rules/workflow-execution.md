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

- Runbook 신선도와 실행 중 관찰 결과

## Gates

- Required Input 충족
- 이전 Step 완료
- Approval Step의 실제 승인자 확인
- Completion Criteria 충족

## Output

Task 상태, 단계별 결과, Outcome Inbox 영수증. Outcome은 Inbox 검사·민감성 검토·승인 후에만 Evidence가 된다.

## Failure State

`awaiting_input`, `failed`, `needs_review` 중 해당 상태로 유지하고 재시도 조건을 기록한다.

## Prohibited

- Step 생략 또는 순서 변경
- Self-approval
- Outcome으로 공식 Runbook 직접 변경
