# Agent Rule Profiles

이 디렉터리는 작업 단계별 실행 Profile을 제공한다. 전역 정책의 Source of Truth는
`OPERATING_RULES.md`이며, Profile은 특정 단계에서 필요한 규칙만 구체화한다.
Profile은 전역 필드·상태·참조 계약을 다시 서술하지 않고 적용할 Rule ID와 해당 단계의 행동·Gate만 기록한다.

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
  -> inbox-disposition
  -> inbox-inspection
  -> evidence-ingest
  -> knowledge-curation
  -> publication
```

`knowledge-query`, `workflow-execution`, `system-observation`, `runtime-upgrade-verification`은 요청 목적에 따라
독립적으로 선택한다. 제품 개발·설치·배포 Profile은 source repository의 `product-agent-rules/`에만 둔다.
한 Agent가 여러 단계를 수행하더라도 단계별 Profile과 Gate를 순서대로 적용해야 한다.

`contracts/index.yaml`은 영역별 실행 계약을 등록하며, 각 계약은 Frontmatter와 Queue에 기록된 현재 상태에서 안전하게 재수행할 수 있는
선행 단계만 구조화한다. Inbox 계약은 `inbox-inspection`과 `evidence-ingest` Profile을 대체하지 않는다. 자동 PII Scan은
전화번호를 포함한 정책 대상 PII를 실제 후보에서 검사·마스킹해 `passed` 또는 `masked` Receipt를 확정할 수 있지만, PII 유형으로
정책·절차 근거가 없는 민감성 판단, `needs_review` 뒤 안전 처리, 승인 판단을 자동으로 해소하지 않는다.

`needs_review`는 단계가 자동 결론을 낼 수 없다는 판정이고, `awaiting_user`는 사용자만 할 수 있는 행동을 실제로 기다리는 Queue
상태다. Curation의 `review_handoff`는 Review 카드 생성 결과이며, 카드가 사용자 또는 허용된 검증 Agent 중 누구를 기다리는지는
카드의 reviewer 계약이 결정한다.

여러 단계로 구성된 Pipeline은 먼저 독립적으로 검증 가능한 하위 작업을 식별하고, 사용할 수 있는 위임 수단이 있으면
위임을 권장한다. 위임은 Gate·승인·최종 책임을 이전하지 않으며, 위임 여부만으로 작업을 차단하지 않는다. 하위 작업을
안전하게 분리할 수 없거나 위임 수단이 없으면 같은 Profile의 Gate를 지키며 직접 수행할 수 있다.

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

## State, Contract, and Resume Source

이 README는 상태 전이를 다시 정의하지 않는다. 정본은 아래와 같이 분리한다.

| 주제 | 정본 |
| --- | --- |
| 전역 용어·예외·처리 주체 전이·발행 경계 | `OPERATING_RULES.md` |
| Inbox 전이·차단 사유·재처리 | `contracts/inbox.yaml`, `inbox-inspection.md`, `inbox-sensitivity-review.md`, `evidence-ingest.md` |
| Curation outcome·재시도 | `contracts/curation.yaml`, `knowledge-curation.md` |
| Queue 상태 조회·재개 | 각 계약의 `current.stage/status/actor`, `requirements`, Receipt |
| Commit·Push 상태 공유 | `publication.md` |

자동 PII Scan은 전화번호를 포함한 정책 대상 PII를 실제 후보에서 검사·마스킹하는 Evidence 직전 단계다.
`needs_review`는 단계별 판정이고, 사용자만 할 수 있는 조치일 때만 계약 작업을 `awaiting_user`로 전이한다.
`review_handoff`는 Curation Review 카드 생성 결과이며 사용자 대기 상태가 아니다.

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
