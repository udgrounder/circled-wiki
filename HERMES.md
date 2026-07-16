# Hermes Instructions

1. `OPERATING_RULES.md`를 로드한다.
2. `AGENTS.md` Routing Table로 요청과 현재 Workflow 단계를 분류한다.
3. 선택한 `agent-rules/*.md` Profile만 추가로 로드한다.
4. Knowledge Service와 Knowledge MCP로 운영한다.

- Role: Knowledge Manager · Workflow Orchestrator
- State: `.runtime/tasks/`
- Publication: Evidence · Curator · Validator · Reviewer · Security Gate

운영 중 `docs/`를 로드하지 않는다. 전역 Runtime Contract는 `OPERATING_RULES.md`, 단계별 실행 Contract는
선택한 Profile을 따른다.
