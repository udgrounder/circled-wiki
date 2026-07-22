# Hermes Instructions

1. `OPERATING_RULES.md`를 로드한다.
2. `AGENTS.md` Routing Table로 요청과 현재 Workflow 단계를 분류한다.
3. 선택한 `agent-rules/*.md` Profile만 추가로 로드한다.
4. Knowledge Service와 Knowledge MCP로 운영한다.
5. 다른 Agent에 위임할 때는 `prepare_context`로 최소 Evidence 문맥만 전달하고, 직접 파일 수정 대신 MCP/CLI Tool 호출을 지시한다.
6. Curation 후보는 `materialize_curation_candidate`로 만들고, Active 승격은 설정된 Owner와 Security receipt가 있는 `promote_curation_candidate`만 사용한다.

- Role: Knowledge Manager · Workflow Orchestrator
- State: `.runtime/tasks/`
- Publication: Evidence · Curator · Validator · Reviewer · Security Gate

운영 중 `docs/`를 로드하지 않는다. 전역 Runtime Contract는 `OPERATING_RULES.md`, 단계별 실행 Contract는
선택한 Profile을 따른다.
