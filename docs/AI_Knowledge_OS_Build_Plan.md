# AI Knowledge Operating System 구축 문서

> 상태: 역사적 통합 초안
>
> 이 문서는 초기 논의를 한 파일로 정리한 초안이다. 현재 기준 문서는 `docs/README.md`에 나열된 문서 세트이며, 특히 `docs/02-architecture.md`, `docs/03-okf-spec.md`, `docs/04-evidence-model.md`, `docs/08-sync-pipeline.md`를 우선한다.
>
> 현재 확정된 주요 기준은 `inbox -> .raw -> evidence -> bundles`, `inbox/.raw는 비Markdown 원본 허용`, `bundles는 정제된 OKF 문서`, `source_uuid는 inbox에서 .raw로 이동할 때 발급`이다.

## 1. 문서 목적

본 문서는 Campingtalk의 사내 지식을 AI 친화적으로 수집, 정제, 저장, 검색, 배포하기 위한
`AI Knowledge Operating System` 구축 기준을 정의한다.

이 문서는 다음 목표를 가진다.

- 사람과 AI Agent가 동일한 지식 자산을 사용하도록 한다.
- 지식의 원본(Evidence)과 공식 문서(Bundle)를 분리 관리한다.
- Google Open Knowledge Format(OKF)을 기준으로 저장 구조를 설계한다.
- Hermes, Knowledge Service, Knowledge MCP의 역할을 명확히 정의한다.
- Codex, Claude Code, Gemini 등 다양한 Agent가 동일한 인터페이스로 접근하도록 한다.

## 2. 구축 목표

핵심 목표는 단순한 내부 위키가 아니라, 다음 특성을 가진 지식 운영 체계를 만드는 것이다.

- 지식 수집 파이프라인이 존재한다.
- 원본 데이터와 정제된 지식이 분리된다.
- 정제된 지식은 표준 포맷으로 관리된다.
- 검색은 키워드, 의미, 관계 기반을 함께 사용한다.
- AI Agent는 동일한 Knowledge MCP 인터페이스를 통해 지식을 사용한다.

## 3. 핵심 원칙

### 3.1 Source of Truth

- 공식 지식의 최종 저장소는 Git Repository다.
- 사람이 보는 편집 UI는 Obsidian Vault를 사용한다.
- 모든 변경은 Git 이력으로 추적 가능해야 한다.

### 3.2 OKF 우선

- 모든 공식 지식 문서는 OKF 기반 Markdown으로 관리한다.
- OKF 기본 필드는 변경하거나 제거하지 않는다.
- Campingtalk 전용 필드는 반드시 `extensions` 아래에만 추가한다.
- Hermes는 OKF Validator를 통과한 문서만 Commit한다.

### 3.3 Evidence 기반 큐레이션

- 모든 공식 문서는 최소 1개 이상의 Evidence를 가져야 한다.
- 원본 데이터는 Evidence Object로 별도 저장한다.
- Evidence와 Curated Knowledge 간 양방향 추적이 가능해야 한다.

### 3.4 AI 공통 인터페이스

- Claude Code, Codex, Gemini 등 외부 Agent는 직접 저장소 구조를 알 필요가 없다.
- 외부 Agent는 `Knowledge MCP`를 통해서만 지식을 조회/제안/검증한다.

## 4. 목표 아키텍처

```text
사람
  │
  ▼
Obsidian Vault
  │
  ▼
Git Repository
  │
  ▼
Hermes Knowledge Manager
  ├─ Collector
  ├─ Curator
  ├─ Reviewer
  ├─ Index Manager
  └─ Delegator
  │
  ▼
Knowledge Service
  │
  ▼
Knowledge MCP
  │
  ▼
Codex / Claude Code / Gemini / 기타 Agent
```

## 5. 저장소 구조

초기 구축 시 권장 구조는 다음과 같다.

```text
project-root/
├── .knowledge-os/
│   ├── templates/
│   ├── schemas/
│   └── policies/
└── knowledge/
    ├── bundles/
    │   ├── company/
    │   ├── product/
    │   ├── engineering/
    │   ├── cs/
    │   └── operations/
    ├── evidence/
    │   ├── notion/
    │   ├── slack/
    │   ├── github/
    │   └── meetings/
    └── inbox/
```

