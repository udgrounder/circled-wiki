# Runtime Execution Contracts

`index.yaml`은 설치된 실행 계약의 ID와 상대 경로를 관리한다. 각 계약 파일은 하나의 운영 영역과
그 상태 전이만 정의한다. 계약은 Router와 Profile을 대체하지 않고, 이미 허용된 안전한 전이만
구조화한다.

## 문서 헤더

계약·Registry YAML은 Markdown Bundle의 YAML Frontmatter가 아니라 실행 설정의 문서 헤더를 같은 형태로
사용한다. Runtime은 헤더와 `spec` 구조를 모두 검증한다.

| 속성 | 의미 | 정본 또는 제약 |
| --- | --- | --- |
| `api_version` | YAML 헤더와 `spec` 형식의 버전 | Runtime loader가 지원하는 값과 정확히 일치해야 한다. |
| `kind` | 문서 종류 (`reconciliation_contract_registry` 또는 `reconciliation_contract`) | 파일의 역할을 구분하며 다른 kind로 대체할 수 없다. |
| `metadata.name` | 안정적인 계약·Registry 식별자 | Registry key와 계약 파일의 이름이 일치해야 한다. |
| `metadata.version` | 해당 계약의 의미 버전 | 지원되지 않는 버전은 추정하지 않고 Preflight·실행에서 거부한다. |
| `metadata.description` | 사람이 읽는 목적 설명 | 실행 권한을 부여하지 않는다. |
| `spec` | Runtime이 해석하는 실행 정의 | 허용된 Profile·action·상태 전이와 정확히 일치해야 한다. |

`index.yaml`의 `spec.contracts.<name>.path`는 Registry 파일 기준의 상대 경로다. 절대 경로와 상위 경로
이동(`..`)은 허용하지 않는다.

## 계약별 `spec`

### Inbox

`inbox.yaml`은 Inbox의 검사·수용·Evidence 변환 재조정을 표현한다.

| 속성 | 의미 |
| --- | --- |
| `stages.<state>.profile` | 해당 상태에 적용할 Runtime Profile이다. |
| `stages.<state>.action` | 이미 구현·허용된 안전한 실행 action이다. |
| `stages.<state>.requires` | action 전에 충족돼야 하는 Gate 목록이다. 누락된 Gate를 자동으로 해소하지 않는다. |
| `stages.<state>.next_stage` | 모든 Gate가 충족됐을 때의 다음 상태다. |
| `stages.<state>.on_blocked.task_contract` | Gate가 충족되지 않았을 때 생성·재개할 예외 계약 작업 영역이다. |
| `stages.<state>.on_blocked.reasons.<reason>` | 해당 단계에서 사람이 결정해야 하는 허용 사유와 `current_stage`, `requested_action`, 결정 후 `resolved_next_action`이다. 실제 발생 사유·결정은 같은 계약 작업 파일의 `requirements`와 단계 Receipt에 기록한다. |

### Curation

`curation.yaml`은 Evidence Curation Queue 분석 결과를 `no_bundle_recorded`, `review_handoff`,
`published`, `draft_created`, 재시도 가능한 `queued`로 구분한다.

| 속성 | 의미 |
| --- | --- |
| `stages.queued.profile`·`action`·`requires` | 큐에 있는 Evidence를 분석할 Profile·허용 action·선행 Gate다. |
| `outcomes.<name>.next_stage` | 분석 결과를 기록할 Curation 계약 상태다. |
| `outcomes.<name>.queue_disposition` | `complete`이면 Curation Queue 항목이 사라져야 하고, `retain`이면 재시도 가능하게 남아야 한다. Runtime이 실제 큐 상태를 검증한다. |
| `outcomes.<name>.terminal` | 전체 업무가 끝났다는 뜻이 아니라, 이 **Curation 재조정 계약**에서 더 진행하지 않는다는 뜻이다. `review_handoff` 뒤의 Review·승인 절차는 별도다. |
| `outcomes.retryable_block.reason_categories.<category>` | 세부 구현 오류를 운영상 사유군으로 정규화한다. `reason_codes`는 허용된 사실 코드, `safe_next_action`은 사람이 수행할 안전한 다음 행동이다. |

`curation.yaml`의 outcome은 실행 결과를 설명하고 검증하는 고정 vocabulary다. 계약 파일을 바꿔 임의의
자동 행동·승인·revision 적용 권한을 추가할 수 없다. `approved_update` 적용은 Curation 재조정의 outcome이
아니며, 기존의 checksum·revision 재검사 적용 경로로만 처리한다.

## 계약 작업 기록과 결과물

`workspace/task/<contract-name>/<subject-uuid>.md`는 계약별 처리 기록이다. Inbox에서는 사람의 검토·재시도·중단이
발생한 예외 입력에만 생성하며, 정상 자동 완료 Inbox는 Evidence와 실행 Receipt만 남긴다. Curation에서는 모든
새 Evidence에 생성하고, `pending` 상태의 작업을 Curation Queue로 조회한다. 완료된 작업 기록은
`workspace/task/.archive/<contract-name>/`으로 이동한다.

Inbox 검토 요청은 위 계약 작업 기록의 `requirements`로 완결하며 별도 요청 문서를 만들지 않는다. Curation Review
Card는 제안 본문·근거 스냅샷·검토 결정을 담는 결과물이므로 계약 작업 기록에 흡수하지 않고 안전한 참조만 남긴다.
작업 기록이 Review 카드·Bundle·결정 Receipt를 만들어내는 것은 아니다. 해당 결과물은 Curator·Reviewer·Publication
단계가 실제 Gate를 통과해 성공했을 때에만 생성된다. 그 뒤 계약 작업 기록은 결과물의 안전한 참조와 다음 상태를
기록한다.

## 정본과 변경 원칙

- `OPERATING_RULES.md`는 승인·보안·의미 변경 Gate와 금지 사항의 정본이다. 특히 Curation은
  `RB-ROUTE-015~016`, `RB-CUR-001~010`을 따른다.
- 각 `agent-rules/*.md` Profile은 해당 단계의 입력·Check·Gate·실패 처리를 정한다.
- 이 README는 YAML 필드의 해석 안내이며, Rule을 완화하거나 자동 실행 권한을 추가하지 않는다.
- Runtime loader의 allowlist와 회귀 테스트는 실제로 지원되는 계약 형식을 검증한다. YAML만 수정해
  새로운 action·outcome·승인 경로를 만들 수 없다.

계약 파일을 추가·변경하면 Router, `OPERATING_RULES.md`, preflight와 회귀 테스트를 함께 갱신한다.
