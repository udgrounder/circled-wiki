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
- 기존 Control Plane 백업과 설치·upgrade Issue 분류 생성

## Checks

- manifest, 이전 checksum, Runtime Profile allowlist와 Router
- manifest의 미해결 Control Plane proposal·미기록 파일 Issue와 Agent 진입점·launcher smoke check
- `knowledge/`, `workspace/`, config와 root Agent 파일의 보존
- preflight, validate와 backup 결과

## Gates

- 기존 OS 변경 전 Control Plane 백업 성공
- Product Profile이 Runtime package에 없을 것
- `knowledge/`와 `workspace/`에 upgrade action이 없을 것
- 사용자 수정 관리 파일과 미기록 Control Plane 파일은 backup을 기준으로 설치·upgrade Issue를 분류하고 해결 전 배포하지 않을 것

## Output

- 설치·upgrade 계획과 적용 보고서
- release, backup, 보존·proposal·설치/upgrade Issue 상태
- 후속 Runtime 검증 요청

## Failure State

기존 사용자 자료를 변경하지 않고 원인과 안전한 재개 조건을 보고한다.

## Prohibited

- `knowledge/`, `workspace/` 또는 기존 root Agent 지침 덮어쓰기
- Product Profile 배포
- backup 실패 후 upgrade 계속 진행
- 사용자 승인 없는 legacy Issue 이동
