# AGENTS

## Bootstrap

1. `OPERATING_RULES.md`
2. 사용자 요청을 아래 Routing Table로 분류한다.
3. 선택한 작업의 `agent-rules/*.md`만 추가로 읽는다.
4. 한 요청이 여러 작업을 포함하면 실제 수행 순서대로 Profile을 전환하고, 각 단계의 Gate를 따로 적용한다.

Runtime Operation에서는 `docs/`를 읽지 않는다. Repository Engineering에서 구현 상세가 필요한 경우에만
`OPERATING_RULES.md`의 Reference Traceability를 사용한다.

## Routing Table

| 요청 또는 현재 상태 | 필수 Profile |
| --- | --- |
| 코드·스키마·테스트·운영 문서 변경 | `agent-rules/repository-engineering.md` |
| 지정 폴더에 운영 OS 설치·안전 업그레이드 | `agent-rules/bootstrap-knowledge-os.md` |
| 지식 조회·질문 답변 | `agent-rules/knowledge-query.md` |
| 사용자 업무 Runbook 실행 | `agent-rules/workflow-execution.md` |
| 대화·파일을 Inbox에 넣기 | `agent-rules/inbox-capture.md` |
| Inbox 항목 검사·승인 | `agent-rules/inbox-inspection.md` |
| 승인된 Inbox를 Evidence로 변환 | `agent-rules/evidence-ingest.md` |
| Evidence 정제·Bundle 초안 또는 갱신 | `agent-rules/knowledge-curation.md` |
| 검토·발행·Commit | `agent-rules/publication.md` |

라우팅이 모호하면 변경 작업을 시작하지 말고 작업의 목적과 기대 출력으로 Profile을 확정한다. 단순히 다음
단계가 가능하다는 이유만으로 Profile을 자동 전환하지 않는다.

## Rule Loading

- `OPERATING_RULES.md`는 모든 작업에 적용되는 전역 불변식과 우선순위다.
- `agent-rules/*.md`는 해당 작업에서만 적용하는 입력·Check·Gate·출력·실패 처리다.
- Profile은 전역 규칙을 완화하거나 다른 Profile의 권한을 가져올 수 없다.
- 현재 Profile에 없는 검사와 전체 테스트를 관성적으로 실행하지 않는다.
- Profile 전환 시 이전 단계의 출력과 Gate 통과 여부를 확인한다.

Profile 목록과 공통 형식은 `agent-rules/README.md`를 따른다.
