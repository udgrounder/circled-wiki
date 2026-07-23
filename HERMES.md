# Hermes Product Instructions

1. `PRODUCT_ENGINEERING_RULES.md`를 로드한다.
2. `AGENTS.md` Routing Table로 제품 작업을 분류한다.
3. 선택한 `product-agent-rules/*.md` Profile만 추가로 로드한다.
4. 운영 설치본에서는 대상의 `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`와
   `.circled-wiki/AGENT_ROUTER.md`를 사용한다.

Product Agent 권한을 설치본 Runtime Agent에 위임하거나 Product Profile을 Runtime release에 포함하지 않는다.
