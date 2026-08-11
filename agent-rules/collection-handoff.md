# External Collection Handoff Profile

## Trigger

외부 수집 Agent가 원문·payload와 Capture 필수 입력값을 제공하지 않은 채, “외부 원문 전달 가이드”, “원문 입력 가이드”, “수집 방식”, 또는 Inbox 입력 방법만 요청할 때 사용한다.

## Input

- 가이드 또는 입력 방식 조회 요청
- 기존에 저장한 `handoff_version`(있으면)

## Allowed Actions

1. `get-collection-handoff()`를 호출한다.
2. 응답의 `handoff_version`, `method_spec_document`, `collection_guide_document`를 **수집 Agent에게 전달**한다.
3. 수집 Agent는 저장한 버전이 없거나 값이 달라진 경우에만 반환된 경로의 두 문서를 가져와 읽고, 그 내용에 따라 원문 입력을 준비·처리한다.

## Checks

- 실제 원문 또는 payload와 Capture 필수 입력값이 함께 제공됐는지 확인한다.
- 제공되지 않았다면 이 Profile을 유지한다.

## Gates

- Handoff 응답은 세 필드만 포함한다.
- 수집 Agent가 문서 경로를 필요할 때 가져가 처리하도록 Handoff를 전달한 뒤, Wiki Agent의 응답은 종료한다.
- 실제 원문과 필수 입력값이 함께 제공된 경우에만 다음 요청에서 `inbox-capture.md`로 전환한다.

## Output

```json
{
  "handoff_version": "<returned value>",
  "method_spec_document": "<returned path>",
  "collection_guide_document": "<returned path>"
}
```

## Failure State

`get-collection-handoff()`을 실행할 수 없으면 실행 불가 사실만 알리고, Capture 절차·입력 파라미터·후속 Inbox 처리 단계를 대신 설명하거나 추정하지 않는다.

## Prohibited

- Capture·Inspection·Data Protection Review·Evidence 전환의 절차, Gate, 파라미터 또는 실행 방법 설명
- `capture_*` 호출, Inbox 파일 생성, 원문·메타데이터 요청
- Handoff 문서 본문을 대신 읽어 Capture 절차로 재서술
