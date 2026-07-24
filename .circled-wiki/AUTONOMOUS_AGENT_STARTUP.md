# Autonomous Agent Startup

이 파일은 설치된 단일 머신에서 Circled Wiki를 운영하는 자율형 Agent의 초기 기동 계약이다. 시작 프롬프트에는
"프로젝트 root의 `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`를 먼저 읽고 따르라"고 지정한다.

## Startup Sequence

1. `.circled-wiki/config.yaml`을 읽어 조직 ID, 운영 Agent, Graphify 사용 여부, Curation 활성화 여부와 `approval.knowledge_owner`를 확인한다.
2. `.circled-wiki/OPERATING_RULES.md`를 읽는다.
3. `.circled-wiki/AGENT_ROUTER.md` Routing Table로 요청을 분류하고 해당
   `.circled-wiki/agent-rules/*.md` 하나만 읽는다.
4. `python3 .circled-wiki/bin/circled-wiki.py operational-preflight`를 실행한다.
5. 질문 처리에는 Knowledge MCP 또는 portable CLI의 `search`, `read-bundle`, `prepare_context`를 사용한다.
   직접 `find`, `grep`, `rg` 탐색은 이 공식 경로가 실패하거나 결과가 불충분할 때 작업을 계속하기 위한 최후 수단으로
   허용한다. 먼저 `system-observation` Profile의 `record-system-issue`로 문제를 남기고, fallback 사유와 사용한
   범위를 기록한다.
6. 운영 변경이 필요한 경우에만 operator MCP를 사용하며, 단계별 Profile과 Gate를 분리한다.

Preflight가 실패하면 지식 파일을 직접 우회 수정하지 않는다. 실패 원인을
`record-system-issue`로 기록하고 Runtime 복구 또는 OS upgrade를 요청한다.

## Single-machine Operating Model

- 이 설치는 신뢰된 단일 운영 Agent 프로세스를 기본으로 한다.
- 사용자 질의 소비자는 read-only MCP를 사용하고, 운영 Agent만 operator MCP를 사용한다.
- 사용자가 Obsidian에서 보는 내용은 참고용이다. 공식 지식 변경은 Agent가 Inbox → Evidence → Bundle → Validator →
  Publication Gate 순서로 수행한다.
- 자율형 Agent라도 승인자를 사칭하거나 스스로 사람 Approval을 기록하지 않는다.
- Curation은 `materialize_curation_candidate`의 typed 결과 경계로만 Draft를 만들며, Evidence·Bundle frontmatter를 직접 편집하지 않는다.
- 하위 Agent는 읽기 전용 문맥만 `prepare_context`로 받고, operator 권한·작업 범위·기간이 명시적으로 위임된 경우에만 변경 Tool을 쓴다.
- `approved` Draft의 Active 승격은 설정된 `approval.knowledge_owner`만 `promote_curation_candidate`로 실행하며, 독립된 Security receipt가 필요하다.
- `knowledge/`는 공식 지식의 Source of Truth다. `workspace/`는 Agent 기록·Issue·백업을 위한 사용자 소유
  Working Plane이며 공식 지식이 아니다. 둘 다 OS upgrade가 수정하지 않는다.

## Answer Contract

1. `search_knowledge`로 후보를 찾는다.
2. 답변에 사용할 Bundle은 `read_bundle`로 전문과 Evidence source를 확인한다.
3. 중요 주장은 `verified`, `limited`, `inferred`, `needs_review` 중 하나로 구분한다.
4. `verified`는 접근 가능한 원본 Evidence가 있을 때만 사용한다.
5. 관련 공식 Bundle이 없으면 조직의 공식 답을 추정하지 말고 근거 부족을 알린다.

## Graphify Boundary

Graphify는 별도 설치하는 선택적 파생 인덱스다. `.circled-wiki/config.yaml`의 `graphify.enabled`가 `true`이고
설정된 command와 graph 파일이 실제로 존재할 때만 사용한다. 활성화된 Graphify가 준비되지 않으면 preflight를
통과한 것으로 주장하지 않는다.

- Graphify는 관계 탐색, 후보 문서 발견, 경로 분석에 사용할 수 있다.
- Graphify 결과만으로 정책·사실·승인 상태를 확정하지 않는다.
- Graphify 후보는 반드시 Knowledge MCP의 `read_bundle`과 Evidence source로 다시 검증한다.
- graph 파일, cache, query log를 Bundle 또는 Evidence로 ingest하지 않는다.
- 기본 `source_paths`는 `knowledge/bundles`만 사용하고 Inbox·raw·runtime·Evidence 원본은 인덱싱하지 않는다.
- API key나 토큰은 프로젝트 설정·문서·graph output에 저장하지 않는다.
- Graphify가 없거나 실패해도 Knowledge MCP/CLI의 공식 조회 흐름은 계속 사용할 수 있어야 한다.

Graphify 설치와 MCP 등록은 `.circled-wiki/GRAPHIFY.md`를 따른다. Circled Wiki bootstrap은 Graphify 패키지나
외부 자격증명을 설치하지 않는다.

## Shutdown and Recovery

- 변경을 발행하기 전에 `validate`를 통과한다.
- 자동 Git commit은 보안 Gate와 staged 변경 검사를 통과한 `knowledge/` 변경에만 사용한다.
- Push 권한이 있어도 Commit 이후의 Push는 별도 승인된 실행 경로와 remote/branch 검증이 구현되기 전에는 실행하지 않는다.
- 실패·검토 필요 원본은 `.raw/` 또는 Inbox에 보존하고 원인을 기록한다.
- 종료 전 미완료 Runtime Task와 pending Inbox 상태를 사용자에게 요약한다.
