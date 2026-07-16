# Hermes 아키텍처

## 1. 개요

Hermes는 회사 전용 지식 라이브러리를 운영하는 AI 기반 Knowledge Manager이자, 사용자 요청 시 그 라이브러리를 이용하는 핵심 Agent다.

Hermes는 하나의 실행 프로세스가 아니라 아래 다섯 개 역할(Collector/Curator/Reviewer/Index Manager/Delegator)을 묶은 논리적 이름이다. 실제 실행 시점(언제 움직일지)은 `docs/12-runtime-architecture.md`의 **Worker**가 결정한다. 역할별로 코드만으로 처리되는지, LLM 판단이 필요한지가 다르다.

- **트리거(코드, 판단 불필요)**: Worker가 스케줄/수동 트리거 시점을 감지하고 Core Service를 호출한다. Collector의 수집/정규화, Index Manager의 인덱스 갱신은 여기 속한다.
- **판단(LLM 호출 필요)**: Worker가 호출한 뒤, 실제로 의미를 판단해야 하는 지점에서만 LLM Agent를 호출한다. Curator의 Bundle 매칭/신규 판단, Reviewer의 충돌·리뷰 요청 처리가 여기 속한다.
- **위임(LLM 판단 + Context 주입)**: Hermes가 하위 Agent를 실행해야 할 때는 Knowledge Service의 `prepare_context()` 결과를 그 하위 Agent의 프롬프트/도구로 주입한 뒤 실행시킨다. Delegator가 담당한다.

## 2. 책임

- 입력 수집 작업 조정
- Evidence 기반 정제
- Bundle 생성 및 수정
- 문서 품질 점검
- 검색 인덱스 갱신 트리거
- 다른 AI Agent 위임
- 사용자 요청에 맞는 Bundle과 Evidence를 검색하고, 출처를 유지한 응답·작업·수정안을 생성

## 2.1 두 가지 운영 모드

- **라이브러리 운영 모드**: 사용자·지정 Batch·Hermes가 제공한 원본의 Evidence 보존, Bundle 갱신, 검증, Git 반영을 수행한다.
- **사용자 요청 처리 모드**: Hermes가 Knowledge Service를 통해 직접 검색·Context Package 생성·응답을 수행하거나, 하위·외부 AI Agent가 MCP 또는 CLI를 통해 같은 지식 라이브러리를 이용하도록 위임한다. 사용 중 발견된 누락·최신성 의심은 `review_requested` 또는 수집 작업으로 되돌린다.

MCP는 기본적으로 `read_only`로 실행한다. `.runtime/` 기록과 Git 발행이 필요한 `operator`는 Hermes 또는
Hermes가 작업 범위·기간을 한정해 위임한 내부 Agent 실행 컨텍스트에만 부여한다. 위임받지 않은 Agent와
외부 네트워크에는 노출하지 않는다.

## 3. 내부 구성

### Collector

실행 방식: 코드(판단 불필요) — 사용자·지정 Batch·Hermes의 수집 요청에서 호출한다.

- inbox 상대경로와 수집 목적을 확인해 Evidence 생성을 요청한다.
- 지정 Batch 재실행은 안정적인 `idempotency_key`로 중복과 충돌을 구분한다.

### Curator

실행 방식: LLM 판단 필요 — Worker가 호출한 뒤 실제 의미 판단을 수행한다.

- 관련 Bundle 검색
- 중복/갱신/신규 생성 판단
- 매칭이 실패하거나 애매하면 신규 Bundle을 함부로 만들지 않고 사람 검토 큐로 전환한다(오탐 방지)
- 요약, 태그, 링크 제안
- 신규 Bundle은 `create_draft_bundle`, 기존 Bundle은 `apply_bundle_revision`으로 반영
- OKF 검증 전 결과물 작성
- `Campingtalk OKF Profile` 적합성 확인

### Reviewer

실행 방식: LLM 판단 필요 — Worker의 유지보수 스케줄 또는 검토 요청 발생 시 호출한다.

- 충돌 문서 탐지
- `extensions.review_requested`가 true로 표시된 Bundle 처리(사람 또는 Agent의 사후 검토 요청, `docs/03-okf-spec.md` 참고)
- 신규 Evidence가 기존 Bundle과 매칭됐어야 하는데 반영되지 않은 사례 탐지(반영 파이프라인 신뢰성 점검)
- 중복 Bundle 탐지
- 사람 검토 필요 케이스 식별

### Index Manager

실행 방식: 코드(판단 불필요) — Worker의 유지보수 스케줄에서 호출한다.

- OS 파일 검색 대상 갱신
- Frontmatter 필터 인덱스 갱신
- Markdown 링크와 backlink 스캔
- Evidence manifest 검색 대상 갱신

### Delegator

실행 방식: LLM 판단 + Context 주입.

