# Circled Wiki Runtime Agent Router

설치된 Wiki의 Agent는 `.circled-wiki/OPERATING_RULES.md`를 먼저 읽고 요청에 맞는 Runtime Profile만 선택한다.
이 Router는 Wiki 콘텐츠와 Runtime 관찰·검증을 위한 것이며 제품 source repository를 변경하거나 release를
배포할 권한을 부여하지 않는다.

Vault 구조·domain·provider·운영 흐름을 관리하거나 변경하는 작업은 선택한 Profile에 앞서
`knowledge/README.md`를 읽는다. 단일 Inbox 입력의 검사·변환처럼 경로나 운영 방식을 바꾸지 않는 작업에는
이 추가 읽기를 요구하지 않는다.

## Routing Table

| 요청 또는 현재 상태 | 필수 Runtime Profile |
| --- | --- |
| 지식 조회·질문 답변 | `agent-rules/knowledge-query.md` |
| 사용자 업무 Runbook 실행 | `agent-rules/workflow-execution.md` |
| 대화·파일을 Inbox에 넣기 | `agent-rules/inbox-capture.md` — 수집 Agent·Adapter 구분 없이 공통 민감정보 사전 점검을 먼저 실행 |
| Inbox 항목 검사·승인 | `agent-rules/inbox-inspection.md` |
| 승인된 Inbox를 Evidence로 변환 | `agent-rules/evidence-ingest.md` |
| Evidence 정제·Bundle 초안 또는 갱신 | `agent-rules/knowledge-curation.md` |
| `manual`·`runbook` 직접 Review 카드 생성 또는 검증 | `agent-rules/knowledge-curation.md` |
| 승인된 `update_existing` Review로 기존 Bundle 보완 적용 | `agent-rules/knowledge-curation.md` |
| Bundle 파일명·Frontmatter ID 규칙 확인 또는 현재 충돌 점검 | 아래 **Bundle Identity Routing**의 1~3단계를 먼저 수행. 변경 전에는 `agent-rules/knowledge-curation.md` |
| 승인된 Bundle 파일명·Frontmatter ID 일괄 정규화 | 아래 **Bundle Identity Routing** 전체와 `agent-rules/publication.md` |
| 검토·발행·Commit | `agent-rules/publication.md` |
| 오류·비정상 결과·개선 기회, 또는 기존 절차로 처리할 수 없는 사용자 의사 판단 사례 기록 | `agent-rules/system-observation.md` |
| 배포 후 설치본 독립 검증 | `agent-rules/runtime-upgrade-verification.md` |
| Circled Wiki OS version 준비·배포·rollback | Runtime mutation 금지. 제품 source repository의 `AGENTS.md`에서 `release-preparation` 또는 `deployment-coordination`으로 전환 |

라우팅이 모호하면 mutation을 시작하지 않고 목적과 기대 출력을 확인한다. Profile 전환 시 이전 단계의
출력과 Gate를 확인하며, 운영 이슈 기록이 제품 수정 또는 upgrade 권한을 만들지 않는다.

## Bundle Identity Routing

Bundle 파일명·Frontmatter `id`·`bundle_uuid`에 관한 요청은 다음 순서를 지킨다. Agent는 규칙을 찾기 위해
Bundle 본문이나 저장소 전체를 **먼저** shell 검색하지 않는다.

1. **규칙 확인** — 이 Router의 Bundle Identity Contract와 `OPERATING_RULES.md`의 **RB-KNW-026**을 먼저 읽는다.
2. **요청 분류** — 규칙 설명·현재 충돌 보고만 요청되었으면 읽기 전용으로 끝내고 `knowledge-curation` Check를 적용한다. 파일명·ID·링크를 실제 변경하는 요청이면 `publication` Profile로 전환한다.
3. **충돌 점검** — `python3 .circled-wiki/bin/circled-wiki.py validate`를 먼저 실행한다. Validator가 충분한 목록을 주지 않을 때만, 이미 확인한 canonical 규칙을 기준으로 `knowledge/bundles/` 범위에 한정해 파일명·`id`·`bundle_uuid`·참조를 비교한다.
4. **Fallback 탐색** — Router·RB-KNW-026이 없거나 서로 모순되거나 요청 해결에 필요한 세부 규칙이 없을 때는 제한된 `rg` 탐색을 허용한다. 먼저 탐색 실패 사유와 범위(예: `.circled-wiki/`, `knowledge/bundles/`)를 밝히고, 규칙을 추정하지 않으며 찾은 정본을 사용자에게 제시한다. 저장소 전체 검색은 이 제한 탐색으로도 해결되지 않을 때만 사용한다.
5. **변경 계획** — 일괄 정규화는 대상 파일, 이전·새 파일명, 이전·새 ID, 유지할 UUID, 영향받는 링크·Workflow·Evidence 참조, rollback 경로를 먼저 제시한다. 승인 전에는 rename·frontmatter 변경을 하지 않는다.
6. **적용·발행** — 승인 후에만 `publication` Gate, 전체 Validator, Evidence 참조 무결성과 Commit 권한을 확인한다.

## Bundle Identity Contract

Bundle 생성·갱신·파일명 변경·일괄 정규화 요청은 전체 파일 검색으로 규칙을 추정하지 않는다. 먼저
`OPERATING_RULES.md`의 **RB-KNW-026**을 읽고 다음 canonical 형식을 사용한다.

```text
파일명: {slug}.md
id: bundle/{organization_id}/{slug}--{bundle_uuid}
bundle_uuid: 최초 생성 시 발급한 전체 UUID (변경하지 않음)
```

`organization_id`는 `.circled-wiki/config.yaml`에서 확인한다. 이전
`{slug}_{bundle_uuid}.md` 형식은 호환 읽기용 legacy 형식일 뿐 신규 생성·정규화의 목표 형식이 아니다.
`title`, `description`, 본문은 현재 사용자와 소통하는 언어를 기본으로 하며, 이를 판단할 수 없으면 한국어를 사용한다.
