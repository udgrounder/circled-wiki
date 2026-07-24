# Agent Rule Profiles

이 디렉터리는 작업 단계별 실행 Profile을 제공한다. 전역 정책의 Source of Truth는
`OPERATING_RULES.md`이며, Profile은 특정 단계에서 필요한 규칙만 구체화한다.

## Profile Contract

모든 Profile은 다음 항목을 정의한다.

1. Trigger: 언제 선택하는가
2. Input: 시작 전에 필요한 값
3. Allowed Actions: 이 단계에서 허용되는 변경
4. Checks: 결과에 기록하지만 반드시 진행을 막지는 않는 확인
5. Gates: 다음 단계 전환을 차단하는 조건
6. Output: 다음 단계가 소비할 산출물
7. Failure State: 실패 시 자료를 어디에 어떤 상태로 남기는가
8. Prohibited: 이 단계에서 하면 안 되는 작업

## Stage Flow

```text
inbox-capture
  -> inbox-inspection
  -> evidence-ingest
  -> knowledge-curation
  -> publication
```

`knowledge-query`, `workflow-execution`, `system-observation`, `runtime-upgrade-verification`은 요청 목적에 따라
독립적으로 선택한다. 제품 개발·설치·배포 Profile은 source repository의 `product-agent-rules/`에만 둔다.
한 Agent가 여러 단계를 수행하더라도 단계별 Profile과 Gate를 순서대로 적용해야 한다.

여러 단계로 구성된 Pipeline은 먼저 독립적으로 검증 가능한 하위 작업을 식별하고, 사용할 수 있는 위임 수단이 있으면
위임을 우선 검토한다. 위임은 Gate·승인·최종 책임을 이전하지 않으며, 하위 작업을 안전하게 분리할 수 없거나 위임 수단이
없으면 같은 Profile의 Gate를 지키며 직접 수행할 수 있다.

## Responsibility Matrix

| Stage | Responsible | Accountable | Consulted | Informed |
| --- | --- | --- | --- | --- |
| Capture | Capture Agent 또는 Source Adapter | 요청 Scope를 가진 Operator | Data Owner | Inbox Worker |
| Inspection | Inspector Agent | Security 또는 Knowledge Operator | Data Owner | Ingest Worker |
| Evidence Ingest | Ingest Worker | Knowledge Operator | Inspector | Curator |
| Curation | Curator Agent | Knowledge Owner | Domain Reviewer | Publisher |
| Publication | Publisher | 승인된 Owner | Security Reviewer | Runtime Consumer |
| System Observation | Runtime Agent | 설치본 Operator | System Maintainer | Product Maintainer |
| Runtime Upgrade Verification | 독립 Runtime Verifier | Deployment Owner | System Maintainer | Product Maintainer |

같은 실행 주체가 여러 역할을 맡더라도 Profile을 합치지 않는다. Approval이 필요한 단계에서는 제안자와
승인자를 분리한다.

## State Transitions

| Current | Action and Profile | Required Gate | Next |
| --- | --- | --- | --- |
| 없음 | `capture_conversation` · Inbox Capture | 필수 입력, 안전 경로, idempotency, 모든 수집 주체의 공통 민감정보 사전 점검 | `pending` |
| `pending` | `inspect_inbox` · Inbox Inspection | 메타데이터, 경로, checksum, Inbox Sensitive Data Review 상태 | 승인 가능 또는 보류 |
| `pending` + `sensitivity_review: required` | `review_inbox_sensitivity` · Inbox Inspection | 식별된 사람의 완료·비해당 결정 | 승인 검사 가능 |
| `pending` | `accept_inbox` · Inbox Inspection | 모든 Gate 통과, inspector actor | `accepted` |
| `accepted` | `ingest_accepted` · Evidence Ingest | 검사 기록, Evidence Schema, 수집 주체와 독립된 민감정보 재검수·안전한 텍스트 파생본 | Evidence `new` |
| Evidence `new` | `propose_pending` · Knowledge Curation | 원본 접근, 관련성 검토 | 정제 제안 |
| Draft | Review · Publication | Validator, Evidence, 보안, Owner 승인 | 발행 가능 |

## Exceptions

| Scenario | Required Handling |
| --- | --- |
| 동일 idempotency key의 checksum 변경 | Capture 중단, 구조화된 기존 Inbox Item 참조를 확인하고 충돌 보고 |
| checksum 불일치 | Inbox 유지, 승인 금지 |
| `sensitivity_review: required` | 승인 금지, 검토 완료 후 재검사 |
| Evidence 변환 중 민감정보 감지 | 실제 값은 기록하지 않고 범주만 결과에 남긴 뒤, 텍스트는 안전한 파생 입력으로 변환; 파일·판단 불가는 사람 검토 |
| provider와 폴더 불일치 | Inbox 유지, 자동 이동·수정 금지 |
| accepted 항목 ingest 실패 | Inbox와 필요 시 `.raw/` 유지, 재시도 조건 기록 |
| Evidence는 있으나 정제 누락 | `propose_pending`으로 재처리 |
| Profile 선택이 모호함 | 변경을 시작하지 않고 기대 출력을 확인 |

## Metrics

| Metric | Target | Measurement |
| --- | --- | --- |
| Capture에서 Evidence를 생성한 비율 | 0% | Capture 응답에 Evidence ID가 없는지 테스트 |
| 미승인 Inbox ingest 비율 | 0% | `accepted` 외 상태의 Evidence 생성 건수 |
| checksum 변조 통과율 | 0% | 변조 회귀 테스트 |
| Profile 참조 누락 | 0건 | `test_agent_rules.py` |
| 단계별 실패 위치 식별률 | 100% | 도구 응답의 stage·error 확인 |

## Check, Gate, Test

- Check: 관찰 결과를 기록한다. 경고만으로 다음 단계를 자동 차단하지 않는다.
- Gate: 통과하지 못하면 다음 Profile로 전환하지 않는다.
- Test: Repository Engineering에서 시스템 구현의 동작을 검증한다. Runtime 입력 수집의 기본 절차가 아니다.
