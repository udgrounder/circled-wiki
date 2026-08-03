# Evidence Ingest Profile

## Trigger

`accepted` Inbox 항목을 추적 가능한 Evidence로 변환한다.

## Input

- 승인된 Inbox Item, 검사 기록, 외부 문서의 `source_ref`

## Applicable Global Rules

- Evidence 수명주기·무결성·저장: RB-EVD-002·004~010·013·015·017~021·023
- 단일 PII Scan Receipt: RB-SEC-001·005·010

## Allowed Actions

- source UUID와 Evidence ID 발급
- Embedded Evidence Document 또는 Evidence Original+External-file Evidence Manifest 생성
- 원본 checksum과 출처 보존
- RB-EVD-020의 PII Scan이 확정한 후보와 Receipt를 Evidence 생성 입력에 전달

## Checks

- idempotency key로 기존 Evidence 재사용 여부
- 저장 크기와 보존 방식
- PII Scan Receipt의 후보 checksum과 Evidence 입력 checksum이 같은지 확인
- 파일형 입력은 불변 원본과 PII Scan이 확정한 안전한 후보가 분리되어 있는지 확인

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치
- RB-EVD-020·RB-SEC-005의 PII Scan Receipt Gate 통과. `needs_review`는 정상 `awaiting_user` 결과로 Inbox에 유지하고 `workspace/task/inbox_reconciliation/`에 현재 단계·요청 조치만 기록하며 Evidence로 변환하지 않음
- Evidence와 Curation Queue가 RB-EVD-023의 동일 처리 단위로 확정될 것

## Output

RB-EVD-023에 따라 함께 확정된 Evidence ID·보존 경로와 Curation Queue 항목.

## Failure State

RB-EVD-007·023에 따라 Inbox 원본을 유지하고 Evidence·Queue의 부분 성공을 남기지 않는다. Inbox 예외 계약 작업은 사용자 결정 후에도 Evidence와 Curation Queue의 동일 처리 단위가 성공할 때까지 `reprocessing`으로 유지한다.
PII Scan이 `needs_review`이면 RB-SEC-001에 따라 실제 값 없이 범주와 재검토 조건만 기록하고, Queue 상태를 검증한 뒤 `awaiting_user`로 유지한다. 처리 주체 변경 또는 종료 시의 Commit·Push는 Publication Profile이 수행한다. 파일 쓰기·Validator·Git·Push 실패만 실제 실패로 처리한다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
- RB-EVD-020·021·023 또는 RB-SEC-001·005·010을 우회한 Evidence 생성
