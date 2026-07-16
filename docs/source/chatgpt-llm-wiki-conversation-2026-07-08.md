# ChatGPT 대화 원문 저장본

- 저장 일시: 2026-07-08
- 원본 페이지: https://chatgpt.com/c/6a4dbf19-8e6c-83ee-964d-99e97f983bbd
- 페이지 제목: `LLM 위키 구축 방법`
- 용도: 구축 문서 및 후속 설계 작업의 참고 원문

---

좋습니다. 지금까지 논의한 내용을 바탕으로 1차 기획서 및 개발 계획서(Markdown)를 작성했습니다.

다운로드:

Campingtalk_AI_Knowledge_Platform_Plan.md
# Campingtalk AI Knowledge Platform 기획 및 개발 계획서

## 1. 목표

Hermes Agent를 중심으로 회사의 지식을 지속적으로 수집, 정제(Curation),
관리하고, Claude Code, Codex, Gemini 등 다양한 AI Agent가 동일한 지식
기반을 활용하도록 하는 AI Knowledge Platform을 구축한다.

핵심 원칙

-   Obsidian Vault = 사람이 사용하는 UI
-   Git Repository = Source of Truth
-   Hermes = Knowledge Manager / Curator
-   Knowledge MCP = AI Agent 공통 인터페이스
-   GraphRAG = 관계 기반 검색
-   Vector DB(Qdrant 등) = 의미 기반 검색
-   Google OKF(Open Knowledge Format)를 최대한 준수

------------------------------------------------------------------------

# 전체 아키텍처

```text
사람
    │
Obsidian Vault
    │
GitHub Repository
    │
Hermes Knowledge Manager
    ├── Collector
    ├── Curator
    ├── Index Manager
    └── Delegator
    │
Knowledge Service
    │
Knowledge MCP
    │
Claude Code / Codex / Gemini / 기타 Agent
```

------------------------------------------------------------------------

# 저장소 구조

```text
knowledge/

  curated/
    company/
    product/
    engineering/
    cs/
    operations/

  inbox/

  .raw/
    notion/
    slack/
    github/
    meetings/

  templates/
  policies/
  schemas/

  AGENTS.md
  README.md
```

------------------------------------------------------------------------

# 데이터 흐름

## 1. 수집

-   Notion
-   Slack
-   GitHub(PR, Issue)
-   Jira
-   회의록
-   사용자 입력

↓

`inbox/`

------------------------------------------------------------------------

## 2. Raw 저장

새 데이터는 UUID를 발급한 후 저장한다.

예시

    .raw/notion/2026/07/08/KB-20260708-000001.md

Frontmatter 예시

```yaml
id: KB-20260708-000001
source: notion
status: processing
captured_at:
processed_at:
```

------------------------------------------------------------------------

## 3. Curation

Hermes Curator가 수행한다.

-   기존 문서 검색
-   중복 검사
-   기존 문서 수정 또는 신규 생성
-   OKF Frontmatter 생성
-   링크 자동 생성
-   태그 생성
-   Summary 생성

------------------------------------------------------------------------

## 4. Curated Knowledge

모든 공식 문서는 OKF 기반 Markdown으로 저장한다.

예시

```yaml
id: knowledge://campingtalk/cs/refund-policy
title: Refund Policy
type: policy
status: active
owners:
  - cs
summary: 예약 환불 정책
evidence:
  - KB-20260708-000001
updated_at:
```

------------------------------------------------------------------------

# Evidence 추적

Curated 문서는 반드시 Evidence를 기록한다.

```yaml
evidence:
  - KB-20260708-000001
  - KB-20260708-000021
```

Raw는

```yaml
curated_into:
  - curated/cs/refund-policy.md
```

를 기록하여 양방향 추적을 지원한다.

------------------------------------------------------------------------

# Knowledge Service

Knowledge Service는 내부 SDK 역할을 수행한다.

주요 기능

