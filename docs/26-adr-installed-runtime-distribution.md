# ADR-001: Circled Wiki Installed Runtime Distribution

**Status:** Accepted — 2026-07-22

## Decision

운영본은 원본 저장소의 직접 fork가 아니라 공식 Circled Wiki 설치·upgrade 배포본으로 운영한다. 설치 대상의
`.circled-wiki/`는 Control Plane이며, `knowledge/`와 Inbox/Evidence/Bundle은 설치·upgrade가 직접 덮어쓰지 않는
Data Plane이다.

## Consequences

- upgrade 전 `operational-preflight`, manifest/runtime checksum, namespace/config semantic checksum을 확인한다.
- upgrade는 `.circled-wiki-backups/`에 Control Plane snapshot을 만든 뒤에만 적용한다.
- config migration 또는 runtime validation 실패 시 새 Runtime을 시작하지 않고 직전 Control Plane snapshot으로 복구한다.
- `knowledge/` Data Plane, 원본 Evidence, 운영 이슈, `.runtime/` 상태는 Control Plane rollback으로 삭제·덮어쓰지 않는다.
- 운영본에서 변경된 사용자 관리 파일은 proposal 또는 preserve-existing 처리하며 자동 덮어쓰지 않는다.

## Rejected alternative

공식 운영 fork를 canonical Runtime으로 삼지 않는다. fork 방식은 사용자 수정과 제품 배포 변경의 provenance를 섞고,
단일 설치 머신 Agent의 upgrade/rollback 책임을 불명확하게 만든다.

## Verification required before each upgrade

1. 현재 `organization.id`와 effective config semantic checksum을 기록한다.
2. manifest가 가리키는 runtime checksum과 preflight 결과를 기록한다.
3. upgrade 후 같은 namespace, config 의미, Validator 결과 및 canonical Runtime 단일성을 확인한다.
4. 실패 시 backup receipt, 실패 단계, rollback 결과를 운영 이슈에 기록한다.
