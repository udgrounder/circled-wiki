# Circled Wiki Bootstrap and Upgrade Profile

## Trigger

사용자가 지정한 폴더에 Circled Wiki를 최초 설치하거나 안전하게 업그레이드한다.

## Input

- 명시적인 대상 프로젝트 root
- 설치 또는 upgrade 의도와 설정 입력
- 충돌 제안본에 대한 사용자 결정

## Allowed Actions

- 변경 계획 생성 후 승인된 apply 실행
- `.circled-wiki/` 관리 자산과 신규 설치의 빈 `knowledge/`, `workspace/` root 생성
- 비관리 root Agent 파일에 표시된 Runtime 참조 블록을 한 번만 추가
- 기존 Control Plane 백업과 충돌 proposal 생성

## Checks

- manifest, 이전 checksum, Runtime Profile allowlist와 Router
- manifest에 기록할 미해결 Control Plane proposal과 Agent 진입점·launcher smoke check
- `knowledge/`, `workspace/`, config와 root Agent 파일의 보존
- preflight, validate와 backup 결과

## Gates

- 기존 OS 변경 전 Control Plane 백업 성공
- Product Profile이 Runtime package에 없을 것
- `knowledge/`와 `workspace/`에 upgrade action이 없을 것
- 사용자 수정 관리 파일은 덮어쓰지 않고 proposal로 보존할 것

## Output

- 설치·upgrade 계획과 적용 보고서
- release, backup, 보존·proposal 상태
- 후속 Runtime 검증 요청

## Failure State

기존 사용자 자료를 변경하지 않고 원인과 안전한 재개 조건을 보고한다.

## Prohibited

- `knowledge/`, `workspace/` 또는 기존 root Agent 지침 덮어쓰기
- Product Profile 배포
- backup 실패 후 upgrade 계속 진행
- 사용자 승인 없는 legacy Issue 이동
