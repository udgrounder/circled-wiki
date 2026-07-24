# Knowledge 품질, 근거 지원 및 산출물 설계

## 1. 목적

사용자 제공 레퍼런스, Agent 답변, Workflow 산출물과 오래된 지식을 검증 가능한 상태로 관리한다. 공식 지식은
계속 `Markdown + YAML Frontmatter`를 사용하고, Task·API 전달 상태만 JSON을 사용한다.

## 2. 설계 결정

| 대상 | 저장 위치 | Source of Truth 여부 |
| --- | --- | --- |
| Evidence Original과 Evidence Record | `knowledge/evidence/` | 원본 근거 |
| 공식 Bundle·Runbook·Decision | `knowledge/bundles/` | 공식 지식 |
| Reference Assessment 진행 상태 | `.runtime/tasks/` | 일시적 실행 상태 |
| Inventory·Audit | Frontmatter에서 계산 | 파생 조회 |
| Outcome 원본 | Evidence 원본 JSON | 실행 증적 |
| Outcome manifest | Markdown + YAML Frontmatter | Evidence 색인 |

수동 `inventory.md`를 별도 기준으로 관리하지 않는다. Archive는 경로 이동 없이 Bundle `status`와
`extensions.archive`로 표현한다. 이 선택은 파일 경로를 Concept Identity 일부로 취급하는 현재 Profile을
보존한다.

## 3. 사용자 레퍼런스 평가

`submit_runbook_reference`는 레퍼런스를 Candidate Evidence로 열린 Refresh Task에 병합한다. 이후
`record_reference_assessment`가 다음 항목을 기록한다.

```yaml
reference_assessment:
  evidence_id: evidence/{organization_id}/{name}_{source_uuid}.md
  authority: primary
  recency: newer
  applicability: partial
  corroboration: corroborated
  conflicts: []
  disposition: partial_accept
  rationale: 최신 공식 자료의 모바일 규격만 반영
  assessed_by: hermes-curator
  verified_by: verification-agent
  assessed_at: 2026-07-14T00:00:00+09:00
```

- `authority`: `primary`, `official_secondary`, `internal_experience`, `informal`
- `recency`: `newer`, `same_period`, `older`, `unknown`
- `applicability`: `full`, `partial`, `out_of_scope`
- `corroboration`: `corroborated`, `single_source`, `conflicting`
- `disposition`: `accept`, `partial_accept`, `reject`, `needs_more_evidence`

평가자와 검증자는 달라야 한다. 평가는 채택을 자동 확정하지 않으며 Refresh 변화 판정, 독립 Agent 검증,
Validator와 Owner 승인을 계속 거친다.
모든 Candidate Evidence는 변화 판정 전에 Assessment를 가져야 하며 `out_of_scope + accept`와
`conflicting + accept` 조합은 허용하지 않는다.

## 4. Claim Support 계약

정책·보안·가격·법률·외부 등록 요건·성과 수치처럼 중요한 주장은 다음 상태를 사용한다.

- `verified`: 접근 가능한 원본 Evidence로 직접 확인
- `limited`: 근거가 있으나 범위가 제한됨
- `inferred`: Evidence에서 직접 확인되지 않은 해석
- `needs_review`: 근거 부족 또는 최신성 재확인 필요

`prepare_context`는 이 계약을 Agent에 전달하고 `validate_claim_support`는 계약 구조와 Evidence 참조·원본
무결성을 읽기 전용으로 검사한다. Evidence가 Claim을 의미적으로 입증하는지는 별도 Reviewer가 판단한다. 공식 지식 Bundle로 승격할 때는
[Claim Support Template](../.circled-wiki/templates/claim-support.md)의 Markdown 구획을 사용한다.

## 5. 검색, Archive와 Inventory

기본 `search_knowledge`와 Operational Context에는 `status: active` Bundle만 포함한다. Draft, Deprecated,
Archived 조회는 `status` 필터를 명시해야 한다. `read_bundle`은 ID를 명시한 조사·감사 용도로 비활성 Bundle을
읽을 수 있지만 Runtime Context에는 자동 포함하지 않는다.

`list_knowledge_inventory`는 다음 값을 Frontmatter와 Runtime Task에서 계산한다.

- Domain, Type, Status, Owner
- `knowledge_revision`, `updated_at`
- `reviewed_at`, `review_due_at`, Freshness state
- Evidence availability
- 열린 Task와 Inquiry

Restricted Bundle과 Evidence는 Inventory, Audit, Claim Support와 효과 측정 결과에서 제외한다.

