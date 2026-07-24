# Repository Engineering Profile

## Trigger

코드, 스키마, 테스트, Product/Runtime 규칙 또는 제품 문서를 변경한다.

## Input

- 사용자가 승인한 변경 Scope
- 현재 작업 트리와 관련 구현
- 운영 Issue 기반이면 검토된 Workspace Issue와 Triage 결과

## Allowed Actions

- 승인 Scope 안의 Repository 파일 수정
- 관련 단위·통합 테스트와 Validator 실행
- 운영 Issue를 재현하는 실패 테스트와 회귀 테스트 추가

## Checks

- 하위 호환성, Runtime 배포 영향과 문서·규칙 동기화
- 기존 Archive 해결책·회귀 테스트의 적용 가능성
- Archive lifecycle 변경이면 대상이 Bundle인지 Workspace Issue인지 구분한다. Bundle은
  `knowledge/bundles/archive/<domain>/` 이동·검색 제외·복구 경로를, Workspace Issue는
  `workspace/issue/archived/YYYY/MM/` 파일명·Frontmatter occurrence·유사 이력 탐색을 함께 검증한다.
- 프로젝트 한정 값 대신 검증된 설치 로컬 설정과 조직 중립적 안전 기본값 사용

## Gates

- 관련 테스트와 Validator 통과
- 사용자 Scope 밖 변경 없음
- 운영 Issue 기반 변경이면 사용자 review receipt와 Triage 결과 존재
- 재현 테스트 또는 재현 불가 사유 존재

## Output

- 변경 파일과 검증 결과
- release note 후보, 호환성 영향과 연결된 Issue

## Failure State

변경을 완료·발행하지 않고 실패 원인, 재현 방법과 남은 Gate를 기록한다.

## Prohibited

- 사용자 승인 없는 Commit·push·외부 발행
- 운영 Issue 수집·검토·Triage 생략
- 제품 변경 완료만으로 운영 Issue를 `verified` 또는 `resolved` 처리
- 설치별 비밀값·PII·머신 절대 경로 하드코딩
