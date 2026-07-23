# Operational Issue Intake Profile

## Trigger

사용자가 특정 운영 프로젝트의 Issue를 제품 Workspace로 이동해 검토해 달라고 명시적으로 요청한다.

## Input

- 운영 프로젝트 root와 안전한 `project-ref`
- 명시적인 Issue ID 또는 승인된 수집 범위
- 요청 사용자, 이동 actor와 수집 목적

## Allowed Actions

- `workspace/issues/`와 legacy `.circled-wiki/issues/` inventory
- Git 추적·커밋·미변경 상태 확인
- Archive 유사 이력 조회
- 지정 Issue를 `workspace/issue/inbox/<project-ref>/`로 원자적 이동

## Checks

- release, area, 증상, 관련 Archive occurrence와 과거 해결·검증 결과
- 민감정보와 머신 절대 경로가 제외됐는지

## Gates

- 사용자 요청 범위가 명확할 것
- legacy `.circled-wiki/issues/` Issue는 Runtime 운영 중 read-only이며, Product Agent의 명시적 수집 요청에서만 이동할 것
- 원본 Issue가 Git에 추적·커밋되어 있고 미커밋 변경이 없을 것
- 목적지 충돌과 Inbox/Archive 동시 존재가 없을 것
- 사용자 검토 전 Triage·제품 변경·Archive 금지

## Output

- `pending_review` Workspace Issue Item
- 이동·차단 결과와 유사 이력 후보

## Failure State

이동 실패 시 원본 위치의 파일 존재를 확인하고 성공을 주장하지 않는다.

## Prohibited

- 요청되지 않은 Issue 이동
- copy 후 delete 또는 목적지 덮어쓰기
- 사용자 review receipt 없는 상태 전환
