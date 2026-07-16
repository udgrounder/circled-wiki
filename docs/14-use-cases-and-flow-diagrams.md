# 유즈케이스 및 플로우 다이어그램

## 1. 목적

이 문서는 `AI Knowledge Operating System`의 대표 유즈케이스와 핵심 운영 흐름을 Mermaid 다이어그램으로 정리한다.

아래 다이어그램은 `docs/02-architecture.md`, `docs/05-hermes-architecture.md`, `docs/06-knowledge-service.md`, `docs/07-mcp-spec.md`, `docs/08-sync-pipeline.md`, `docs/12-runtime-architecture.md`를 시각적으로 요약한 것이다.

## 2. 주요 액터

- 사람 편집자: Obsidian에서 공식 지식을 읽고 수정한다.
- 운영자: CLI 또는 관리 스크립트로 수동 실행과 점검을 수행한다.
- 외부 시스템: Notion, Slack, GitHub, Jira, Meetings 같은 입력 소스다.
- Worker: 스케줄, 수동 트리거, 유지보수 작업을 실행한다.
- Hermes: 회사 전용 지식 라이브러리의 운영자이자 이용자다. Collector, Curator, Reviewer, Index Manager, Delegator 역할로 외부 정보를 축적·정제하고, 사용자 요청 시 직접 라이브러리를 검색·활용하거나 다른 AI Agent가 MCP 또는 CLI로 이용하도록 한다.
- Knowledge Service: 저장소, 검색, 검증, Context Package 생성을 제공한다.
- Knowledge MCP: 외부 AI Agent용 인터페이스를 제공한다.
- AI Agent: Codex, Claude Code, Gemini 같은 소비자다.

## 3. 시스템 유즈케이스

```mermaid
flowchart LR
    editor["사람 편집자"] --> uc1["공식 Bundle 읽기/수정"]
    operator["운영자"] --> uc2["수동 ingest 실행"]
    operator --> uc3["수동 validate / reindex 실행"]
    external["외부 시스템"] --> uc4["신규/변경 입력 제공"]
    worker["Worker"] --> uc5["스케줄 수집 실행"]
    worker --> uc6["유지보수 작업 실행"]
    agent["AI Agent"] --> uc7["지식 검색"]
    agent --> uc8["Context Package 요청"]
    agent --> uc9["Bundle 전문 조회"]
    agent --> uc10["수정안 제안"]
    hermes["Hermes"] --> uc11["Evidence를 Bundle로 정제"]
    hermes --> uc12["리뷰 요청 Bundle 점검"]
    hermes --> uc13["검색 인덱스 갱신"]

    uc1 --> repo["Knowledge Repository"]
    uc2 --> repo
    uc3 --> repo
    uc4 --> repo
    uc5 --> repo
    uc6 --> repo
    uc7 --> mcp["Knowledge MCP"]
    uc8 --> mcp
    uc9 --> mcp
    uc10 --> mcp
    mcp --> service["Knowledge Service"]
    service --> repo
    hermes --> service
    hermes --> uc14[사용자 요청에 지식 라이브러리 활용]
    uc14 --> mcp
```

## 4. 신규 지식 수집 유즈케이스

```mermaid
flowchart TD
    ext["외부 시스템 또는 수기 업로드"] --> inbox["knowledge/inbox/"]
    inbox --> raw["knowledge/.raw/"]
    raw --> assign["source_uuid 발급 및 source_ref 기록"]
    assign --> evidence["Evidence 원본 + manifest 생성"]
    evidence --> curator["Hermes Curator"]
    curator --> decision{"기존 Bundle 매칭 가능?"}
    decision -->|예| update["기존 Bundle 갱신안 작성"]
    decision -->|아니오, 명확함| create["신규 Bundle 작성"]
    decision -->|애매함| review["needs_review / 사람 검토 큐"]
    update --> validate["OKF / Profile Validator"]
    create --> validate
    validate -->|통과| publish["자동 Commit 가능 상태"]
    validate -->|실패| fail["Commit 금지 / 재검토"]
    publish --> reindex["Index Manager 갱신"]
```

## 5. AI Agent 조회 유즈케이스

```mermaid
flowchart LR
    agent["AI Agent"] --> tool["search_knowledge / read_bundle / prepare_context"]
    tool --> mcp["Knowledge MCP"]
    mcp --> service["Knowledge Service"]
    service --> search["Search Orchestrator"]
    service --> repo["Repository Adapter"]
    service --> parser["Parser / Validator"]
    search --> files["Bundles / Evidence manifest / Policies / Templates / Schemas"]
    repo --> files
    parser --> files
    service --> response["Bundle 중심 결과 / Context Package"]
    response --> mcp
    mcp --> agent
```

## 6. 운영 시퀀스: 스케줄 수집

