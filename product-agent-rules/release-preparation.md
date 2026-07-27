# Release Preparation Profile

## Trigger

검토된 제품 변경을 설치 가능한 Circled Wiki release 후보로 묶는다.

## Input

- 변경 revision, 포함 Issue와 관련 테스트 결과
- Runtime·schema·config migration 영향
- clean source revision 또는 명시적으로 기록된 source snapshot

## Allowed Actions

- 대상 설치본과 독립된 release manifest·release ID·관리 자산 checksum 생성
- Runtime 패키징, release note와 rollback 조건 작성
- 격리 설치 dry-run·apply 검증

## Checks

- Runtime Router checksum과 Runtime Profile 목록
- 포함 Issue, 호환성, migration과 rollback 정보
- source revision, release manifest와 receipt의 asset checksum이 동일한지

## Gates

- 테스트와 Validator 통과
- Product Profile, `knowledge/`, `workspace/`, 설치 config가 release 자산에 없을 것
- manifest와 Runtime checksum 일치
- release manifest와 Release Receipt를 **대상 배포 전에** immutable하게 기록할 것
- release ID는 제품 release asset map만으로 계산할 것. 대상별 preserve·proposal·backup 결과를 release asset map에 섞지 말 것
- source revision이 재현 가능할 것. uncommitted 작업 트리는 기본적으로 release 준비를 차단하며, 예외는 revision·diff checksum·승인 사유를 release note에 함께 기록할 것

## Output

- immutable release ID, release manifest와 Release Receipt (대상 설치본과 무관한 Product artifact)
- 설치 자산, 호환성·rollback 정보와 독립 검증 결과

## Failure State

release를 발행하지 않고 혼입 자산·검증 실패를 보고한다.

## Prohibited

- Product Profile 또는 사용자 소유 Plane 패키징
- 검증되지 않은 release 배포 요청
- 대상 설치본 manifest를 release manifest로 사용하거나, 배포 후에만 Release Receipt를 만드는 행위
- 제품 release 생성만으로 Issue 해결 처리