현재 저장소에서는 위 구조를 최종 목표로 보고, 우선 `docs/`부터 설계 기준 문서를 축적하는 방식으로 시작한다.

## 6. 데이터 흐름

### 6.1 수집

수집 대상 예시는 다음과 같다.

- Notion
- Slack
- GitHub Issue / PR
- Jira
- 회의록
- 수기 입력 문서

신규 데이터는 먼저 `inbox/` 또는 수집 파이프라인의 임시 큐로 들어간다.

### 6.2 Evidence 저장

원본 데이터는 Evidence Object로 저장한다.

예시 경로:

```text
evidence/notion/2026/07/08/000001.md
```

예시 Frontmatter:

```yaml
---
id: evidence://campingtalk/notion/2026/07/08/000001
provider: notion
provider_url: https://example.com/source
captured_at: 2026-07-08T10:00:00+09:00
status: processed
processed_at: 2026-07-08T10:03:00+09:00
curated_into:
  - knowledge://campingtalk/cs/refund-policy
---
```

권장 상태값:

- `new`
- `processing`
- `processed`
- `ignored`
- `failed`
- `needs_review`

### 6.3 Curation

Hermes Curator의 책임은 다음과 같다.

- 관련 기존 Bundle 검색
- 중복 여부 판단
- 신규 Bundle 생성 또는 기존 Bundle 갱신
- OKF Frontmatter 검증
- 링크, 태그, 요약 생성
- Evidence 연결

### 6.4 Curated Knowledge 저장

공식 지식은 OKF Bundle로 저장한다.

예시:

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

## 7. 주요 컴포넌트 정의

### 7.1 Hermes

Hermes는 Knowledge Manager 역할을 수행한다.

- `Collector`: 외부 시스템 동기화
- `Curator`: Evidence 분석 및 Bundle 생성/수정
- `Reviewer`: 중복/오래된 문서/충돌 문서 탐지
- `Index Manager`: Vector Index와 GraphRAG 갱신
- `Delegator`: 다른 AI Agent 작업 위임 및 Context Package 생성

### 7.2 Knowledge Service

Knowledge Service는 저장소, 검색 인덱스, 검증 로직을 감싸는 내부 SDK다.

권장 API:

- `search_knowledge()`
- `prepare_context()`
- `update_bundle()`
- `propose_update()`
- `validate_okf()`
- `rebuild_indexes()`

Knowledge Service 내부 책임:

- Git 읽기/쓰기
- Markdown 파싱
- OKF 검증
- Evidence 연결
- Vector DB 질의
- GraphRAG 질의

### 7.3 Knowledge MCP

Knowledge MCP는 외부 AI Agent용 표준 인터페이스다.

권장 Tool:

- `search_knowledge`
- `prepare_context`
- `read_bundle`
- `propose_update`
- `validate_result`
- `publish_changes`

원칙:

- 외부 Agent는 Evidence 저장소의 내부 구조를 직접 다루지 않는다.
- 외부 Agent는 MCP를 통해 필요한 문맥만 전달받는다.
- MCP는 내부 구현체(GraphRAG, Vector DB, Git)를 은닉한다.

## 8. 검색 전략

하이브리드 검색을 기본으로 한다.

### 8.1 Semantic Search

- Qdrant 등 Vector DB 사용
- 자연어 질의와 유사한 문서를 찾는다.

### 8.2 Relationship Search

- Microsoft GraphRAG 사용
- 문서 간 관계, 엔티티 연결, 맥락 흐름을 추적한다.

### 8.3 Keyword Search

- Markdown/BM25 기반 검색 사용
- 정확한 명칭, 정책명, 키워드 매칭에 활용한다.

최종적으로 Knowledge MCP는 세 결과를 통합해 반환한다.

## 9. 운영 정책

### 9.1 문서 정책

- 모든 공식 문서는 Markdown 기반으로 관리한다.
- 모든 Bundle은 `summary`를 가진다.
- 모든 Bundle은 `owner` 또는 `owners`를 가진다.
- 모든 Bundle은 최소 1개 이상의 `evidence`를 가진다.
- `status`는 `active`, `draft`, `deprecated` 등을 명확히 관리한다.

### 9.2 확장 정책

- OKF 표준 필드는 그대로 유지한다.
- 조직 특화 메타데이터는 `extensions` 아래에만 추가한다.
- 확장 스펙은 별도 문서에서 정의하고 코드로 검증 가능해야 한다.

