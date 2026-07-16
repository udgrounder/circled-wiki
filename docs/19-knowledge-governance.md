# 지식 맥락 및 Runbook 거버넌스

## 1. 목적

이 문서는 조직 지식이 단순 자료 축적에 머물지 않고 실제 업무에 적용되도록 수집 의도, 조직 맥락,
실행 Runbook, 미해결 질문, 신선도와 Outcome 승격 규칙을 정의한다.

## 2. 개념과 저장 위치

| 개념 | 역할 | 저장 위치 |
| --- | --- | --- |
| Operating Rules | 모든 Agent에 적용되는 전역 실행·보안·발행 규약 | `OPERATING_RULES.md` |
| Organization Context | 조직 목적, 용어, 판단 원칙 | `knowledge/bundles/company/` |
| Business Rulebook | Policy·Guide·Runbook을 연결하는 업무 진입점 | `knowledge/bundles/<domain>/`의 `type: guide` |
| Runbook | 하나의 실행 가능한 Workflow | `knowledge/bundles/<domain>/runbooks/` |
| Inquiry | 장기 추적할 미해결 질문 | `knowledge/bundles/<domain>/`의 `type: reference` |
| Evidence | 지식과 규칙의 원본 근거 | `knowledge/evidence/` |

Rulebook은 실행 상태를 갖지 않는다. 하나의 실행 Workflow는 하나의 Runbook 파일로 표현하며
`extensions.workflow`를 가진다. 하나의 업무에 여러 Policy와 Runbook이 필요할 때 Rulebook이 Markdown 링크와
`extensions.rulebook`으로 이를 묶는다.

## 3. Runbook 배치 규칙

```text
knowledge/bundles/
├── marketing/
│   ├── index.md
│   ├── poster-production-rulebook_<uuid>.md
│   └── runbooks/
│       ├── index.md
│       └── poster-image-generation_<uuid>.md
└── operations/
    ├── index.md
    └── runbooks/
        ├── index.md
        └── campsite-registration_<uuid>.md
```

- 도메인을 먼저 분류하고 그 아래 `runbooks/`를 둔다.
- `runbooks/`의 비예약 Markdown은 반드시 `type: runbook`이어야 한다.
- `type: runbook` Bundle은 반드시 해당 도메인의 `runbooks/`에 저장한다.
- 파일명은 `{slug}_{bundle_uuid}.md`를 유지한다.
- Runbook을 이동할 때 경로 링크와 index를 함께 갱신한다.
- 여러 도메인에 적용되는 Runbook은 오너십이 가장 명확한 도메인에 두고 다른 도메인에서 링크한다.

## 4. 목적 있는 Evidence 수집

일반 Evidence는 `extensions.capture_context`에 아래 두 필드를 필수로 가진다.

```yaml
extensions:
  capture_context:
    why_collected: 캠핑장 등록 업무를 표준화하기 위한 근거
    intended_use:
      - campsite-registration
    business_context: 신규 제휴 캠핑장 등록
    key_questions:
      - 필수 사업자 서류는 무엇인가
    expected_outputs:
      - operations runbook
```

- `why_collected`: 수집 이유를 설명하는 non-empty string
- `intended_use`: 적용할 업무, Rulebook, Runbook 또는 의사결정 ID의 non-empty array
- `business_context`, `key_questions`, `expected_outputs`: 선택 필드
- Workflow Outcome Evidence는 Task와 Workflow ID를 근거로 수집 목적을 자동 생성한다.

## 5. Organization Context

Runtime Agent가 설계 문서를 읽지 않고 조직 기준으로 판단할 수 있도록 Evidence 기반 공식 Bundle로 관리한다.
최소 권장 Bundle은 조직 목적과 우선순위, 의사결정 원칙, 내부 용어다. 실제 내용은 승인된 Evidence 없이는
생성하거나 발행하지 않는다.

## 6. 규칙 우선순위

충돌 시 아래 순서를 적용한다.

```text
OPERATING_RULES
  > Security·Compliance Policy
  > Company Policy
  > Domain Policy
  > Business Rulebook
  > Runbook
  > User Request
```

