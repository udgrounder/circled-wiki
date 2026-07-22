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
- 읽은 Bundle·Evidence excerpt와 작성할 답변에 자격증명·PII 평문 또는 문맥상 재식별 정보가 남는지 확인

## Gates

- `restricted` 권한
- `verified` 주장에 접근 가능한 Evidence 존재
- 응답 전 최종 마스킹 확인; 의심 값은 `*`로 가리거나 답변에서 제외하고 필요하면 보안 검토로 전환

## Output

사실·추정·미검증 내용을 구분한 읽기 전용 답변

## Failure State

근거 부족 또는 권한 제한을 명시하고 공식 답을 추정하지 않는다.

## Prohibited

- Task 또는 Repository 파일 생성
- 조회만으로 Bundle 수정
- Bundle·Evidence에 남아 있던 자격증명·PII를 사용자 답변에 재출력
