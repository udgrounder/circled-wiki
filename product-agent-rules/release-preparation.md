# Release Preparation Profile

## Trigger

검토된 제품 변경을 설치 가능한 Circled Wiki release 후보로 묶는다.

## Input

- 변경 revision, 포함 Issue와 관련 테스트 결과
- Runtime·schema·config migration 영향

## Allowed Actions

- release ID, manifest와 관리 자산 checksum 생성
- Runtime 패키징, release note와 rollback 조건 작성
- 격리 설치 dry-run·apply 검증

## Checks

- Runtime Router checksum과 Runtime Profile 목록
- 포함 Issue, 호환성, migration과 rollback 정보

## Gates

- 테스트와 Validator 통과
- Product Profile, `knowledge/`, `workspace/`, 설치 config가 release 자산에 없을 것
- manifest와 Runtime checksum 일치

## Output

- immutable release ID와 Release Receipt
- 설치 자산, 호환성·rollback 정보와 독립 검증 결과

## Failure State

release를 발행하지 않고 혼입 자산·검증 실패를 보고한다.

## Prohibited

- Product Profile 또는 사용자 소유 Plane 패키징
- 검증되지 않은 release 배포 요청
- 제품 release 생성만으로 Issue 해결 처리
