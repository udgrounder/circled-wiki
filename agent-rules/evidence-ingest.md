# Evidence Ingest Profile

## Trigger

`accepted` Inbox 항목을 추적 가능한 Evidence로 변환한다.

## Input

- 승인된 Inbox Item, 검사 기록, 외부 문서의 `source_ref`

## Allowed Actions

- `.raw/` 경유
- source UUID와 Evidence ID 발급
- Embedded Evidence Document 또는 Evidence Original+External-file Evidence Manifest 생성
- 원본 checksum과 출처 보존

## Checks

- idempotency key로 기존 Evidence 재사용 여부
- 저장 크기와 보존 방식

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치

## Output

Evidence ID와 보존 경로

## Failure State

Inbox 원본과 필요 시 `.raw/`를 유지하고 Evidence 변환 실패를 반환한다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
