# Claude Instructions

1. `OPERATING_RULES.md`를 로드한다.
2. `AGENTS.md` Routing Table로 사용자 요청과 현재 단계를 분류한다.
3. 선택한 `agent-rules/*.md` Profile만 추가로 로드한다.
4. 사용자 요청을 처리한다.

Runtime Operation에서는 `docs/`를 로드하지 않는다. Repository Engineering에 필요한 구현 상세만
`OPERATING_RULES.md`의 Reference Traceability에서 선택한다.

Execution, Security, Publication Contract는 `OPERATING_RULES.md`를 따르며 단계별 Check와 Gate는 선택한
Profile을 따른다.
