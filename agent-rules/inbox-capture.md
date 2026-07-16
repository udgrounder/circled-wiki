# Inbox Capture Profile

## Trigger

사용자·Agent·Batch가 제공한 대화, URL에서 수집한 텍스트·HTML, PDF·Word·기타 원본 파일을 처리 대기열에 적재한다.

## Input

- 원문(파일이면 Payload bytes)과 외부 문서인 경우 `source_ref`의 URL·locator
- provider, title, 수집 이유, intended use, idempotency key

## Allowed Actions

- 텍스트는 `Markdown + 원문`으로, 파일은 `Markdown envelope + 동명 원본`으로 `knowledge/inbox/<provider>/`에 저장
- checksum과 `pending` 상태 기록

## Checks

- provider 경로 형식
- 입력을 읽고 저장할 수 있는지, 파일 checksum이 원본과 일치하는지
- 동일 idempotency key와 checksum의 기존 pending 항목
- Capture 명령이 충돌을 반환하면 `existing_intake_id`와 상태를 먼저 조회할 수 있는지

## Gates

- 비어 있지 않은 원문과 필수 메타데이터
- 안전한 provider 경로
- 동일 키의 checksum 충돌 없음

## Output

`pending` Capture Receipt: Intake ID, Inbox Item 경로, checksum, 외부 문서의 경우 `source_ref`

## Failure State

수집 파일을 만들지 않고 입력 오류 또는 충돌을 반환한다. checksum 충돌은 기존 Intake ID·경로·checksum만 포함한
구조화된 복구 응답으로 반환하며, 원문은 출력하지 않는다. Agent는 기존 Inbox Item을 검사하고 변경된 원문이 의도된
새 revision일 때만 새 idempotency key를 사용한다. 충돌·CLI 실패는 `system-observation` Profile로 Issue를 남긴다.

## Prohibited

- Evidence 생성
- Bundle 후보 탐색 또는 정제
- 전체 Repository Validator·단위 테스트 실행
- 실제 검사 없이 `pii_scanned: true` 주장
- URL 주소만 보존하고 실제 수집한 원문 없이 원본을 확보했다고 주장