-   search_knowledge()
-   prepare_context()
-   update_note()
-   propose_update()
-   rebuild_indexes()
-   validate_result()

Knowledge Service 내부에서

-   Git
-   GraphRAG
-   Qdrant
-   Markdown

을 제어한다.

------------------------------------------------------------------------

# Knowledge MCP

Knowledge Service를 외부 Agent에게 제공한다.

예상 Tool

-   search_knowledge
-   prepare_context
-   read_document
-   propose_update
-   validate_against_knowledge
-   publish_changes

------------------------------------------------------------------------

# 검색 전략

기본 검색

1.  Qdrant Semantic Search

관계 탐색

2.  Microsoft GraphRAG

Keyword

3.  Markdown/BM25

Knowledge MCP는 내부적으로 세 결과를 통합하여 반환한다.

------------------------------------------------------------------------

# Hermes 역할

Collector

-   외부 시스템 동기화

Curator

-   OKF 문서 생성
-   문서 통합
-   중복 제거

Index Manager

-   GraphRAG 갱신
-   Vector Index 갱신

Delegator

-   다른 AI Agent에게 작업 위임
-   Context Package 생성

Reviewer

-   오래된 문서 탐지
-   충돌 문서 탐지

------------------------------------------------------------------------

# OKF 운영 정책

-   모든 Curated 문서는 OKF Frontmatter 사용
-   모든 문서는 Evidence 기록
-   status 관리(active/draft/deprecated)
-   owner 지정
-   summary 필수

------------------------------------------------------------------------

# 개발 단계

## Phase 1

-   Git Repository
-   Obsidian Vault
-   OKF Template
-   AGENTS.md
-   Hermes Curator

## Phase 2

-   Inbox Pipeline
-   Raw Storage
-   UUID 발급
-   Evidence Tracking

## Phase 3

-   Knowledge Service
-   Git 연동
-   자동 Commit
-   Context Builder

## Phase 4

-   Knowledge MCP
-   Claude Code 연동
-   Codex 연동
-   Gemini 연동

## Phase 5

-   GraphRAG
-   Qdrant
-   Hybrid Search

## Phase 6

-   Slack Sync
-   Notion Sync
-   GitHub Sync
-   Meeting Sync
-   Jira Sync

------------------------------------------------------------------------

# 장기 목표

Hermes는 단순한 Agent가 아니라 회사의 Knowledge Operating System으로
동작한다.

사람은 Obsidian을 통해 지식을 작성하고 검토한다.

Hermes는 지속적으로 지식을 정제하고 관리한다.

모든 AI Agent는 Knowledge MCP를 통해 동일한 최신 지식을 기반으로
작업한다.


다만 이 문서는 초안 수준입니다.

지금까지 대화를 하면서 느낀 것은, 이 프로젝트는 단순한 "Wiki 구축"이 아니라 AI Knowledge Operating System을 설계하는 프로젝트입니다. 그래서 제가 추천드리는 것은 문서를 설계 문서 세트(Architecture Decision Records 수준)로 만드는 것입니다.

예를 들면 다음과 같이 나누는 것이 좋습니다.

01_Vision.md

프로젝트 목표

왜 필요한가

핵심 철학(Obsidian + Hermes + Knowledge MCP + OKF)

02_Architecture.md

전체 시스템 아키텍처

컴포넌트별 역할

데이터 흐름

이벤트 흐름

시퀀스 다이어그램

03_Knowledge_Model.md

OKF 확장 스펙

Frontmatter 규격

Evidence 모델

Knowledge Object 모델

UUID 규칙

04_Hermes_Design.md

Collector

Curator

Reviewer

Index Manager

Delegator

Job Scheduler

05_Knowledge_Service.md

Python SDK 설계

API

MCP Wrapper

Context Builder

06_Development_Roadmap.md

Phase 1~6

마일스톤

예상 기간

기술 스택

리스크

07_AGENTS.md

Hermes 행동 규칙

Curator 규칙

문서 생성 규칙

