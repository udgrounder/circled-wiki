# Claude Product Instructions

1. `PRODUCT_ENGINEERING_RULES.md`를 로드한다.
2. `AGENTS.md` Routing Table로 제품 작업을 분류한다.
3. 선택한 `product-agent-rules/*.md` Profile만 추가로 로드한다.
4. 설치본 Runtime 작업은 대상의 `.circled-wiki/AGENT_ROUTER.md`로 별도 라우팅한다.

제품 변경, 설치, 운영 Issue intake·triage, release와 deployment의 Gate를 합치지 않는다.
