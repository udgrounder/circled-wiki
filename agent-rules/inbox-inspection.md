# Inbox Inspection Profile

## Trigger

`pending` Inbox 대화·문서·파일 항목을 다음 단계로 넘길 수 있는지 검사하거나 검사 결과를 승인한다.

## Input

- 자기완결형 Inbox Item Markdown 또는 Inbox Envelope와 원본 Payload
- 검사자 actor

## Allowed Actions

- 원문 checksum, 필수 메타데이터, provider 폴더, Inbox Sensitive Data Review 상태 검사
- 외부 문서의 source URL·locator 존재 여부 검사
- `required` 민감성 상태는 식별된 검토자의 `completed` 또는 `not_applicable` 결정으로만 해소
- 통과 항목을 검사자 actor와 함께 `accepted`로 기록

## Checks

- 내용 유형과 intended use의 타당성
- 재사용 가치와 보존 분류

## Gates

- checksum 일치
- provider와 폴더 일치
- 필수 메타데이터 완전성
- `sensitivity_review`가 `completed` 또는 `not_applicable`

## Output

읽기 전용 검사 보고서, Inbox Sensitive Data Review 기록 또는 `accepted` Inbox Item 상태

## Failure State

원본을 `pending` Inbox에 유지하고 문제 목록과 재검사 조건을 반환한다.

## Prohibited

- Evidence 또는 Bundle 생성
- 원문 자동 수정
- 검사자 정보 없는 승인
- 수집 Agent가 Inbox Sensitive Data Review를 완료했다고 자동 기록
