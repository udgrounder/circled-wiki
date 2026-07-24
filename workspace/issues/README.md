# Issues

`workspace/issues/`는 운영 문제와 제품 개선 검토를 위한 단일 기준 경로다. 루트의 Issue는 Runtime 운영
피드백이고, 사용자가 명시적으로 수집한 제품 개선 작업은 `inbox/`와 `archived/`에서 관리한다.

## Lifecycle

1. `product-agent-rules/operational-issue-intake.md`의 Gate를 통과한 Git 추적·커밋 Issue만
   `inbox/<project-ref>/`로 원자적으로 이동한다.
2. Archive 유사 이력과 과거 해결·회귀 테스트·검증 결과를 조회한 뒤 사용자 review receipt를 기록한다.
3. 승인된 항목만 Triage와 제품 개선으로 진행한다.
4. 최종 disposition과 필요한 release·deployment·verification receipt가 연결되면
   `archived/YYYY/MM/YYYYMMDDTHHMMSSZ-<canonical-issue-key>-vNNNN.md`로 이동한다.

Inbox와 Archive에 같은 Workspace Issue를 동시에 두거나 기존 Archive 파일을 덮어쓰지 않는다. 발생 번호는 파일명과
Frontmatter에 보존하며, 이동 전 운영 Issue는 원본 프로젝트 Git 이력에서 확인·복구한다.
