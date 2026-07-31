# Deployment Coordination Profile

## Trigger

승인된 release를 명시적인 설치본에 배포할 계획을 세우거나 적용한다.

## Input

- 배포 전에 준비·검증된 release ID, immutable Release Receipt와 release manifest
- 현재 release, upgrade dry-run, maintenance window와 rollback 책임자
- 명시된 대상, 승인과 rollback에 쓸 backup reference

## Allowed Actions

- 대상별 upgrade dry-run
- 충돌·proposal·backup 필요성 평가
- 승인 후 Bootstrap upgrade와 Deployment Receipt 기록
- 명시된 backup으로 rollback 적용과 실패·rollback Deployment Receipt 기록

## Checks

- 이전/새 release, backup, applied·preserved·proposed action
- post-upgrade Runtime 검증 요청
- 대상의 실제 manifest asset map이 승인된 release manifest와 일치하는지
- 대상의 `.circled-wiki/history/releases/<release>.json`이 승인된 release manifest와 일치하는지

## Gates

- 대상·승인·release가 명확할 것
- Release Receipt와 release manifest가 deployment 시작 전에 존재하고 서로 일치할 것
- backup 성공과 proposal 결정 완료
- `knowledge/`와 `workspace/` action이 없을 것
- release manifest와 다른 source asset, 미해결 proposal 또는 target-specific hybrid asset map이면 apply하지 말 것

## Output

- Deployment Receipt와 Verification 요청. Receipt에는 승인된 release manifest·Release Receipt·실제 backup을 참조할 것
- 적용·보존·proposal·실패·rollback 상태

## Failure State

실패 receipt와 rollback 조건을 남기고 해결을 주장하지 않는다.

## Prohibited

- 대상 추정, backup 없는 변경
- 대상 설치 결과로 새 release ID를 만들거나, 배포 후 Release Receipt를 처음 만드는 행위
- Runtime 독립 검증 생략
- 사용자 자료를 배포 자산으로 취급