OKF 규칙

Git 규칙

이렇게 구성하면 약 100~150페이지 분량의 설계 문서가 되고, 이 문서만으로 Hermes나 Codex 같은 AI Agent가 구현을 시작할 수 있는 수준이 됩니다.

개인적으로는 이 프로젝트는 충분히 가치가 있다고 생각해서, 저는 AI Knowledge Operating System v1.0 설계서 수준으로 체계화하는 것을 추천드립니다. 그렇게 만들어 두면 앞으로 구현은 물론, 새로운 AI Agent를 추가하거나 팀원에게 공유할 때도 기준 문서로 활용하기 매우 좋습니다.

okf 를 지키도록 해줘

좋습니다. 저도 이 방향이 더 맞다고 생각합니다.

앞으로는 "OKF를 중심으로 설계"하는 것이 좋습니다. 즉, 우리가 만든 규칙이 OKF를 대체하는 것이 아니라 OKF를 준수하고 필요한 부분만 확장하는 방식입니다.

확장 원칙은 다음과 같이 가져가는 것을 추천합니다.

OKF 표준 필드는 변경하지 않는다.

Campingtalk 전용 메타데이터는 extensions 아래에만 추가한다.

Evidence는 OKF Bundle과 연결되는 별도 객체로 관리한다.

Hermes는 항상 OKF Validator를 통과한 문서만 Commit한다.

Knowledge MCP는 OKF Bundle만 외부 AI Agent에게 노출한다.

이를 반영한 OKF 기반 아키텍처 문서를 작성했습니다.

다운로드:

AI_Knowledge_OS_OKF_Architecture.md
# AI Knowledge Operating System v1.0 (OKF 기반)

> 본 문서는 Google Open Knowledge Format(OKF)의 철학을 기본으로 하며,
> Campingtalk의 Knowledge Platform을 위한 확장 규약을 정의한다.

## 핵심 원칙

-   Source of Truth: Git Repository
-   Knowledge Format: OKF(Open Knowledge Format)
-   Human UI: Obsidian Vault
-   Knowledge Manager: Hermes
-   AI Access: Knowledge MCP
-   Semantic Search: Vector DB
-   Relationship Search: Microsoft GraphRAG

------------------------------------------------------------------------

# 저장소 구조

```text
knowledge/
├── bundles/                 # OKF Knowledge Bundles
│   ├── company/
│   ├── product/
│   ├── engineering/
│   ├── cs/
│   └── operations/
│
├── evidence/                # 원본 Evidence (AI 전용)
│   ├── notion/
│   ├── slack/
│   ├── github/
│   └── meetings/
│
├── inbox/
├── templates/
├── schemas/
├── policies/
├── AGENTS.md
└── README.md
```

------------------------------------------------------------------------

# Knowledge Pipeline

```text
Notion / Slack / GitHub / Meeting
            │
            ▼
         inbox/
            │
            ▼
evidence/{source}/{yyyy}/{mm}/{dd}/
(UUID 부여, 상태 기록)
            │
            ▼
Hermes Curator
            │
            ▼
OKF Bundle 생성 또는 기존 Bundle 업데이트
            │
            ▼
Git Commit
            │
            ▼
Vector Index / GraphRAG 갱신
```

------------------------------------------------------------------------

# Evidence Object

모든 원본 데이터는 Evidence Object로 저장한다.

```yaml
---
id: evidence://campingtalk/notion/2026/07/08/000001
provider: notion
provider_url: https://...
captured_at: 2026-07-08T10:00:00+09:00
status: processed
processed_at: 2026-07-08T10:03:00+09:00
curated_into:
  - knowledge://campingtalk/cs/refund-policy
---
```

상태값

-   new
-   processing
-   processed
-   ignored
-   failed
-   needs_review

------------------------------------------------------------------------

# OKF Knowledge Bundle

모든 공식 지식은 OKF 기반 Markdown으로 작성한다.