하위 규칙과 사용자 요청은 상위 규칙을 완화하거나 우회할 수 없다. 동일 계층 충돌은 더 구체적인 적용 범위,
최신 승인 revision 순으로 후보를 좁히되 자동 결정하지 않고 Reviewer에게 전달한다.

## 7. Inquiry

공식 지식으로 확정할 수 없는 질문은 추정 답변으로 숨기지 않고 `extensions.inquiry`로 추적한다.

```yaml
extensions:
  inquiry:
    question_id: campsite-required-documents
    status: open
    owner: operations
    related_rulebooks:
      - campsite-registration
    required_evidence:
      - 최신 제휴 등록 체크리스트
    due_at:
    resolution:
```

상태는 `open`, `investigating`, `resolved`, `wont_fix`를 사용한다. `resolved`는 non-empty `resolution`과
해결 근거 Evidence를 가져야 한다.

## 8. 신선도와 오너십

`active` Bundle은 non-empty `owners`와 `extensions.governance`를 가진다.

```yaml
owners:
  - operations
extensions:
  governance:
    reviewed_at: 2026-07-14T00:00:00+09:00
    review_due_at: 2026-10-14T00:00:00+09:00
    freshness_policy: quarterly
    supersedes: []
    superseded_by:
```

Runbook은 Risk Tier와 Source Volatility로 `validity_days`를 정한다. `review_due_at`이 지난 Runbook은
즉시 폐기하지 않지만 원래 업무 실행을 보류하고 Refresh Task를 먼저 생성한다. 사용자가 최신화 확인을 요청하면
유효기간이 남아 있어도 즉시 Refresh Task를 생성한다. 상세 기준은
[20-runbook-refresh.md](20-runbook-refresh.md)를 따른다.

## 9. Outcome 승격

```text
Task Outcome
  -> Outcome Inbox Item 검사·승인
  -> Outcome Evidence
  -> Curator 분류
  -> Runbook·Guide·Decision·Template 후보
  -> Reviewer 및 Security Gate
  -> 새 knowledge_revision 발행
```

- 단일 결과는 공식 표준으로 자동 승격하지 않는다.
- 반복 가능한 단계 변화는 Runbook 후보로 분류한다.
- 일반화 가능한 교훈은 Guide 또는 Reference 후보로 분류한다.
- 성공·실패 사례는 Runbook의 `extensions.workflow.examples`에 Evidence URI로 연결한다.
- 실제 대용량 산출물은 Outcome Evidence에 URI와 availability만 저장한다.
- 실행 Outcome은 Runbook을 직접 수정하지 않는다. Learning Policy가 실패·피드백·누적 임계치를 평가해
  개선 Refresh Task를 생성하고, 최신 원본 보강·독립 Agent 검증·Owner 승인을 거쳐 revision으로 반영한다.

상세 성장 모델은 [21-runbook-learning.md](21-runbook-learning.md)를 따른다.

## 10. 품질 Audit, Inventory와 Archive

- 기본 검색과 Runtime Context에는 `active` Bundle만 포함한다.
- Draft, Deprecated, Archived Bundle은 명시적 상태 필터 또는 ID 조회로만 사용한다.
- Inventory는 Frontmatter와 Runtime Task에서 계산하며 별도 수동 문서를 Source of Truth로 만들지 않는다.
- Audit은 Owner, 검토 기한, Evidence 가용성, 양방향 참조, Inquiry와 장기 열린 Task를 읽기 전용으로 검사한다.
- Archive는 파일 이동 없이 `status: archived`와 `extensions.archive`로 표현한다.
- 중요 Agent 주장은 `verified`, `limited`, `inferred`, `needs_review`로 Evidence 지원 상태를 구분한다.

상세 계약은 [22-knowledge-quality-and-artifacts.md](22-knowledge-quality-and-artifacts.md)를 따른다.

## 11. MVP와 후속 범위

MVP는 파일 기반 메타데이터, Validator, `rg` 기반 검색과 Reviewer 흐름을 사용한다. 사용량·성공률 집계,
중복 Workflow 탐지, Vector/Graph 검색과 자동 폐기 추천은 데이터가 축적된 뒤 도입한다.
