# Repository Engineering Profile

## Trigger

코드, 스키마, 테스트, `AGENTS.md`, `OPERATING_RULES.md`, `agent-rules/` 또는 운영 문서를 변경한다.

## Input

- 사용자가 승인한 변경 Scope
- 현재 작업 트리와 관련 구현
- 필요할 때만 Reference Traceability가 지정한 `docs/` 문서

## Allowed Actions

- 승인 Scope 안의 Repository 파일 수정
- 관련 단위·통합 테스트와 Validator 실행
- 기존 사용자 변경을 보존한 진단

## Checks

- 변경 영향 범위와 하위 호환성
- 관련 규칙·문서·테스트의 동기화

## Gates

- 관련 테스트 통과
- `knowledge-os validate` 통과
- 사용자 Scope 밖 변경 없음

## Output

- 변경 파일
- 검증 결과
- 남은 외부 의존성 또는 제한

## Failure State

변경을 발행하지 않고 실패 원인과 재현 방법을 보고한다.

## Prohibited

- Runtime 입력 하나를 수집하기 위해 전체 Repository 테스트 실행
- 사용자 승인 없는 외부 발행·Commit
- `docs/`를 Runtime 운영 규칙으로 사용