- 다른 AI Agent에게 태스크를 분할한다.
- Hermes는 직접 Knowledge Service를 호출할 수 있고, 실행할 하위·외부 Agent에는 MCP 또는 CLI를 통해 `search_knowledge`, `read_bundle`, `prepare_context`를 사용하게 한다.
- Knowledge Service의 `prepare_context()`로 Context Package를 만들어, 실행할 하위 Agent의 프롬프트/도구로 주입한다.
- 하위 Agent 실행 결과를 검증 후 반영한다.
- Workflow Orchestrator로서 `find_workflow`로 활성 Runbook을 선택하고 `prepare_task`로 실행 상태를 생성한다.
- 도메인별 `runbooks/` 후보가 `freshness.state: expired`이면 원래 업무 대신 Refresh Task를 시작한다.
- 사용자가 최신화를 요청하면 유효기간과 관계없이 `prepare_runbook_refresh`를 호출한다.
- `missing_inputs`만 사용자에게 확인하고, `approval_gates`에서는 사람 승인을 받기 전 진행하지 않는다.
- `completion_criteria`로 결과를 검증하고 `record_outcome`으로 완료·실패·학습을 Evidence로 환류한다.
- Task 상태는 공식 지식과 분리된 `.runtime/tasks/`에서 관리한다.

상세 실행 계약은 [16-workflow-execution.md](16-workflow-execution.md)를 따른다.

## 4. 작업 흐름

1. Collector가 입력을 받는다.
2. Evidence를 생성한다.
3. Curator가 관련 Bundle 후보를 찾는다.
4. 신규 생성 또는 수정안을 만든다.
5. Reviewer가 규칙 위반과 충돌을 검사한다.
6. OKF Validator와 Profile Validator를 통과하면 자동 Commit 가능 상태로 전환한다.
7. Agent가 검증된 변경만 자동 Commit한다.
8. Index Manager가 기본 검색 계층을 갱신한다.

사용자 요청 처리 모드에서는 별도로 아래 흐름을 사용한다.

1. Delegator가 요청에 맞는 Workflow 후보를 찾는다.
2. Hermes가 Workflow를 선택하고 Task를 준비한다.
3. 필수 입력과 사람 승인을 확인하며 단계를 수행한다.
4. 결과를 완료 기준으로 검증한다.
5. Outcome Evidence를 만들고 Curator/Reviewer 흐름으로 되돌린다.
6. 사용자 레퍼런스는 Candidate Evidence로 제출하고 별도 Agent 검증을 포함한 Reference Assessment를 기록한다.
7. 중요 주장에는 Claim Support 상태를 붙이고 구조화된 결정·실행 항목·미해결 질문을 Outcome에 남긴다.

## 5. 사람 개입이 필요한 경우

- Evidence가 상충하는 경우
- confidence가 낮은 경우
- 기존 정책과 신규 입력이 충돌하는 경우
- 자동 분류가 애매한 경우
- Candidate Evidence의 권위·적용 범위·상충 여부가 합의되지 않은 경우
- Claim Support가 `needs_review`인 중요 주장을 실행 근거로 사용해야 하는 경우

## 6. 실패 처리

- 파싱 실패: Evidence `failed`
- 의미 없음: Evidence `ignored`
- 품질 불충분: `needs_review`
- 검증 실패: Commit 금지

## 7. 문서 신선도와 검토 요청

문서가 오래됐다는 것 자체는 문제가 아니다. 정확성이 떨어졌는지가 문제이며, 정확성 문제는 아래 두 경로로만 다룬다. `updated_at` 나이를 기준으로 자동 폐기/경고하지 않는다.

### 7.1 반영 파이프라인이 원인인 경우

새 정책(Evidence)이 들어왔는데 기존 Bundle에 반영되지 않았다면, 이는 Curator의 Bundle 매칭 로직이나 반영 규칙의 문제다.

- Curator가 관련 Bundle을 찾지 못하거나 매칭이 애매하면 신규 Bundle을 만들지 않고 검토 큐로 보낸다(3절 Curator 참고).
- Reviewer가 "Evidence는 처리됐는데 대응 Bundle이 갱신되지 않은 사례"를 주기적으로 탐지한다.
- 이 경로에서 반복적으로 놓치는 패턴이 발견되면 `docs/13-future-work.md`의 매칭 정확도 개선 항목으로 넘긴다.

### 7.2 콘텐츠 자체가 의심되는 경우

이미 `active`인 Bundle의 내용에 문제가 있다고 판단되면, 사람 또는 Agent가 아래 방식으로 검토를 요청한다.

- Bundle frontmatter의 `extensions.review_requested`를 `true`로 설정하고 `extensions.review_reason`, `extensions.review_requested_by`, `extensions.review_requested_at`을 함께 기록한다.
- Reviewer가 `review_requested: true`인 Bundle을 주기적으로 모아 사람 검토 큐로 올린다.
- `search_knowledge`/`read_bundle`/`prepare_context` 응답은 `review_requested: true`인 Bundle을 사용할 때 그 사실을 항상 표시한다(저장된 `confidence`와 별개로).
- 검토가 끝나면 `review_requested`를 `false`로 되돌리고 `extensions.knowledge_revision`을 올린다.

## 8. 확장 관리

MVP 범위를 벗어나는 확장 항목은 `docs/13-future-work.md`에서만 관리한다.
