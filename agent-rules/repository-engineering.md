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
- 운영 이슈·개선 사항에서 가져온 값이 특정 조직·프로젝트·머신에만 유효한지 확인
- 프로젝트 한정 값이 필요하면 `.circled-wiki/config.yaml`의 typed setting, 검증, 안전 기본값과 기존 config 호환 테스트가 함께 있는지 확인

## Gates

- 관련 테스트 통과
- `knowledge-os validate` 통과
- 사용자 Scope 밖 변경 없음
- 프로젝트 한정 값을 코드·규칙·템플릿·제품 기본값에 하드코딩하지 않고 설치 로컬 설정으로 주입
- 누락된 선택 설정은 조직 중립적 안전 기본값을 사용하고, 유효하지 않은 설정은 추정하지 않고 실패
- 기존 관리 ID가 있으면 `organization.id` 변경과 혼합 namespace의 새 ID 생성을 차단

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
- 실제 조직명·Organization ID·Owner·Agent 이름·머신 절대 경로·Git 대상·Integration 식별자를 제품 구현이나 기본값에 직접 복사
- API key, token, password, PII를 `.circled-wiki/config.yaml` 또는 설정 기본값에 저장
