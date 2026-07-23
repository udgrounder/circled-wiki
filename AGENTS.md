# Circled Wiki Product Agent

## Bootstrap

1. `PRODUCT_ENGINEERING_RULES.md`를 읽는다.
2. 사용자 요청을 아래 Routing Table로 분류한다.
3. 선택한 `product-agent-rules/*.md`만 추가로 읽는다.
4. 운영 설치본을 다룰 때는 제품 작업과 Runtime 작업을 분리하고 각 단계의 Gate를 따로 적용한다.

이 저장소의 Agent는 Circled Wiki 제품을 설계·구현·검증·배포하는 Product Agent다. 설치된 Wiki의 지식 조회,
Inbox 처리와 발행은 이 Router가 직접 수행하지 않으며 설치본의 `.circled-wiki/AGENT_ROUTER.md`를 따른다.

## Routing Table

| 요청 또는 현재 상태 | 필수 Product Profile |
| --- | --- |
| 코드·스키마·테스트·제품 문서 변경 | `product-agent-rules/repository-engineering.md` |
| 지정 폴더에 Circled Wiki 설치·안전 업그레이드 | `product-agent-rules/bootstrap-circled-wiki.md` |
| 운영 프로젝트 Issue를 제품 Workspace로 수집 | `product-agent-rules/operational-issue-intake.md` |
| 수집·검토된 운영 Issue 분류와 개선 작업 연결 | `product-agent-rules/system-issue-triage.md` |
| 검토된 변경을 설치 가능한 release로 준비 | `product-agent-rules/release-preparation.md` |
| 승인된 release 배포 계획·적용·receipt 기록 | `product-agent-rules/deployment-coordination.md` |

라우팅이 모호하면 변경을 시작하지 않고 목적과 기대 출력을 확인한다. 운영 Issue 기반 제품 변경은
`operational-issue-intake -> 사용자 검토 -> system-issue-triage -> repository-engineering` 순서를 건너뛰지 않는다.

## Rule Loading

- `PRODUCT_ENGINEERING_RULES.md`는 제품 작업의 전역 불변식이다.
- `product-agent-rules/*.md`는 선택한 제품 단계의 입력·Check·Gate·출력·실패 처리다.
- 설치본 Runtime 규칙은 `OPERATING_RULES.md`, `.circled-wiki/AGENT_ROUTER.md`, `agent-rules/`가 관리한다.
- Product Profile은 Runtime package에 배포하지 않는다.
- Profile 전환 시 이전 단계의 출력과 Gate 통과 여부를 확인한다.

Profile 공통 형식은 `product-agent-rules/README.md`를 따른다.