Archive Bundle은 다음 계약을 사용하고 파일을 이동하지 않는다.

```yaml
status: archived
extensions:
  archive:
    archived_at: 2026-07-14T00:00:00+09:00
    archived_by: knowledge-owner
    reason: 프로젝트 종료
    restore_condition: 다음 캠페인 비교 검토 시
```

## 6. Knowledge Audit

`audit_knowledge`는 공식 지식을 수정하지 않는 읽기 전용 검사다.

- Owner 없는 Active Bundle
- 검토 기한이 지난 Bundle
- 접근 불가능하거나 누락된 Evidence
- Bundle-Evidence 역참조 누락
- 열린 Inquiry
- 관련 링크가 없는 Active Bundle
- 30일 이상 열린 Runtime Task
- Deprecated 기반 Archive 후보

MVP는 파일·Frontmatter·Markdown 링크로 확인 가능한 항목만 검사한다. 의미 기반 중복·상충 탐지는
Vector/Graph 검색 도입 전까지 휴리스틱 자동 판정으로 확정하지 않는다.

권장 운영 주기는 자료 수집 직후 무결성 검사, 주간 운영 Audit, 월간 Archive·상충 후보 검토, 중요 산출물
작성 전 Claim Support 검사다. 스케줄 자동화는 Worker 운영 설정으로 제공하며 Audit 결과 자체는 공식 지식이 아니다.

## 7. Evidence 수집 가치

Evidence `extensions.capture_context`는 기존 수집 이유와 적용 대상에 다음 선택 기준을 추가한다.

```yaml
capture_context:
  why_collected: 포스터 Runbook 최신화 근거
  intended_use: [poster-production]
  reuse_value: high
  retention_class: workflow_reference
  sensitivity_review: completed
```

- `reuse_value`: `high`, `medium`, `low`
- `retention_class`: `workflow_reference`, `decision_record`, `outcome`, `general_reference`, `ephemeral`
- `sensitivity_review`: `completed`, `required`, `not_applicable`

이 값은 Evidence의 진실성 점수가 아니라 수집·보존 운영 분류다.

## 8. Artifact Profile과 Outcome

Runbook은 선택적으로 `extensions.workflow.artifact_profile`을 정의한다.

```yaml
artifact_profile:
  type: decision_report
  required_sections:
    - purpose
    - conclusion
    - evidence
    - risks
    - next_actions
    - open_questions
```

지원 Profile은 `decision_report`, `work_guide`, `registration_package`, `design_brief`, `review_report`,
`comparison_report`다. Profile이 있는 Runbook의 완료 Outcome은 같은 Profile과 필수 section을 선언한 Artifact를
포함해야 한다.

Outcome은 `summary`, `feedback`, `learnings`, `artifacts` 외에 다음을 구조화한다.

- `decisions`: 결정, 결정자, 이유, Evidence
- `action_items`: 제목, Owner, 완료 기준, 선택적 기한
- `open_questions`: 질문과 확인 Owner

Outcome 원본 JSON은 Evidence로 보존하며 manifest는 계속 Markdown + YAML Frontmatter다. 반복 가능한 변화만
Curator·Reviewer·Owner 검증을 거쳐 Runbook, Guide, Decision 또는 Template revision으로 승격한다.

`measure_runbook_effectiveness`는 Outcome을 `knowledge_revision`별로 집계해 완료·실패·검토 필요·피드백과
완료율을 제공한다. 최소 두 revision에 실제 Outcome이 있어야 비교 가능하다고 표시하며, 표본이 적은 결과를
개선 인과관계로 자동 단정하지 않는다.

## 9. 검증과 완료 조건

- 비활성 Bundle이 기본 검색과 Context에 포함되지 않는다.
- 사용자 Candidate Evidence는 평가자와 별도 검증자를 가진다.
- `verified` Claim은 `available` Evidence를 참조한다.
- Archive Bundle은 사유와 복구 조건을 가진다.
- Artifact Profile이 있는 완료 Outcome은 필수 section을 만족한다.
- Inventory와 Audit은 저장된 수동 색인 없이 재생성 가능하다.

## 10. Reference

- [OKF 적용 및 확장 규격](03-okf-spec.md)
- [Evidence 객체 설계](04-evidence-model.md)
- [Workflow 실행 및 지식 환류](16-workflow-execution.md)
- [Knowledge Governance](19-knowledge-governance.md)
- [Runbook Refresh](20-runbook-refresh.md)
- [Runbook Learning](21-runbook-learning.md)