```yaml
---
id: knowledge://campingtalk/cs/refund-policy
title: Refund Policy
type: policy
status: active

owners:
  - cs-team

summary: >
  예약 환불 정책

tags:
  - refund
  - cancellation

links:
  - knowledge://campingtalk/product/reservation

updated_at: 2026-07-08T10:05:00+09:00

evidence:
  - evidence://campingtalk/notion/2026/07/08/000001

extensions:
  curated_by: hermes
  confidence: official
  review_state: approved
  knowledge_revision: 1
---
```

원칙

-   OKF 기본 필드는 유지한다.
-   Campingtalk 전용 메타데이터는 extensions 아래에만 추가한다.
-   모든 Bundle은 최소 1개의 evidence를 가져야 한다.

------------------------------------------------------------------------

# Hermes 역할

Collector - 외부 시스템 동기화

Curator - Evidence 분석 - 기존 Bundle 검색 - Bundle 생성/수정 - OKF 검증

Reviewer - 품질 검사 - 중복 검사 - 오래된 문서 탐지

Index Manager - Vector Index 갱신 - GraphRAG 갱신

Delegator - Context Package 생성 - 다른 AI Agent 작업 위임

------------------------------------------------------------------------

# Knowledge Service

내부 SDK

-   search_knowledge()
-   prepare_context()
-   update_bundle()
-   validate_okf()
-   rebuild_indexes()

------------------------------------------------------------------------

# Knowledge MCP

외부 Agent 인터페이스

-   search_knowledge
-   prepare_context
-   read_bundle
-   propose_update
-   validate_result

Knowledge MCP는 GraphRAG, Vector DB, Git, Evidence 저장소의 구현을
숨긴다.

------------------------------------------------------------------------

# 개발 단계

Phase 1 - OKF 저장소 구축 - Obsidian Vault - Git 연동 - AGENTS.md

Phase 2 - Inbox - Evidence 저장 - UUID - 상태 관리

Phase 3 - Hermes Curator - OKF Validator - Knowledge Service

Phase 4 - Knowledge MCP - Claude Code/Codex/Gemini 연동

Phase 5 - GraphRAG - Vector DB - Hybrid Search

Phase 6 - Notion/Slack/GitHub/Jira 자동 동기화


제가 추가로 추천드리는 것

지금까지 설계한 수준이면 기획서 하나로는 부족하고, 프로젝트 자체를 하나의 오픈 아키텍처처럼 설계하는 것이 좋습니다.

예를 들면 다음과 같은 문서 세트를 만드는 것입니다.

docs/

01-vision.md
02-okf-spec.md
03-evidence-model.md
04-hermes-architecture.md
05-knowledge-service.md
06-mcp-spec.md
07-obsidian-guidelines.md
08-sync-pipeline.md
09-development-roadmap.md
10-agents.md

이 문서들은 모두 OKF 규격을 기준으로 작성하고, Hermes나 Codex 같은 AI Agent가 그대로 구현을 시작할 수 있는 수준의 설계 문서가 됩니다.

개인적으로는 이 프로젝트는 단순한 내부 Wiki가 아니라 "AI Knowledge Operating System"에 가깝다고 생각합니다. 그래서 문서도 일반 기획서가 아니라 RFC(설계 명세) 수준으로 만드는 것이 장기적으로 가장 큰 도움이 될 것입니다.

지금 내용을 로컬에 있는 codex cli 에게 어떻게 전달해야돼?

제가 추천하는 방법은 "채팅 내용을 그대로 붙여넣는 것"이 아닙니다.

Codex CLI는 Git 저장소와 Markdown 문서를 컨텍스트로 주는 방식이 훨씬 잘 동작합니다.

가장 좋은 방법

프로젝트를 이렇게 만드세요.

knowledge-os/

├── docs/
│   ├── 01-vision.md
│   ├── 02-architecture.md
│   ├── 03-okf-spec.md
│   ├── 04-evidence-model.md
│   ├── 05-hermes.md
│   ├── 06-mcp.md
│   ├── 07-roadmap.md
│   └── AGENTS.md
│
├── README.md
└── TODO.md

