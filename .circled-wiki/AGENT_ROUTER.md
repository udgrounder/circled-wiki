# Circled Wiki Runtime Agent Router

설치된 Wiki의 Agent는 `.circled-wiki/OPERATING_RULES.md`를 먼저 읽고 요청에 맞는 Runtime Profile만 선택한다.
이 Router는 Wiki 콘텐츠와 Runtime 관찰·검증을 위한 것이며 제품 source repository를 변경하거나 release를
배포할 권한을 부여하지 않는다.

## Routing Table

| 요청 또는 현재 상태 | 필수 Runtime Profile |
| --- | --- |
| 지식 조회·질문 답변 | `agent-rules/knowledge-query.md` |
| 사용자 업무 Runbook 실행 | `agent-rules/workflow-execution.md` |
| 대화·파일을 Inbox에 넣기 | `agent-rules/inbox-capture.md` — 수집 Agent·Adapter 구분 없이 공통 민감정보 사전 점검을 먼저 실행 |
| Inbox 항목 검사·승인 | `agent-rules/inbox-inspection.md` |
| 승인된 Inbox를 Evidence로 변환 | `agent-rules/evidence-ingest.md` |
| Evidence 정제·Bundle 초안 또는 갱신 | `agent-rules/knowledge-curation.md` |
| Bundle 파일명·Frontmatter ID 정규화 | `agent-rules/publication.md` — 아래 Bundle Identity Contract와 전체 Validator를 먼저 적용 |
| 검토·발행·Commit | `agent-rules/publication.md` |
| 오류·비정상 결과·개선 기회 기록 | `agent-rules/system-observation.md` |
| 배포 후 설치본 독립 검증 | `agent-rules/runtime-upgrade-verification.md` |
| Circled Wiki OS version 준비·배포·rollback | Runtime mutation 금지. 제품 source repository의 `AGENTS.md`에서 `release-preparation` 또는 `deployment-coordination`으로 전환 |

라우팅이 모호하면 mutation을 시작하지 않고 목적과 기대 출력을 확인한다. Profile 전환 시 이전 단계의
출력과 Gate를 확인하며, 운영 이슈 기록이 제품 수정 또는 upgrade 권한을 만들지 않는다.

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
