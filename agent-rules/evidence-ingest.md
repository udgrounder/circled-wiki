# Evidence Ingest Profile

## Trigger

`accepted` Inbox 항목을 추적 가능한 Evidence로 변환한다.

## Input

- 승인된 Inbox Item, 검사 기록, 외부 문서의 `source_ref`

## Applicable Global Rules

- Evidence 수명주기·무결성·저장: RB-EVD-002·004~010·013·015·017~021·023
- 민감정보 재검수와 PII Receipt: RB-SEC-001·005·010

## Allowed Actions

- `.raw/` 경유
- source UUID와 Evidence ID 발급
- Embedded Evidence Document 또는 Evidence Original+External-file Evidence Manifest 생성
- 원본 checksum과 출처 보존
- RB-EVD-021·RB-SEC-010의 생성 직전 민감정보 재검수와 안전한 파생 입력 생성
- RB-EVD-020·RB-SEC-005의 PII Scan 결과를 Evidence 생성 입력에 전달

## Checks

- idempotency key로 기존 Evidence 재사용 여부
- 저장 크기와 보존 방식
- Inbox Item과 변환할 텍스트를 직접 다시 읽어 RB-EVD-021의 누락·과소 마스킹과 문맥상 재식별 가능성을 확인
- 파일형 입력은 불변 원본과 Evidence에 사용할 마스킹 파생본이 분리되어 있는지 확인

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치
- RB-EVD-021·RB-SEC-010의 재검수 Gate 통과
- PII Scan 입력이 있으면 RB-EVD-020·RB-SEC-005의 Receipt Gate 통과. `needs_review` 결과는 Inbox에 유지하고 Evidence로 변환하지 않음
- Evidence와 Curation Queue가 RB-EVD-023의 동일 처리 단위로 확정될 것

## Output

RB-EVD-023에 따라 함께 확정된 Evidence ID·보존 경로와 Curation Queue 항목.

## Failure State

RB-EVD-007·023에 따라 Inbox 원본과 필요 시 `.raw/`를 유지하고 Evidence·Queue의 부분 성공을 남기지 않는다.
민감정보 실패는 RB-SEC-001에 따라 실제 값 없이 범주와 재검토 조건만 기록한다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
- RB-EVD-020·021·023 또는 RB-SEC-001·005·010을 우회한 Evidence 생성