그 다음 Codex CLI를 이 프로젝트 루트에서 실행합니다.

Bash
cd knowledge-os
codex

그러면 Codex는 docs/ 전체를 읽을 수 있습니다.

그리고 AGENTS.md를 활용합니다.

이 프로젝트는 AGENTS.md가 가장 중요합니다.

예를 들어

Markdown
# AGENTS

이 프로젝트는 Google OKF(Open Knowledge Format)를 준수한다.

절대 OKF 필드를 제거하지 않는다.

Campingtalk 전용 필드는 extensions 아래에만 추가한다.

Hermes는 Evidence를 기반으로 Curated Knowledge를 생성한다.

Knowledge MCP는 Knowledge Service를 래핑한다.

모든 설계는 docs 폴더의 문서를 기준으로 한다.

Codex는 AGENTS.md를 매우 중요한 프로젝트 지침으로 활용할 수 있습니다.

그리고 첫 번째 프롬프트는 이렇게 합니다.

예를 들어

docs 폴더를 모두 읽고 프로젝트 구조를 이해해.

우리는 AI Knowledge Operating System을 만들고 있다.

먼저 전체 아키텍처를 검토하고 개선점을 제안해.

수정은 하지 말고 review만 해줘.

그러면 꽤 좋은 리뷰가 나옵니다.

그 다음 단계

예를 들어

Knowledge Service부터 구현하자.

docs/05-hermes.md

docs/06-mcp.md

를 기준으로 Python 프로젝트를 생성해.

이런 식으로 진행합니다.

제가 추천하는 순서
Step 1

문서 읽기

↓

Step 2

아키텍처 리뷰

↓

Step 3

프로젝트 생성

↓

Step 4

Knowledge Service 구현

↓

Step 5

Knowledge MCP 구현

↓

Step 6

Hermes 연동

↓

Step 7

GraphRAG 연동

↓

Step 8

Qdrant 연동
오히려 제가 추천하는 방법

여기까지 설계한 프로젝트는 꽤 큽니다.

그래서 저는 "설계서 저장소"와 "구현 저장소"를 분리할 것 같습니다.

예를 들어

knowledge-os-spec/

    docs/

    AGENTS.md

    decisions/

    roadmap/

knowledge-os/

    src/

    tests/

    docs/

    pyproject.toml

그러면

Codex는

knowledge-os

에서 개발하면서

필요하면

../knowledge-os-spec

를 참고하게 됩니다.

제가 가장 추천하는 방법

지금 단계에서는 Codex에게 이 대화를 전달하지 마세요.

대신 이 대화를 기반으로 "설계 문서 저장소"를 먼저 만드는 것을 추천합니다.

그리고 Codex에게는

"docs 폴더를 설계의 단일 기준(Source of Truth)으로 삼아 구현하라."

라고 지시하는 것이 가장 효과적입니다.

제가 도와드릴 수 있는 부분

개인적으로는 지금 있는 기획서는 아직 10~20% 수준이라고 봅니다.

제가 이 프로젝트를 맡는다면 먼저 약 15~20개의 RFC 수준 Markdown 문서를 작성합니다.

예를 들어:

RFC-0001: Vision

RFC-0002: Repository Structure

RFC-0003: OKF Extension Specification

RFC-0004: Evidence Object

RFC-0005: Knowledge Service API

RFC-0006: Knowledge MCP Protocol

RFC-0007: Hermes Curator

RFC-0008: Sync Pipeline

RFC-0009: GraphRAG Integration

RFC-0010: Vector Search

이렇게 만들어 두면 Codex CLI는 "이 문서들을 읽고 구현해"라는 한 문장만으로도 상당히 정확하게 개발을 진행할 수 있습니다. 저는 이 방식이 가장 생산적이라고 생각합니다.
