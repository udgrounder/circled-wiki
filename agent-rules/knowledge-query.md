# Knowledge Query Profile

## Trigger

정책, 사실, 과거 결정 또는 공식 지식을 조회한다.

## Input

- 사용자 질문
- Knowledge MCP 검색 결과와 공식 Bundle

## Allowed Actions

- `search_knowledge`, `read_bundle`, `prepare_context`
- 출처와 지원 상태를 포함한 답변

## Checks

- 관련 Bundle의 최신성·상태·지원 수준

## Gates

- `restricted` 권한
- `verified` 주장에 접근 가능한 Evidence 존재

## Output

사실·추정·미검증 내용을 구분한 읽기 전용 답변

## Failure State

근거 부족 또는 권한 제한을 명시하고 공식 답을 추정하지 않는다.

## Prohibited

- Task 또는 Repository 파일 생성
- 조회만으로 Bundle 수정
