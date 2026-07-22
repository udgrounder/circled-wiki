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
- Inbox Item과 변환할 텍스트를 직접 다시 읽어 자격증명·PII 평문, 과소 마스킹과 문맥상 재식별 가능성을 확인
- 파일형 입력은 불변 원본과 Evidence에 사용할 마스킹 파생본이 분리되어 있는지 확인

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치
- 처리 Agent의 마스킹 재확인 통과; 평문·고위험·판단 불가 항목은 Evidence를 생성하지 않고 `needs_review`

## Output

Evidence ID와 보존 경로

## Failure State

Inbox 원본과 필요 시 `.raw/`를 유지하고 Evidence 변환 실패를 반환한다. 마스킹 재확인 실패 시 발견한 값 자체를
로그·Issue·응답에 복사하지 않고 범주와 재검토 조건만 기록한다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
- 평문 자격증명·PII가 남은 입력 또는 안전한 마스킹 파생본이 없는 파일 ingest
- 마스킹 재확인만으로 `pii_scanned: true` 기록
