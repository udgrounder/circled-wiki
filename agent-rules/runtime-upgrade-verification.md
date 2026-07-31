# Runtime Upgrade Verification Profile

## Trigger

Deployment Operator가 upgrade를 완료한 뒤 실제 설치본의 독립 검증을 요청한다.

## Input

- 기대 release ID와 Deployment Receipt
- upgrade 전 config semantic checksum
- 관련 운영 Issue와 안전한 재현 시나리오
- 구현자와 다른 검증 actor

## Allowed Actions

- `validate`와 관련 재현 시나리오 실행
- 기대 release, Deployment Receipt, config·namespace 보존 확인
- `knowledge/`, `workspace/` sentinel과 file tree 보존 확인
- Verification Receipt와 운영 Issue 검증 이력 기록

## Checks

- 실행 release와 Deployment Receipt, 적용·보존·proposal 결과
- config semantic checksum, organization ID와 사용자 Plane 보존
- 관련 증상의 재현 여부

## Gates

- 기대 release와 실제 release 일치
- Deployment Receipt의 적용·보존·proposal 결과가 승인된 배포 계획과 일치
- config, `knowledge/`, `workspace/`의 예상하지 않은 변경 없음
- 재현 시나리오 통과
- 구현자와 검증 actor가 다름

## Output

- Verification Receipt
- `verified` 전환 가능 여부와 실패 시 rollback·Triage 조건

## Failure State

Issue를 해결 처리하지 않고 실패 근거와 안전한 rollback 또는 재검토 조건을 남긴다.

## Prohibited

- Deployment Receipt 없는 검증
- source test만으로 운영 해결 주장
- self-verification
- 사용자 소유 파일 수정
