# Inbox Business-Relevance Disposition Profile

## Trigger

`pending` Inbox 항목이 `non_business_confirmed`로 명확히 판정됐을 때 보존 격리하거나, 격리 항목을 일괄 검토한다.

## Input

- `pending` Inbox Item의 ID
- 분류 결과, 분류기 식별자, 규칙 버전, 짧은 근거
- 폐기 검토 시 `recover` 또는 `dispose` 결정과 actor

## Allowed Actions

- `non_business_confirmed`만 `quarantine_inbox_item`으로 원문 보존 격리한다.
- `list_inbox_disposals`로 격리 대기 목록을 조회한다.
- 일괄 검토 결정으로만 `decide_inbox_disposal`을 실행한다.

## Checks

- 비업무 확정 시 분류기, 규칙 버전, 근거가 비어 있지 않은지
- 격리·복구 후 원문과 payload가 Evidence·Curation 탐색 대상이 아닌지 또는 정상 Inbox에만 있는지

## Gates

- 분류 불가 또는 애매함은 기록·폐기·격리 없이 일반 Inbox Inspection으로 보낸다.
- `non_business_confirmed` 외 결과는 격리할 수 없다.
- 영구 폐기는 격리 후 별도 actor의 일괄 검토 결정으로만 가능하다.

## Output

- Inbox의 checksum 보존 업무성 분류 Receipt 또는 보존 격리·처분 Receipt

## Failure State

원문을 `pending` Inbox에 유지하고 일반 Inbox Inspection으로 보낸다. 원문을 추정해 폐기하지 않는다.

## Prohibited

- 비업무성이 명확하지 않은 항목을 격리·폐기
- 애매한 항목의 격리·폐기
- 격리 원문의 Evidence 변환·Curation
- 처분 검토 없이 원문 또는 payload 삭제