### 9.3 커밋 정책

- Hermes는 검증 실패 문서를 Commit하지 않는다.
- 대량 갱신 시 Evidence와 Bundle의 참조 무결성을 먼저 검사한다.
- 인덱스 갱신은 Commit 이후 비동기 작업으로 분리 가능하다.

## 10. 단계별 구축 로드맵

### Phase 1. 저장소 및 문서 기반 구축

- Git Repository 구조 확정
- `docs/` 설계 문서 작성
- Obsidian Vault 사용 원칙 정리
- `AGENTS.md` 작성
- OKF 기본 템플릿 정의

### Phase 2. Evidence 파이프라인 구축

- `inbox/` 설계
- Evidence 저장 규칙 확정
- `why_collected`, `intended_use` 기반 목적 있는 수집
- UUID 또는 URI 규칙 확정
- 상태 전이 모델 정의

### Phase 3. Hermes Curator 구축

- Evidence 읽기
- 기존 Bundle 탐색
- 신규/수정 판단 로직
- OKF Validator 연동
- Outcome의 Runbook·Guide·Decision·Template 승격 후보 분류

### Phase 4. Knowledge Service 구축

- Bundle CRUD
- Context Builder
- 검색 인터페이스 추상화
- Git 연동
- `bundles/<domain>/runbooks/` Workflow 탐색
- Inquiry와 신선도 검토 대상 조회

### Phase 5. Knowledge MCP 구축

- 외부 Agent용 Tool 정의
- Claude Code / Codex / Gemini 연동 방식 정리
- Context 전달 정책 수립

### Phase 6. 고급 검색 및 자동 동기화

- GraphRAG 연동
- Vector DB 연동
- Slack / Notion / GitHub / Jira / 회의록 동기화

## 11. Codex 연계 방식

Codex에는 대화 내용을 직접 길게 전달하기보다, 문서 저장소를 컨텍스트로 주는 방식이 적합하다.

권장 방식:

1. 프로젝트 루트에 `docs/`를 둔다.
2. `OPERATING_RULES.md`에 전역 운영 규약과 Reference Traceability를 명시한다.
3. Runtime Agent는 전역 운영 규약만 사용하고, Repository Agent만 필요한 설계 문서를 확인한다.

예시 지시:

```text
OPERATING_RULES.md를 먼저 읽어.
Reference Traceability에서 아키텍처 리뷰에 필요한 문서만 선택해.
OKF와 Campingtalk Profile을 구분해 전체 아키텍처를 리뷰해.
수정은 하지 말고 review만 해줘.
```

## 12. 권장 문서 세트

구축 문서 1개만으로는 부족하므로 아래 문서 세트를 권장한다.

```text
docs/
├── 01-vision.md
├── 02-architecture.md
├── 03-okf-spec.md
├── 04-evidence-model.md
├── 05-hermes.md
├── 06-knowledge-service.md
├── 07-mcp-spec.md
├── 08-obsidian-guidelines.md
├── 09-sync-pipeline.md
├── 10-development-roadmap.md
└── 11-agents-guidelines.md
```

## 13. 우선 실행 권장사항

현재 단계에서는 아래 순서로 진행하는 것이 가장 효율적이다.

1. `docs/` 문서 세트 작성
2. `AGENTS.md`에 OKF 중심 규칙 명시
3. 저장소 구조 초안 생성
4. Evidence 모델과 OKF Bundle 스펙 확정
5. Knowledge Service 뼈대 구현
6. Knowledge MCP 인터페이스 정의
7. Hermes Curator 구현

## 14. 결론

이 프로젝트는 일반적인 위키 구축이 아니라, 지식의 수집, 검증, 정제, 검색, 배포를 표준화하는
`AI Knowledge Operating System` 구축 프로젝트로 정의하는 것이 적절하다.

구현의 출발점은 코드가 아니라 문서다.

특히 다음 세 가지를 먼저 고정해야 한다.

- OKF 준수 원칙
- Evidence와 Bundle의 데이터 모델
- Hermes / Knowledge Service / Knowledge MCP의 책임 경계

이 문서를 기준으로 후속 세부 설계 문서를 확장하면, Codex 같은 구현 Agent가 저장소 문맥만으로도
안정적으로 개발을 시작할 수 있다.