```mermaid
sequenceDiagram
    participant Scheduler as Scheduler
    participant Worker as Worker
    participant Collector as Hermes Collector
    participant Service as Knowledge Service
    participant Repo as Knowledge Repository
    participant Curator as Hermes Curator
    participant Reviewer as Hermes Reviewer
    participant Index as Index Manager

    Scheduler->>Worker: provider 폴링 주기 도달
    Worker->>Collector: 수집 작업 시작
    Collector->>Service: 신규/변경 입력 정규화 요청
    Service->>Repo: inbox/.raw/evidence 기록
    Worker->>Curator: Evidence 기반 큐레이션 실행
    Curator->>Service: 관련 Bundle 검색 및 수정안 작성
    Service->>Repo: Bundle 초안 저장
    Worker->>Reviewer: 검증/충돌 점검
    Reviewer->>Service: OKF/Profile 검증 요청
    Service-->>Reviewer: 통과 또는 실패 결과
    Reviewer-->>Worker: publish 가능 여부 반환
    Worker->>Index: 인덱스 갱신 요청
    Index->>Service: rebuild_indexes(scope)
```

## 7. 운영 시퀀스: Agent 조회

```mermaid
sequenceDiagram
    participant Agent as AI Agent
    participant MCP as Knowledge MCP
    participant Service as Knowledge Service
    participant Search as Search Orchestrator
    participant Repo as Repository Adapter

    Agent->>MCP: search_knowledge(query, filters)
    MCP->>Service: search_knowledge(query, filters)
    Service->>Search: 검색 실행
    Search->>Repo: 대상 문서 로드
    Repo-->>Search: Bundle / Evidence manifest / 정책 문서
    Search-->>Service: 정규화된 결과
    Service-->>MCP: 출처 포함 Bundle 중심 결과
    MCP-->>Agent: 검색 결과 반환

    Agent->>MCP: prepare_context(task, references)
    MCP->>Service: prepare_context(task, references)
    Service->>Repo: 관련 Bundle / Evidence 로드
    Repo-->>Service: 문서 본문 및 frontmatter
    Service-->>MCP: Context Package
    MCP-->>Agent: 작업용 문맥 반환
```

## 8. 운영 시퀀스: review_requested 처리

```mermaid
sequenceDiagram
    participant Human as 사람 또는 Agent
    participant Repo as Bundle 문서
    participant Scheduler as Scheduler
    participant Worker as Worker
    participant Reviewer as Hermes Reviewer
    participant Service as Knowledge Service

    Human->>Repo: review_requested=true 기록
    Scheduler->>Worker: 유지보수 스케줄 실행
    Worker->>Reviewer: review_requested Bundle 점검 요청
    Reviewer->>Service: 대상 Bundle 조회
    Service-->>Reviewer: Bundle + Evidence + 상태 정보
    Reviewer-->>Worker: 검토 큐 등록 또는 수정 권고
    Worker-->>Human: 사람 검토 필요 상태 알림
```

## 9. 해석 포인트

- MVP 기본 경로는 `스케줄 폴링 + 수동 트리거`다.
- 실시간 webhook과 파일 watcher는 현재 기본 경로가 아니다.
- Knowledge MCP는 직접 OS 명령을 고르지 않고 Knowledge Service를 호출한다.
- Bundle 생성/갱신은 항상 Evidence 기반이며, 검증 통과 전에는 publish되지 않는다.
- `review_requested`는 문서 나이와 무관한 정확성 의심 신호다.

## 10. Workflow 실행과 지식 환류

```mermaid
flowchart TD
    request["사용자 작업 요청"] --> find["find_workflow"]
    find --> choose{"Workflow 선택 가능?"}
    choose -->|아니오| clarify["목적 확인 / 사람 선택"]
    clarify --> find
    choose -->|예| freshness{"Runbook 유효?"}
    freshness -->|예| prepare["prepare_task"]
    freshness -->|아니오| refresh["prepare_runbook_refresh"]
    refresh --> reviewed["최신 Evidence 비교 / 독립 Agent 검증 / Owner 승인 / revision 발행"]
    reviewed --> prepare
    prepare --> missing{"필수 입력 누락?"}
    missing -->|예| ask["누락 입력만 질문"]
    ask --> prepare
    missing -->|아니오| execute["Hermes / 사람 / 하위 Agent 실행"]
    execute --> approval{"사람 승인 지점?"}
    approval -->|예| human["승인 또는 반려"]
    human --> execute
    approval -->|아니오| validate["완료 기준 검증"]
    validate --> outcome["record_outcome"]
    outcome --> evidence["Workflow Outcome Evidence"]
    evidence --> signal{"Learning Trigger?"}
    signal -->|아니오| accumulate["Outcome Evidence 누적"]
    signal -->|예| curator["개선 Refresh Task"]
    curator --> bundle["Runbook / Guide / Decision 개선 후보"]
```

실행 중 상태는 `.runtime/tasks/`에 두고, 재사용 가치가 있는 결과만 Evidence와 Bundle 흐름으로
되돌린다. 상세 규칙은 [16-workflow-execution.md](16-workflow-execution.md)를 따른다.
