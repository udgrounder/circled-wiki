# Deployment Coordination Profile

## Trigger

승인된 release를 명시적인 설치본에 배포할 계획을 세우거나 적용한다.

## Input

- 검증된 release ID와 대상 프로젝트
- 현재 release, preflight, maintenance window와 rollback 책임자

## Allowed Actions

- 대상별 upgrade dry-run
- 충돌·proposal·backup 필요성 평가
- 승인 후 Bootstrap upgrade와 Deployment Receipt 기록

## Checks

- 이전/새 release, backup, applied·preserved·proposed action
- post-upgrade Runtime 검증 요청

## Gates

- 대상·승인·release가 명확할 것
- backup 성공과 proposal 결정 완료
- `knowledge/`와 `workspace/` action이 없을 것

## Output

- Deployment Receipt와 Verification 요청
- 적용·보존·proposal·실패·rollback 상태

## Failure State

실패 receipt와 rollback 조건을 남기고 해결을 주장하지 않는다.

## Prohibited

- 대상 추정, backup 없는 변경
- Runtime 독립 검증 생략
- 사용자 자료를 배포 자산으로 취급
