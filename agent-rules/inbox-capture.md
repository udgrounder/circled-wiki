# Inbox Capture Profile

## Trigger

사용자·Agent·Batch가 제공한 대화, URL에서 수집한 텍스트·HTML, PDF·Word·기타 원본 파일을 처리 대기열에 적재한다.

원문 없이 가이드·수집 방식만 조회하는 요청은 이 Profile의 Trigger가 아니다. Router의 `collection-handoff.md`를 선택한다.

## Input

- 원문(파일이면 Payload bytes)과 외부 문서인 경우 `source_ref`의 URL·locator
- provider, title, 수집 이유, intended use, idempotency key

## Allowed Actions

- **모든 수집 Agent와 Source Adapter의 공통 첫 단계**로 텍스트와 저장할 텍스트 메타데이터를 `.circled-wiki/policies/sensitive-data-masking.md`에 따라 민감정보 사전 점검한다. 이 단계는 특정 Agent의 선택 사항이 아니며 공통 Capture API를 우회할 수 없다.
- Capture는 현재 `data-protection.yaml`에서 `hard_mask_categories: true`인 하드 마스킹 값을 안전하게 처리한다. 매핑에서 빠진 지원 범주는 `true`로 간주하며, 기본 템플릿은 휴대전화·이메일을 `false`로 명시한다. `false`인 범주는 이 하드 PII 경로에서 처리하지 않는다.
- 텍스트는 `Markdown + 하드 마스킹된 수집 내용`으로, 파일은 `Markdown envelope + 동명 원본`으로 `knowledge/inbox/<provider>/`에 저장한다. 정책 판단 후보의 선택적 마스킹은 `review-data-protection`에서 수행한다.
- Capture의 `sensitivity_review` 기본값은 항상 `required`다. `completed` 또는 `not_applicable`은 Capture의 자동 판정값이 아니며, Inbox Inspection의 식별된 검토자가 남기는 명시적 결정으로만 해소한다.
- 파일 원본은 자동 수정하지 않고, 민감정보 가능성이 있으면 `sensitivity_review: required`로 유지해 Inspection에서 제한·파생본 처리를 결정
- checksum과 `pending` 상태 기록

## Checks

- provider 경로 형식
- 입력을 읽고 저장할 수 있는지, 파일 checksum이 원본과 일치하는지
- 동일 idempotency key와 checksum의 기존 pending 항목
- Capture 명령이 충돌을 반환하면 `existing_intake_id`와 상태를 먼저 조회할 수 있는지
- 현재 `hard_mask_categories: true`인 범주의 평문 잔존 여부
- 자동 점검 결과가 있으면 `capture_details.sensitive_data_precheck.masked`와 범주만 기록되고 실제 값은 기록되지 않는지

## Gates

- 비어 있지 않은 원문과 필수 메타데이터
- 안전한 provider 경로
- 동일 키의 checksum 충돌 없음
- 현재 활성 하드 범주의 1차 마스킹 완료. 정책 판단 후보·파일 원본·판단 불가 입력은 저장을 멈추지 않고 `sensitivity_review: required`로 두어 다음 단계에서 검토

## Output

`pending` Capture Receipt: Intake ID, Inbox Item 경로, checksum, 외부 문서의 경우 `source_ref`

## Failure State

수집 파일을 만들지 않고 입력 오류 또는 충돌을 반환한다. checksum 충돌은 기존 Intake ID·경로·checksum만 포함한
구조화된 복구 응답으로 반환하며, 원문은 출력하지 않는다. Agent는 기존 Inbox Item을 검사하고 변경된 원문이 의도된
새 revision일 때만 새 idempotency key를 사용한다. 충돌·CLI 실패가 입력·idempotency Gate의 정상 결과인지, 지침 부재·모호성 또는 Runtime 결함인지 개별 판단하고 후자로 판단한 경우에만 `system-observation` Profile로 Issue를 남긴다.

외부 수집 Agent가 Runtime을 실행할 수 없으면 원문과 알고 있는 메타데이터를 Wiki Agent에 전달해 대행 제출을 요청한다. Wiki Agent는
같은 Capture 메소드로 처리하며 원문을 재해석하거나 누락 값을 추정하지 않는다.

## Prohibited

- Evidence 생성
- Bundle 후보 탐색 또는 정제
- 전체 Repository Validator·단위 테스트 실행
- 실제 검사 없이 `pii_scanned: true` 주장
- 1차 마스킹만으로 통합 Data Protection Review 또는 `data_protection_receipt`가 완료됐다고 주장
- 비밀번호·token·private key를 일부만 남기는 부분 마스킹
- 불변 파일 원본을 직접 `*`로 덮어써서 checksum·출처 무결성을 훼손
- URL 주소만 보존하고 실제 수집한 원문 없이 원본을 확보했다고 주장
