# 운영 피드백 기반 지속 개선 계획

**제품명:** Circled Wiki  
**상태:** Proposed — P0 안전조치 완료 전 운영 자동 발행 금지  
**최종 독립평가:** 2026-07-22

## 1. 목적과 적용 범위

이 계획은 실제 운영 저장소에서 발견된 이슈와 개선 요청을 Circled Wiki 원본 프로젝트의 검증 가능한 제품 개선으로
전환하고, 검증된 릴리스를 운영 저장소에 안전하게 배포하는 절차를 정의한다.

대상은 다음 두 저장소다.

| 구분 | 역할 | Source of Truth |
| --- | --- | --- |
| 원본 프로젝트 | Bootstrap, Runtime, CLI, MCP, 정책, 테스트, 배포 자산의 개발 | 제품 코드와 릴리스 규칙 |
| 운영 저장소 | 설치별 설정, 공식 지식, Evidence, Inbox, 운영 이슈, 실행 자동화 | 조직 운영 자료와 실행 이력 |

운영 저장소의 `knowledge/`, 설치별 `config.yaml`, Inbox·Evidence 원문, 자격증명, cron 환경은 원본 프로젝트로
자동 복사하거나 병합하지 않는다. 운영 이슈는 개선 후보이며, 자동 수정·자동 발행 권한이 아니다.

## 2. 즉시 안전조치

현재 운영 관찰에는 문서 유효성과 별개로 확인해야 할 보안·실행 일관성 문제가 있다. 다음 조치는 제품 개선보다 먼저
수행한다.

1. 자동 정제와 자동 발행을 일시 중지하고 수동 조회는 read-only로 제한한다.
2. 자동화가 `sensitivity_review: not_applicable` 또는 `pii_scanned: true`를 단순 기록한 Evidence를 신뢰하지 않는다.
3. 해당 Evidence를 재검사 대상으로 표시하고 원문 접근 권한, 노출 범위, 원격 Git 반영 여부를 조사한다.
4. 실제 민감정보 검사가 확인되기 전에는 재발행·재사용·공식 Bundle 승격을 중지한다.
5. 운영본의 `src/`와 `.circled-wiki/runtime/` checksum이 다르면 실행 Runtime을 확정하기 전까지 mutation 명령을 중지한다.
6. 예상하지 않은 staged·unstaged 파일이 있으면 `publish-changes`를 실행하지 않는다.

PII Scan 완료 증빙은 단순 boolean이 아니라 최소 다음 정보를 가져야 한다.

| 필드 | 의미 |
| --- | --- |
| `scanner` | 실제 검사 구현 또는 승인된 수동 절차 식별자 |
| `scanner_version` | 검사 규칙·도구 버전 |
| `scanned_at` | 검사 완료 시각 |
| `result` | 통과, 마스킹 필요, 검토 필요 등의 구조화된 결과 |
| `reviewed_by` | 인증된 사람 또는 승인된 검사 주체 |
| `receipt` | 재현 가능한 검사 결과 또는 제한된 보안 시스템의 참조 |

자동화는 실제 검사 없이 위 필드나 `pii_scanned` 값을 생성할 수 없다. 운영 원문에 민감정보가 포함됐을 가능성이
확인되면 이 문서의 일반 개선 흐름이 아니라 제한된 사고 대응 절차로 전환한다.

## 3. 운영 저장소 모델과 실행 Runtime 결정

현재 운영 저장소는 순수 설치 root와 제품 source/docs/tests를 함께 가진 운영 fork 형태다. 이 상태에서는 `src/`를
수정해도 Portable CLI가 사용하는 `.circled-wiki/runtime/`에 반영되지 않으며, 전체 staging은 제품 코드와 운영 데이터를
같은 Commit에 포함할 수 있다.

릴리스 작업 전 다음 선택을 ADR로 확정한다.

| 선택지 | 장점 | 위험·비용 | 권고 |
| --- | --- | --- | --- |
| 순수 운영 설치본으로 이전 | 제품과 운영 데이터 경계가 명확하고 upgrade가 단순함 | 초기 이전·검증 필요 | 권고 |
| 운영 fork 공식 지원 | 운영별 코드 실험이 쉬움 | source/runtime drift, 병합·발행 경계 복잡도 증가 | 명시적 유지보수 체계가 있을 때만 |

어느 모델이든 운영 명령은 하나의 canonical Runtime만 사용한다. CLI와 MCP는 시작 시 다음 정보를 보고해야 한다.

- Circled Wiki release ID
- 실행 모듈의 실제 경로
- Runtime asset checksum
- manifest checksum 일치 여부
- source/runtime 중복 및 drift 여부
- pending proposal과 충돌 자산 수

managed Runtime checksum이 manifest와 다르거나 실행 후보가 둘 이상이면 `operational-preflight`는 `ready=false`를 반환한다.

## 4. 운영 피드백 수명주기

```text
운영 이슈 기록
  -> 사용자 요청에 따른 Product Workspace 이동
  -> Archive 유사 이력 조회와 사용자 검토
  -> 원본 프로젝트 Triage
  -> 재현 테스트와 영향 평가
  -> 코드·규칙·테스트 수정
  -> 원본 릴리스 검증
  -> 운영본 upgrade 계획 검토
  -> 백업 후 Control Plane upgrade
  -> 운영 사전점검·검증·관찰
```

### 4.1 운영 저장소

1. Agent·사용자·자동화는 실제 문제를 사용자 소유 `workspace/issues/`에 기록한다.
2. 기록은 사실, 기대 결과, 실제 결과, 재현 문맥, 관련 상대 경로, 개선 가설을 분리한다.
3. 민감정보, 원문, 토큰, 고객 식별자는 이슈에 넣지 않는다.
4. 운영 이슈 상태는 `open -> triaged -> mitigated -> verified -> resolved` 또는 `wont_fix`로 관리한다.
5. Reporter·구현자·검증자를 기록하고 동일 주체의 self-verification을 허용하지 않는다.
6. `verified`에는 `fixed_release`, 실제 `deployed_release`, Deployment Receipt, 재현 결과와 독립 Verification Receipt가 필요하다.
7. 원인이 같은 이슈는 `duplicate`, 후속 이슈로 교체되면 `superseded`, 재발하면 `reopened` 관계를 기록한다.

### 4.2 원본 프로젝트

1. 사용자가 프로젝트와 Issue를 명시해 수집을 요청하면 Git 추적·커밋·미변경 상태를 확인하고
   `workspace/issues/inbox/`로 이동한다. 실패하면 원본이 남아 있는지 확인한다.
2. 사용자 검토 전에 `workspace/issues/archived/`에서 유사 occurrence, 과거 해결책·회귀 테스트·검증 결과를 찾는다.
3. 사용자가 Issue와 관계를 검토한 뒤 System Maintainer가 제품 결함, 설치별 설정, 데이터 품질, 운영 절차 문제로 분류한다.
4. 제품 결함만 원본 프로젝트의 개선 작업으로 승격한다. 승격 시 운영 이슈 ID와 재현 조건을 링크한다.
5. 원본에서 최소 하나의 실패 재현 테스트를 만든 뒤 수정한다.
6. 수정은 관련 단위·통합 테스트와 Circled Wiki Validator를 통과해야 한다.
7. 원본의 변경은 검토 후 릴리스 식별자로 묶는다. 운영 이슈를 수정했다는 이유만으로 운영 자료를 Commit하거나 Push하지 않는다.
8. 처리 완료 항목은 receipt와 복구 조건을 기록하고
   `workspace/issues/archived/YYYY/MM/YYYYMMDDTHHMMSSZ-<canonical-key>-vNNNN.md`로 이동한다.

### 4.3 운영본 배포와 확인

1. 운영자는 먼저 `bootstrap-circled-wiki --target <운영-root>`의 계획을 검토한다.
2. 계획에 `preserve_and_propose`가 있으면 사람의 병합 결정 전에는 적용하지 않는다.
3. 적용 시 기존 `.circled-wiki/`는 `.circled-wiki-backups/`에 백업되어야 한다.
4. upgrade 후 `operational-preflight`, `validate`, 관련 재현 시나리오를 실행한다.
5. 독립 검증 결과를 운영 이슈에 기록하고, 검증 전에는 `resolved`로 전환하지 않는다.

## 5. 변경 경계

| 변경 대상 | 원본 프로젝트에서 변경 | 운영 저장소에서 변경 | 자동 반영 |
| --- | --- | --- | --- |
| CLI·MCP·Validator·Bootstrap 코드 | 예 | 릴리스 upgrade로만 반영 | 아니오 |
| 운영 규칙·정책·템플릿 | 예 | 릴리스 upgrade로만 반영 | 아니오 |
| `knowledge/` Bundle·Evidence·Inbox | 아니오 | 예 | 아니오 |
| `workspace/` Issue·Agent 기록·설치별 작업 자료 | 개선용 Archive만 | 예 | 아니오 |
| 조직 ID, Agent 이름, Graphify 설정 | 기본값만 | 설치별 값 | 아니오 |
| cron·외부 수집 adapter | 계약·샘플·테스트 | 버전 고정 실행본 | 아니오 |
| 외부 자격증명·서비스 비밀 설정 | 아니오 | Git 밖의 제한된 설정 | 아니오 |
| 운영 이슈 | 개선 연결 정보만 | 원본 기록 | 아니오 |

원본 Runtime과 운영본 `.circled-wiki/runtime/`은 별도 편집 대상이 아니다. Runtime 수정은 원본에서만 수행하고
운영본에는 Bootstrap upgrade로 배포한다.

## 6. 설치별 설정 계약과 하드코딩 방지

운영 저장소에서 발견된 개선을 원본 제품에 반영할 때 조직·프로젝트·머신에 한정된 값을 코드, 템플릿, 정책 기본값에
그대로 복사하지 않는다. 해당 값은 `.circled-wiki/config.yaml`의 검증된 설치별 설정으로 모델링하고 Runtime이 설정을
주입받아 사용한다.

### 6.1 설정으로 분리할 값

| 범주 | 예시 | 처리 원칙 |
| --- | --- | --- |
| 조직 Identity | 조직 ID, 표시 이름, 기본 locale·timezone | 설치 시 입력하고 upgrade에서 보존 |
| Agent·승인 주체 | 운영 Agent, 기본 Owner, 승인 역할 | 인증 가능한 식별자 또는 역할 참조로 설정 |
| 발행 정책 | 허용 경로, 기본 branch·remote 이름, Commit·Push 분리 여부 | 안전 기본값을 사용하고 Push는 명시적으로 활성화 |
| Workflow 기본값 | 기본 Owner 후보, 신선도, 위험 등급 | 조직 Profile 설정으로 두되 Bundle의 명시값이 우선 |
| Integration | provider, 실행 command, source path, schedule, checkpoint | 상대 경로와 버전 고정 adapter를 사용 |
| 기능 선택 | Graphify, 자동 정제, 자동 발행 | 기본 비활성, Gate 충족 후 설치별 활성화 |

API key, token, password, 개인 식별정보는 `config.yaml`에 넣지 않는다. 설정에는 환경 변수명, secret manager key처럼
비밀 값 자체가 아닌 제한된 참조만 허용한다. 머신 절대 경로, 저장소 폴더명, Git remote URL에서 조직 설정을 추론하지
않는다.

### 6.2 설정 우선순위와 안전 기본값

설정 우선순위는 다음으로 고정한다.

```text
명시적인 요청별 입력
  > 검증된 설치 config.yaml
  > 조직과 무관한 제품 안전 기본값
```

- 제품 기본값에는 실제 조직명, 실제 Owner, 실제 채널, 실제 remote, 실제 머신 경로를 넣지 않는다.
- 코드의 `DEFAULT_*`는 기능을 비활성화하거나 중립적인 설치 안내를 제공하는 용도로만 사용한다.
- 운영본의 하드코딩 수정은 원본으로 그대로 cherry-pick하지 않고 설정 필드와 migration을 먼저 설계한다.
- 선택 설정이 없으면 schema에 정의된 안전 기본값을 사용한다. 현재 `workflow.default_owners`는 빈 목록,
  `publication.allowed_paths`는 `knowledge`만 허용한다.
- 설정값이 유효하지 않거나 기존 URI namespace를 바꿀 가능성이 있으면 추정하지 않고 preflight를 차단한다.

### 6.3 기존 데이터 보호와 불변 필드

`organization.id`는 Evidence·Bundle URI namespace의 일부이므로 `knowledge/`에 관리 문서가 생성된 뒤에는 불변으로
취급한다. 표시 이름은 변경할 수 있지만 ID 변경은 일반 config 편집으로 허용하지 않는다.

namespace 변경이 필요하면 다음을 수행하는 별도 승인 migration이 있어야 한다.

1. `knowledge/`와 Control Plane의 복구 지점 생성
2. Bundle·Evidence·Inbox·Runtime 참조 전체 계획 생성
3. ID와 양방향 참조를 원자적으로 변경
4. 이전 ID mapping과 rollback 정보 보존
5. 전체 Validator·검색·Workflow·질의 회귀 테스트

upgrade는 기존 `config.yaml`을 덮어쓰거나 누락 필드를 실제 조직값으로 추정하지 않는다. 새 schema가 필요한 경우
`schema_version`별 migration plan을 먼저 보여 주고, 백업 후 적용하며, 알 수 없는 extension key를 보존한다.

### 6.4 설정 검증과 회귀 테스트

원본 프로젝트의 설정 관련 변경은 다음 테스트를 통과해야 한다.

- 서로 다른 두 개 이상의 조직 ID·표시 이름·Owner·timezone으로 동일 시나리오 실행
- 한 설치의 설정이 다른 설치의 URI·검색·발행 결과에 섞이지 않는지 확인
- 기존 config로 새 Runtime을 실행하는 backward compatibility 테스트
- 새 config를 구 Runtime이 읽을 때의 명시적 실패 또는 호환 동작 테스트
- upgrade 전후 config checksum 및 의미적 설정값 불변 확인
- 기존 `knowledge/`가 있는 상태에서 `organization.id` 변경 차단 테스트
- source·template·test fixture의 실제 조직명, 머신 절대 경로, 프로젝트 전용 Owner 정적 검사
- 설정 출력과 오류 메시지에서 secret 참조와 민감 값 마스킹 확인

## 7. 외부 자동화 계약

Slack·Notion·Hermes cron처럼 저장소 밖에서 실행되는 자동화도 제품과 연결되는 지원 계약을 가져야 한다. 자격증명은
저장소 밖에 두되 adapter의 인터페이스, 버전, checksum, 테스트 fixture는 원본 프로젝트에서 관리한다.

각 자동화는 다음을 제공해야 한다.

- 고정된 Circled Wiki Runtime 경로와 기대 release
- idempotency key와 checkpoint
- 동시 실행 방지 lock과 lease 만료
- dry-run과 입력 건수·출력 건수 보고
- 부분 실패 재시도와 dead-letter 또는 `needs_review` 보존
- 민감성 검토가 필요한 항목의 사람 대기 상태
- health receipt, 마지막 성공 시각, 실패 알림
- 실제 검사를 수행하지 않는 PII·민감성 상태 자동 변경 금지

## 8. 우선 개선 TODO

이 목록을 개선 작업의 단일 진행 체크리스트로 사용한다. 각 작업을 시작하거나 완료할 때 같은 변경에서 체크 상태와
검증 근거를 갱신한다. `[x]`는 명시된 범위만 완료했다는 뜻이며, `[~]`는 하위 작업 중 일부만 완료된 진행 상태다.
상위 항목은 모든 하위 항목과 운영 배포 Gate가 완료되기 전까지 `[ ]` 또는 `[~]`로 유지한다. 체크는 작업 승인이나
자동 배포를 의미하지 않는다.

### P0 — 보안·무결성·배포 차단 항목

- [ ] **P0-01 기존 Evidence 보안 증빙 감사·격리**
  - [x] Inbox Capture 1차 마스킹과 Inspection 2차 재검사 규칙 추가
  - [x] Inbox review 결과가 `pii_scanned: true`로 자동 승계되지 않도록 차단
  - [x] 현재 Evidence checksum에 결합된 구조화 `extensions.pii_scan` 영수증 구현
  - [x] 영수증 누락·checksum 불일치 시 Validator와 Publication 차단 테스트 추가
  - [x] 운영본의 기존 boolean-only 완료 주장 메타데이터 인벤토리를 읽기 전용으로 산출
  - [~] 기존 Evidence를 실제 재검사하고 결과별로 `passed`, `masked`, `needs_review` 기록
    - [x] 운영 Agent용 [PII 재검사·격리 runbook](27-operational-pii-remediation-runbook.md) 작성
    - [ ] 운영본 Evidence에 실제 scanner 실행 및 결과 receipt 기록
  - [ ] 노출 가능성이 있는 Evidence 격리·영향 평가·보안 대응
  - [ ] 운영본에서 false attestation 회귀 테스트와 독립 검증 완료

- [ ] **P0-02 Canonical Runtime과 실행 provenance**
  - [x] release, 실행 모듈 경로, managed Runtime checksum 보고
  - [x] Runtime 변조·누락·미등록 파일과 중복 source/runtime 후보의 Preflight 차단
  - [x] mutation 전 `operational-preflight` 규칙 추가
  - [x] 운영 모델을 순수 설치본 또는 공식 운영 fork 중 하나로 ADR 확정
    - [x] 운영 책임자 결정: 공식 Circled Wiki 설치·upgrade 배포본
    - [x] ADR 문서와 release/upgrade rollback 조건 반영
      - [x] [ADR-001 installed runtime distribution](26-adr-installed-runtime-distribution.md) 작성
  - [ ] 운영본 upgrade 후 canonical Runtime 단일성 검증

- [ ] **P0-03 설치별 설정 계약과 backward compatibility**
  - [x] 조직 중립적 안전 기본값과 config 우선순위 정의
  - [x] Workflow 기본 Owner와 Publication 허용 경로를 config에서 로드
  - [x] `organization.id` 불변성과 기존 namespace 혼합 차단
  - [x] 기존 config 누락 필드의 안전 기본값 회귀 테스트
  - [~] config schema version별 migration plan 구현
    - [x] schema_version 없는 legacy config를 파일 변경 없이 v1 의미로 읽는 in-memory migration 구현
    - [ ] version별 명시적 on-disk migration·checksum·rollback receipt 구현
  - [~] 서로 다른 두 개 이상 설치의 설정·URI·검색·발행 격리 테스트
    - [x] 두 설치의 config·Inbox URI 격리 회귀 테스트
    - [ ] Bundle 검색·발행 및 remote 경계의 다중 설치 격리 테스트
  - [~] upgrade 전후 config checksum과 의미적 값 보존 테스트
    - [x] YAML 레이아웃·누락 기본값과 무관한 effective config semantic checksum 구현
    - [ ] 실제 upgrade 전후 checksum·의미 값·rollback receipt 회귀 테스트
  - [~] 실제 조직명·절대 경로·전용 Owner 하드코딩 정적 검사 자동화
    - [x] 설치 config 값 기반 source/Agent 규칙 정적 감사기와 회귀 테스트 구현
    - [ ] CI·upgrade preflight에서 허용 목록과 함께 실행하고 운영본 결과를 검토

- [ ] **P0-04 Bundle 후보 자동 생성·검토 상태와 Draft → Active Gate**
  - [x] 저장 위치를 별도 임시 폴더가 아닌 `knowledge/bundles/`로 결정
  - [x] 자동화 경계를 신규 `status: draft` + `extensions.review_state: pending` 후보 생성까지로 결정
  - [x] 기본 검색·질의·Workflow 실행에는 `active` Bundle만 사용하고 후보 Draft는 제외하기로 결정
  - [x] `dawn-curation`은 Evidence 파일을 복제하지 않고 LLM Curator가 읽고 정제한 후보를 생성하기로 결정
  - [~] LLM Curation 파이프라인 구현
    - [x] LLM 자유 형식 응답을 저장하지 않는 typed JSON 출력 계약과 입력 Evidence ID 정확 일치 검증 구현
    - [x] provider·model·command·timeout·재시도·입력 크기의 typed config 및 기본 비활성 상태 구현
    - [~] 설치별 adapter 실행기·timeout/retry를 Core Curation API에 연결
      - [x] config command를 shell 없이 실행하고 typed JSON·timeout·retry·disabled `needs_review` 경로 구현
      - [~] 실패 health receipt 영속화와 비용/토큰 사용량 수집
        - [x] 성공·차단·실패 결과에 Evidence checksum, provider/model, profile, prompt/schema version, 시작·완료 시각을 포함한 안전한 구조화 receipt 기록
        - [x] bounded configured batch의 생성·재사용·no_bundle·차단·실패·needs_review 건수와 미확인 usage 상태 보고
        - [ ] adapter가 서명 또는 검증 가능한 token/cost usage receipt를 제공할 때 실제 사용량을 검증·집계
    - [ ] Evidence Original과 capture context를 읽되 원문 지시를 Untrusted Input으로 취급
    - [ ] 핵심 사실·결정·반복 절차·적용 범위·제약·미해결 사항을 추출하고 근거 부족을 구분
    - [ ] `no_bundle`, `policy`, `guide`, `runbook` 중 결과를 선택하고 선택 근거를 기록
    - [ ] 원문 전체 복사 대신 중복을 제거한 제목·요약·실행 가능한 curated Body 생성
    - [ ] `policy`는 적용 범위·규칙·예외·책임·검토 조건을 구조화
    - [ ] `guide`는 목적·적용 대상·핵심 설명·예시·주의사항을 구조화
    - [ ] `runbook`은 입력·순서화된 Step·검증·실패 처리·승인·완료 조건을 구조화
    - [ ] 참조한 기존 Evidence URI만 Frontmatter `evidence` 배열에 기록하고 Body에는 원문을 복제하지 않음
  - [~] Evidence 메타데이터와 후보 이름 생성 경로를 Core API로 통합
    - [x] 기존 제안 경로에서 Evidence ID를 파일 경로·원본 stem·UUID prefix로 역산하거나 glob 검색하지 않고 `find_document_by_id`로 해석
    - [x] Bundle 제목은 확인된 Evidence Record title과 LLM Curator의 정제 결과에서 만들고, title을 읽지 못하면 후보 생성을 차단
    - [x] 파일 slug는 사용자 표시 제목이나 Bundle ID가 아니라 안전한 ASCII path segment로 정규화
    - [x] slug 충돌 시 이미 존재하는 경로를 덮어쓰지 않고 안정적인 Evidence checksum suffix와 전체 Bundle UUID로 구분
    - [x] Evidence UUID·Bundle UUID의 앞 8자는 식별, 파일 탐색, 중복 판정, 역참조, slug 충돌 회피에 사용하지 않음
    - [ ] 축약 UUID는 사람이 보는 보조 표시에만 허용하며, 항상 전체 URI 또는 전체 UUID를 함께 제공
    - [ ] 외부 자동화와 기존 후보에서 `uuid[:8]`·prefix 기반 이름 생성 사용처를 인벤토리하고, 전체 ID 기반 매핑으로 이전
    - [ ] title·slug·경로·Bundle ID의 관계와 최대 길이를 단위·통합 테스트로 고정
  - [x] LLM 출력 계약을 JSON 또는 typed object로 정의하고 자유 형식 Markdown 직접 저장 금지
    - 필수 출력: `action`, `domain`, `bundle_type`, `title`, `summary`, `body`, `evidence_ids`
    - 보조 출력: `rationale`, `limitations`, `existing_bundle_candidates`, `confidence`
  - [x] LLM이 반환한 Evidence ID가 입력 허용 목록과 정확히 일치하는지 검증하고 임의 URI 생성을 차단
  - [x] 생성 Body의 PII·자격증명 재검사와 Prompt Injection 영향 검사를 수행
    - [x] 저장 전 credential·PII 형태·prompt injection rule-based Gate와 회귀 테스트 구현
  - [x] LLM 실패·timeout·schema 오류·근거 부족 시 부분 Bundle을 저장하지 않고 `needs_review` 제안으로 보존
    - adapter 오류는 원문·오류 전문 없이 checksum/profile 결합 `extensions.curation_attempt` receipt로 기록
  - [x] Model provider·model ID·실행 command·timeout·재시도·최대 입력 크기를 typed config로 분리
    - 실제 조직명, Agent 이름, 머신 경로, provider 자격증명은 제품 기본값에 하드코딩하지 않음
    - [x] 모델 미설정 시 자동 후보 생성 설정을 안전하게 비활성화
    - [ ] 모델 미설정 시 비변경 제안만 수행하는 실행 경로 연결
  - [x] LLM 호출 전후 checksum, model/version, prompt template version, 결과 schema version을 Curation Receipt로 기록
  - [x] 동일 Evidence checksum과 Curation Profile 버전의 재실행은 기존 후보를 재사용
  - [~] 후보 생성 수 상한·비용·토큰 사용량과 Batch별 성공·차단·실패 건수를 보고
    - [x] 1~1000 범위의 bounded batch와 결과별 건수 보고
    - [ ] adapter 제공 token/cost receipt 검증과 설치별 비용 상한 설정
  - [x] `extensions.curation` 후보 메타데이터 schema와 Validator 구현
    - [x] review 상태·검토 이력·생성자/시각/사유·병합 대상의 schema와 Validator 구현
    - [x] 실제 Curation Receipt와 Evidence checksum·recommendation 기록·검증 연결
    - [x] `generated_by`, `generated_at`, `generation_reason`, `evidence_checksum`, `curation_receipt`
    - [~] `recommendation`, `reviewed_by`, `reviewed_at`, `rejection_reason`, `merged_into`
      (reviewed_by·reviewed_at·merged_into 검증 완료, recommendation·rejection_reason 기록은 미연결)
  - [x] 후보 상태 전이 구현
    - [x] `draft + pending -> draft + needs_changes|approved`
    - [x] `draft + pending -> archived + rejected|merged`
  - [x] `draft + approved -> active + published` 전용 Owner·Security Gate 구현
    - [x] 일반 Bundle revision API를 통한 Curation 후보의 Active 우회 승격 차단
  - [x] 현재 전환 API에서 승인해도 Active로 승격되지 않는 회귀 테스트 작성
  - [x] `list-curation-candidates` CLI·MCP 조회 구현
  - [x] `review|approve|reject|merge-curation-candidate` CLI·operator MCP 구현
  - [~] 후보 정보를 사용자에게 표시
    - [x] 제목·요약·type·Evidence URI·검토 상태를 CLI/MCP 목록에 표시
    - [x] 추천 type·기존 Bundle 후보·제약/신뢰도는 Curation 결과와 함께 표시
    - [ ] 추천 domain·차단 사유를 Curation 결과와 함께 표시
  - [~] 일별 신규·병합·차단·장기 대기 후보 Digest 구현
    - [x] 현재 후보 수·검토 상태별 수·장기 대기 후보를 계산하는 read-only Core Digest 구현
    - [ ] 일별 신규·병합·차단 변화량과 CLI/MCP·운영 알림 연결
  - [x] 동일 Evidence ID와 checksum에 대한 후보 생성 idempotency 구현
  - [x] PII Scan Receipt, visibility, Evidence checksum, Validator를 통과한 Evidence만 후보화
  - [x] `propose-pending`의 `recommended_action`과 `blocking_conditions`를 생성 Gate로 강제
    - configured adapter는 신규 Draft 허용 제안이 아니거나 차단 조건이 있으면 adapter를 호출하지 않고 `proposal_blocked` receipt만 기록
  - [x] `no_bundle` 결과는 Evidence를 처리 완료로 오인하지 않고 사유와 재검토 조건을 기록
    - [x] typed 결과에서 `rationale`·`recheck_condition`을 필수화하고 Evidence 상태를 변경하지 않음
    - [x] checksum·Curation profile에 결합된 idempotent 운영 기록으로 영속화
  - [x] 자동화는 기존 Bundle을 직접 갱신하지 않고 `merge` 후보 관계만 기록
  - [~] 권한 있는 Reviewer와 Publication Security Review 통과 전 Active 전환 차단
    - [x] Curation 후보는 일반 revision API로 Active 전환 불가
    - [x] config Owner와 Security receipt를 강제하는 전용 Active 승격 CLI·MCP API 구현
    - [ ] 상위 인증 adapter가 확인한 사용자 주체와 config Owner를 결합
  - [~] self-approval 및 인증되지 않은 actor 회귀 테스트
    - [x] Curation 후보 생성 actor와 동일한 actor의 자기 승인 차단 회귀 테스트
    - [x] `approval.knowledge_owner` 미설정·불일치 actor·Security receipt 누락 시 Active 승격 차단 회귀 테스트
    - [ ] 상위 인증 adapter가 확인하지 않은 actor 문자열 차단 회귀 테스트
  - [ ] 후보 Draft의 Git 보존과 공식 지식 Publish를 구분하고 자동 Push 여부를 설정·권한으로 분리
  - [ ] `issue-20260722T023010Z-cddff909` 운영 시나리오 회귀 테스트
  - [ ] `issue-20260722T030134Z-8424fa0f` Evidence title 조회 실패·UUID fallback·slug 충돌 회귀 테스트
  - [ ] UUID 8자 축약 충돌·동일 prefix·잘린 UUID로 인한 잘못된 Evidence 연결 회귀 테스트
  - [ ] 운영본 자동 생성 후보 40건을 원 Evidence와 재대조하고 LLM Curation 파이프라인으로 재정제
    - 단순 복제·UUID 제목 후보는 승인 대상에서 제외
    - 유용한 자산이 되지 않는 항목은 `rejected` 또는 `no_bundle`로 분류
    - 유지 후보는 `policy|guide|runbook` 구조, curated Body, 정확한 Evidence 링크로 재작성
  - [ ] 자동 변경으로 손상된 기존 Bundle의 Evidence 목록을 별도 복구하고 Validator 정상 종료 확인

- [ ] **P0-05 발행 staging·push 권한 경계 복구**
  - [x] config 기반 allowlist 경로만 staging
  - [x] 사전 staged 변경이 있으면 자동 발행 차단
  - [x] Commit 대상이 허용 경계를 벗어나면 차단
  - [x] Commit과 Push의 명시적 API·권한 분리
    - [x] 운영 책임자 결정: 자동화 Push 권한 허용
    - [x] Commit/Push 분리 API와 branch·remote Gate 구현
      - [x] 설정 기반 disabled-by-default Push API와 current HEAD·remote·branch 검증 구현
      - [x] operator MCP/CLI transport와 commit별 Push receipt·재시도 상태 연결
  - [x] branch·remote 검증, 동시 실행 lock, Push 재시도 상태 구현
    - Push는 configured branch의 current HEAD만 허용하고 `.runtime/locks/`의 non-blocking lock을 사용
    - 실패는 `.runtime/publication/push/<commit>.json`의 `commit_pending_push` receipt로 남기며 같은 commit 재시도 때 count 증가
  - [ ] dirty tree의 허용·차단 기준과 부분 실패 복구 테스트

- [ ] **P0-06 Inbox 민감성 검토와 PII Scan 자동화 계약**
  - [x] `sensitivity_review: required` 기본값과 단계별 Gate 정의
  - [x] 실제 검사를 대신하지 않는 CLI `record-evidence-pii-scan` 구현
  - [x] operator MCP `record_evidence_pii_scan` 구현 및 read-only 모드 비노출
  - [~] Scanner adapter 인터페이스와 결과 서명·검증 방식 설계
    - [x] preserved Evidence bytes·checksum을 입력으로 하고 structured receipt만 반환하는 scanner adapter 계약 구현
    - [ ] scanner 결과의 외부 서명 검증 및 설치별 scanner health/credential 계약 구현
  - [x] 사람 결정 없는 `required` 항목의 승인·ingest·발행 차단 통합 테스트
    - required Inbox는 accept 실패·Evidence 0건·Inspection blocked를 단일 흐름으로 회귀 검증
  - [ ] 실패·재시도·`needs_review`·health receipt 관찰 기능 구현

- [x] **P0-07 구형 manifest 관리 자산 마이그레이션**
  - [x] `preserve_existing` 및 구형 marker 자산 인벤토리 산출
    - Bootstrap plan의 asset action으로 `adopt`, `preserve_existing`, `preserve_and_propose`를 구분해 반환
  - [x] 관리 자산 채택 조건과 충돌 proposal 형식 정의
    - manifest에 없지만 배포본과 checksum이 같은 파일만 `adopt`; 내용이 다르면 기존 proposal 경로로 보존
  - [x] manifest 소유권·checksum 갱신과 rollback 구현
    - `adopt`는 backup 뒤 manifest checksum만 등록하며 Control Plane backup을 rollback 기준으로 유지
  - [x] 두 번째 upgrade의 idempotency 및 사용자 수정 보존 테스트
    - `test_unrecorded_identical_legacy_asset_is_adopted_and_next_upgrade_is_idempotent`

### P1 — 운영 안정성과 품질

- [ ] **P1-01 Slack 활성 세션 수집 안정화**
  - [ ] 종료 시각 없는 활성 세션 누락 재현
  - [ ] 활성·종료 세션 checkpoint와 idempotency 구현
  - [ ] 중복·부분 실패 회귀 테스트

- [ ] **P1-02 외부 Hermes 자동화의 제품 계약**
  - [ ] adapter 버전·checksum·fixture를 원본 프로젝트에서 관리
  - [~] `dawn-curation`이 Core의 Curation API만 호출하고 Bundle·Evidence Frontmatter를 직접 편집하지 않도록 변경
    - [x] typed Curation Core 서비스/MCP API와 Agent 시작 문서 계약 구현
    - [ ] 실제 `dawn-curation` adapter fixture·checksum 검증과 direct-write 제거 적용
  - [ ] lock·lease·checkpoint·재시도·dead-letter 계약 구현
  - [ ] dry-run과 health receipt·마지막 성공·실패 알림 검증

- [x] **P1-03 Workflow 탐색과 Draft 처리 설명 정합화**
  - [x] 현재 Draft 탐색 동작 재현
    - [x] Draft가 기본 `search_knowledge` 결과에는 없고 후보 목록 API에서만 보이는 회귀 테스트
  - [x] Active 실행 조회와 Draft 검토 조회 API 분리
    - [x] `search_knowledge`/Workflow Active 경로와 `list_curation_candidates` 검토 경로 분리
  - [x] CLI·MCP·문서·테스트 용어 정합화

- [ ] **P1-04 운영 파일 배치와 Git hygiene**
  - [x] 사용자 편집 가능한 `.circled-wiki/templates/.gitignore` 관리 템플릿 추가
  - [x] 관리 영역 line 비교·영역 치환·사용자 규칙 보존 구현
  - [x] cache·backup·temp·egg-info·Obsidian UI 상태 신규 추적 차단
  - [x] Bundle의 영구 Evidence ID와 Obsidian용 `knowledge/` root 기준 Evidence 파일 링크 분리
  - [x] ID를 `bundle/{organization_id}/{filename}.md`·`evidence/{organization_id}/{filename}.md`로 단순화하고, 기존 URI ID의 dry-run/apply 참조 일괄 마이그레이션 추가
  - [x] `evidence_links`를 실제 Markdown 링크(`[표시명](evidence/...md)`)로 생성·검증하도록 변경
  - [x] `knowledge/` 루트 진입 문서는 `README.md`로 관리하고, 1-depth 폴더는 설명용 `README.md`와 탐색용 `index.md`를 둘 수 있으며, Inbox는 깊이와 무관하게 자동 index·README 생성·갱신·삭제 대상에서 제외
  - [x] 운영본에서 이미 추적된 생성물의 읽기 전용 목록 산출
    - [x] `.raw`, `.runtime`, cache, backup 등 Git tracked 생성물 후보 감사기 구현
  - [~] 검토된 untrack migration과 rollback 검증
    - [x] 기존 Bundle의 durable `evidence` URI로부터 Obsidian용 `evidence_links`를 dry-run/apply 보정하는 Core·CLI·operator MCP 경로와 unresolved Evidence 보존 테스트 추가
    - [ ] 실제 Git tracked 생성물의 untrack migration과 rollback 검증

- [ ] **P1-05 이슈 상태·독립 검증자 Gate**
  - [x] 구현자와 검증자 역할 분리 강제
  - [ ] actor를 상위 인증 주체에 결합하는 계약 구현
  - [x] fixed release와 검증 artifact 없는 `verified`·`resolved` 전환 차단

- [ ] **P1-06 질의 응답 품질 평가**
  - [~] 한국어 golden query 세트 작성
    - [x] SNS 마케팅 질의의 Active Bundle 검색·Evidence 출처와 근거 부재 결과 회귀 테스트
    - [ ] 권한·신선도·복수 도메인·근거 부족 응답 golden set 확대
  - [x] 출처·신선도·권한·근거 부족 응답 평가 기준 정의
    - [질의 응답 평가 기준](29-query-answer-evaluation.md)에 Active 상태·근거·신선도·restricted·무근거·Workflow 전환 기준 고정
  - [~] SNS 마케팅 등 실제 운영 질의 회귀 테스트 자동화
    - [x] SNS 마케팅 검색·출처·무근거 질의 회귀 테스트
    - [ ] 실제 Agent 답변 형식·출처 인용·신선도 표현 평가 자동화

- [ ] **P1-07 Evidence 정제 적체 관찰**
  - [x] Evidence→Bundle 전환율과 `new` 체류시간 측정
  - [~] Owner 없는 Draft, 상태별 후보 수, 후보 대기시간과 도메인별 질문 커버리지 측정
    - [x] 후보 상태별 수·대기시간·도메인 분포를 read-only 지표로 산출
    - [ ] Owner 없는 Draft와 도메인별 질문 커버리지를 지표에 연결
  - [x] 후보 신규 생성·승인·거절·병합 전환율 측정
    - `curation_backlog_metrics`에 UTC 일자 기준 생성·승인·보완요청·거절·병합 전환량을 포함
  - [ ] 임계치 초과 시 review task 또는 운영 Digest 생성

### P2 — 장기 호환성과 표준화

- [x] **P2-01 Frontmatter 국제화 규칙 정리**
  - [x] machine-readable field와 사용자 표시 문구 구분 원칙 확정
  - [x] 기존 혼용 필드 인벤토리와 migration guide 작성
    - [x] [Frontmatter internationalization rules](25-frontmatter-internationalization.md) 작성

- [x] **P2-02 Circled Wiki 명칭 전환**
  - [x] 사용자 노출 명칭의 legacy `Circled Wiki` 인벤토리 산출
    - [x] [legacy name inventory](24-legacy-name-inventory.md)와 사용자 표기/호환 식별자/역사 자료 분류 기준 작성
  - [x] CLI·Python package 호환 alias와 deprecation 기간 결정
    - [x] `circled-wiki` CLI alias 추가, legacy `circled-wiki` CLI와 `circled_wiki` package 유지
    - [x] 0.x compatibility 기간 및 1.0 release notice 전 제거 금지 결정
  - [x] 설치·upgrade·운영 문서의 사용자 표기 통일
    - [x] README·package·CLI alias의 기본 사용자 표기를 Circled Wiki로 전환
    - [x] legacy inventory를 compatibility·migration 문맥으로 한정하고 historical 문서 제외 기준 검토

### 8.1 최근 검증 기록

- [x] **2026-07-22 설정·namespace·Runtime provenance 묶음** — 관련 단위·통합 테스트 통과
- [x] **2026-07-22 `.gitignore` 관리 영역 묶음** — line diff, 영역 치환, 사용자 규칙 보존 테스트 통과
- [x] **2026-07-22 구조화 PII Scan Receipt 원본 구현** — 전체 107 tests 통과, Validator `validated=32 invalid=0`
- [x] **2026-07-22 운영본 PII 상태 읽기 전용 인벤토리** — `pii_scanned: true` 41건,
  `extensions.pii_scan` 0건, `pii_masked: true` 0건, 41건 모두 `sensitivity_review: not_applicable` 확인;
  원문 열람·Evidence 수정·재검사는 수행하지 않음
- [x] **2026-07-22 자동 Bundle 후보 이슈 검토** — 자동 후보 생성 요구는 수용하고 `bundles/`의
  `draft + pending` 모델로 결정; 운영본에서 후보 40건 생성, 기존 Bundle 1건 자동 변경, 구조가 손상된 Evidence
  참조로 Validator가 `unhashable type: 'dict'`로 중단되는 현상 확인; 운영본 파일은 수정하지 않음
- [x] **2026-07-22 LLM Curation 방향 결정** — `dawn-curation`이 Evidence를 읽어 핵심을 추출하고
  `policy|guide|runbook|no_bundle`을 판단한 뒤 curated Body와 정확한 `evidence` 참조를 가진 검토 후보를 생성하도록
  계획 확정; Evidence 파일·원문 전체 복제 방식은 허용하지 않음
- [x] **2026-07-22 Evidence metadata·slug 이슈 검토** — Evidence ID를 파일명으로 역산하는 외부 자동화의
  title 조회 실패와 UUID fallback 후보명을 확인; Core의 ID 기반 조회, 안전한 slug 충돌 처리, title 미확인 시 후보 생성 차단을
  P0-04에 추가했고 운영본 파일은 수정하지 않음
- [x] **2026-07-22 UUID 축약 규칙 명시** — UUID 앞 8자는 표시 보조값으로만 허용하고 Evidence 조회·중복 판정·경로 생성·역참조에는
  전체 ID를 사용하도록 P0-04에 추가; 외부 자동화의 prefix 사용처 인벤토리와 충돌 회귀 테스트를 후속 작업으로 등록
- [x] **2026-07-22 후보 검토 Core 기반 구현** — Draft 후보 목록과 `needs_changes|approved|rejected|merged`
  검토 기록 CLI·MCP를 추가; 승인은 Active 승격이 아닌 `draft + approved`로 보존하고 malformed Evidence 참조가
  Validator를 중단시키지 않는 회귀 테스트를 추가
- [x] **2026-07-22 Curation 계약·안전 기본값 구현** — `extensions.curation` schema/validator, LLM 정형 출력과
  입력 Evidence ID 정확 일치 검증, provider·model·command·timeout 등의 비활성 기본 config를 추가; 전체 116 tests와
  기본 저장소 Validator `validated=32 invalid=0` 통과
- [x] **2026-07-22 Curation 후보화 Gate 확장** — typed adapter 결과를 Core 서비스/MCP 경계로 연결하고,
  PII Scan Receipt·visibility·Evidence Validator·checksum 기반 idempotency를 강제; 일반 revision API의 Active 우회 승격을
  차단하고 read-only 후보 Digest를 추가; 전체 122 tests와 기본 저장소 Validator `validated=32 invalid=0` 통과
- [x] **2026-07-22 단일 Owner Active Gate 구현** — 설치별 `approval.knowledge_owner`와 Security receipt를 요구하는
  Curation 후보 전용 Active 승격 CLI·MCP API를 추가; 미설정·다른 actor·일반 revision API 우회는 차단, 전체 124 tests와
  기본 저장소 Validator `validated=32 invalid=0` 통과
- [x] **2026-07-22 자유형 Agent 운영 경로 문서화** — 초기 기동 문서와 Hermes 운영 절차에 typed Curation,
  하위 Agent 위임 범위, Owner·Security Active Gate, MCP 기본/CLI 복구 경로 및 Push 보류 경계를 반영; 전체 124 tests와
  기본 저장소 Validator `validated=32 invalid=0` 통과
- [x] **2026-07-22 Commit/Push 경계 구현** — Push를 Commit에서 분리하고, 설치 config의 disabled-by-default
  remote/branch allowlist·current HEAD 검증을 거친 CLI/MCP API로 제한; 전체 128 tests와 기본 저장소 Validator
  `validated=32 invalid=0` 통과
- [x] **2026-07-22 Curation no_bundle·config 보존 보강** — no_bundle 판단을 Evidence 상태 변경 없이 checksum/profile에
  결합해 영속화하고, effective config semantic checksum을 추가; 전체 131 tests와 기본 저장소 Validator
  `validated=32 invalid=0` 통과
- [ ] **운영본 배포·독립 검증** — 아직 수행하지 않았으며 위 원본 구현 완료와 별도로 추적
- [x] **2026-07-22 구형 manifest 자산 채택 보강** — checksum이 같은 미등록 관리 자산을 backup 후 `adopt`하고,
  변경된 미등록 자산은 proposal로 보존하도록 구현; Bootstrap 단위 테스트 22건 통과.
- [x] **2026-07-22 Curation 실패 receipt 보강** — adapter timeout·출력 오류·계약/Gate 실패는 Bundle을 쓰지 않고
  Evidence의 checksum-bound `needs_review` receipt로 기록; `test_curation` 9건 통과.
- [x] **2026-07-22 Push receipt·lock 보강** — configured branch/current HEAD/remote를 검증하고 Push를 직렬화하며,
  성공·실패의 commit별 receipt와 `commit_pending_push` 재시도 상태를 구현; Publisher·settings 테스트 19건 통과.
- [x] **2026-07-22 Curation 자기승인 차단 보강** — Curation 후보 생성 actor와 동일한 actor의 review를 차단하고,
  Owner 미설정·불일치 actor·Security receipt 누락 Active 승격 차단을 회귀 테스트로 고정; 전체 153 tests,
  기본 저장소 Validator `validated=32 invalid=0`, `git diff --check` 통과.
- [x] **2026-07-22 Obsidian Evidence 링크 분리** — 당시 URI ID와 별도 파일 링크를 분리했다. 이 기록은
  현재 규칙이 아니며, 현행 canonical ID·링크 규약은 `docs/26-reference-contract.md`를 따른다;
  전체 153 tests와 기본 저장소 Validator `validated=32 invalid=0`, `git diff --check` 통과.

소스 저장소에서 처리 가능한 구현과 운영본에서만 증명 가능한 항목의 현재 경계는
[completion audit](28-operational-improvement-completion-audit.md)에 기록한다.

체크 상태를 바꿀 때는 날짜, 실제 실행한 검증, 결과, 관련 이슈·release를 이 절에 추가한다. 테스트 없이 구현만
끝난 항목이나 원본에서만 완료된 운영 항목은 상위 체크박스를 닫지 않는다.

## 9. 릴리스와 운영 배포 Gate

원본 프로젝트 릴리스 후보는 다음을 모두 충족해야 한다.

1. 해당 운영 이슈의 재현 테스트가 수정 전 실패와 수정 후 통과를 보여 준다.
2. 전체 테스트와 `PYTHONPATH=src python3 -m circled_wiki.cli validate`가 통과한다.
3. false PII attestation, 자동 `not_applicable`, Active 전환 우회, 전체 저장소 staging 회귀 테스트가 통과한다.
4. 다중 설치 설정 격리, 기존 config 호환성, 조직 namespace 변경 차단 테스트가 통과한다.
5. 실제 조직명·절대 경로·프로젝트 전용 Owner 하드코딩 검사가 통과한다.
6. release artifact와 manifest가 immutable checksum을 가진다.
7. Bootstrap 계획이 기존 운영본의 `knowledge/` Data Plane과 설치별 config를 변경하지 않음을 보여 준다.
8. 구형 manifest 소유권 마이그레이션과 재실행 idempotency를 테스트한다.
9. 변경 범위, 알려진 제한, config schema 호환성, 롤백 기준을 릴리스 노트에 기록한다.

운영본 배포 Gate는 다음과 같다.

1. 운영자가 Bootstrap 계획과 backup 경로를 검토한다.
2. 운영본의 dirty tree, staged 경로, branch, remote, Runtime provenance를 기록한다.
3. pending proposal과 `preserve_existing` 자산의 채택·보존 결정을 완료한다.
4. config schema migration 계획과 기존 설정 checksum·의미적 diff를 검토한다.
5. Control Plane backup 성공 후에만 upgrade를 적용한다.
6. upgrade 후 config와 기존 Knowledge URI가 불변인지 확인한다.
7. `operational-preflight`가 release·checksum·drift·proposal·설정·자동화 health를 확인하고 `ready=true`를 반환한다.
8. Validator와 false attestation audit가 통과한다.
9. 해당 이슈의 재현 시나리오와 한국어 질의 회귀 테스트가 운영본에서 통과한다.
10. 독립 검증자가 이슈의 `verified` 전환 근거를 기록한다.

`validated=0 errors` 또는 `ready=true` 하나만으로 배포를 승인하지 않는다. 문서 적합성, 실행 provenance, 보안 증빙,
Git hygiene, 외부 자동화 health를 각각 독립 Gate로 판정한다.

## 10. 롤백과 사고 대응

- Control Plane upgrade 실패 시 `.circled-wiki-backups/`의 직전 스냅샷으로 Control Plane만 복구한다.
- config migration 실패 시 새 Runtime을 시작하지 않고 이전 config와 Runtime을 함께 복구한다.
- 설정 오류가 기존 URI에 영향을 주었다면 새 ID 생성을 중지하고 mapping·참조 무결성을 조사한다.
- `knowledge/` Data Plane, Inbox, Evidence, 이슈 기록은 Bootstrap 롤백 대상으로 취급하지 않는다.
- 발행·Push가 예상 범위를 벗어났다면 추가 자동 발행을 중지하고 Git diff, staged 경로, 원격 Commit 범위를 먼저 조사한다.
- Commit 성공 후 Push가 실패하면 성공으로 종료하지 않고 `commit_pending_push` 상태로 기록해 동일 Commit 재시도만 허용한다.
- 이미 원격 반영된 민감정보 가능성이 있으면 일반 revert만으로 해결됐다고 판단하지 않고 Git history·clone·cache 노출 범위를 평가한다.
- 민감정보 노출 가능성이 있으면 이슈 본문에 원문을 복사하지 않고, 접근이 제한된 사고 대응 절차로 Escalation한다.

## 11. 이슈 품질과 책임 분리

System Observation은 다음 필드를 구조적으로 관리한다.

- `reported_by`, `implemented_by`, `verified_by`, `owner`
- `source_issue_ref`, `fixed_release`, `affected_release`
- 재현 명령 또는 안전한 재현 fixture
- 수정 전 결과, 수정 후 결과, 검증 시각
- 관련 test·Commit·release·upgrade receipt
- `duplicate_of`, `superseded_by`, `reopened_from`

Reporter 또는 구현자가 같은 변경을 독립 검증할 수 없다. CLI가 actor 문자열만 검사하는 경우 상위 실행 계층이 actor를
인증된 주체에 결합해야 한다. `resolved`는 운영본 재현 테스트와 독립 검증이 모두 끝난 뒤에만 허용한다.

## 12. 운영 지표와 정기 검토

매주 또는 릴리스 전 다음을 확인한다.

| 지표 | 기준 |
| --- | --- |
| `open` High/Critical 이슈 | 담당자·다음 조치·재현 상태가 있어야 함 |
| Inbox Gate 차단 건수 | 민감성 검토 대기와 구현 결함을 분리 |
| PII Scan 증빙 완전성 | boolean뿐인 완료 주장은 0건 |
| Validator 실패 | 발행 전에 0건 |
| Runtime drift | canonical Runtime 외 실행 후보와 checksum 불일치 0건 |
| 설치 config drift | upgrade 전후 기존 설정·URI의 비승인 변경 0건 |
| 프로젝트 값 하드코딩 | 실제 조직명·절대 경로·전용 Owner 검출 0건 |
| Upgrade 충돌·제안본 수 | 수동 병합 필요 항목으로 추적 |
| 외부 자동화 health | 마지막 성공, checkpoint, retry backlog, lock 상태 확인 |
| Runbook 신선도 | 만료·검토 요청 Runbook은 자동 실행하지 않음 |
| Evidence 정제 적체 | `new` 체류시간과 Evidence→Bundle 전환율 추적 |
| 질의 응답 품질 | golden query의 출처·권한·근거 부족 응답 기준 충족 |
| Commit·Push 범위 | 명시 승인된 경로와 원격 결과만 포함 |

## 13. 명칭과 호환성

공식 제품명과 사용자 표시 이름은 `Circled Wiki`로 통일한다. 기존 `circled-wiki` CLI 명령과 Python `circled_wiki`
패키지는 운영 자동화 호환성을 위해 즉시 제거하지 않는다. 새 `circled-wiki` CLI alias, 경고 없는 병행 기간,
deprecation 공지, 자동화 마이그레이션 확인 후 제거 여부를 별도 ADR로 결정한다.

문서에서는 제품을 Circled Wiki로 부르고, 기존 식별자를 언급할 때만 `legacy CLI`, `compatibility package`처럼 역할을
명시한다.

## 14. 다음 실행 순서

1. 자동 정제·자동 발행을 중지하고 false security attestation 가능성이 있는 Evidence를 재검사한다.
2. 순수 운영 설치본과 운영 fork 중 운영 저장소 모델을 ADR로 결정한다.
3. canonical Runtime과 release/checksum provenance를 구현하고 drift 시 preflight를 차단한다.
4. 설치별 config schema, 불변 필드, migration, 다중 설치 호환 테스트를 구현한다.
5. 운영본의 하드코딩 변경을 설정 필드와 제품 동작으로 분리해 원본에 반영한다.
6. 발행 allowlist, dirty tree 차단, Commit·Push 분리, Active 전환 승인 Gate의 실패 재현 테스트를 추가한다.
7. 구형 manifest 자산 채택과 proposal 처리 migration을 구현하고 두 번 연속 upgrade 테스트를 수행한다.
8. 외부 자동화 adapter 계약과 PII Scan receipt 모델을 구현한다.
9. 기존 추적 오염을 분류하고 검토된 untrack migration을 준비한다.
10. 원본 릴리스 후보의 전체 Gate를 검증한다.
11. 운영본 upgrade 계획만 생성해 config·Knowledge URI·충돌·보존·rollback 범위를 승인받는다.
12. 승인 후 Control Plane upgrade와 운영 회귀 테스트를 수행한다.
13. 독립 검증 근거를 운영 이슈에 기록한 뒤에만 상태를 `resolved`로 전환한다.

## 15. 추가 작업 사항 — 2026-07-22 운영 결정 반영

아래 결정은 운영 책임자가 확정했다. 원본 프로젝트의 기본값에는 특정 조직·Agent·머신·자격증명을 넣지 않고,
설치별 `.circled-wiki/config.yaml`과 인증된 실행 환경에서만 구체 값을 제공한다.

| 운영 결정 | 확정 내용 | 구현 경계 |
| --- | --- | --- |
| Curation 실행 | 자율형 상위 Agent가 필요 시 다른 Agent를 호출하여 수행 | 외부 Agent는 Core CLI/MCP의 typed Curation API만 호출하고 Bundle/Evidence Frontmatter를 직접 수정하지 않는다. |
| Active 승인 | 사용자 1명이 승인 | 인증된 사용자 주체를 `knowledge-owner` 승인자로 결합한다. self-approval, 단순 actor 문자열, 자동 Active 승격은 허용하지 않는다. |
| 운영본 수정 | 현재 운영 중인 Agent가 수행 | 원본은 실행 계획·검증 도구·rollback 절차를 제공하고, 운영 Agent가 실제 Evidence 재검사·격리·수정을 수행한다. |
| 저장소 모델 | 설치·upgrade 배포본 | 운영본은 공식 Circled Wiki 배포본의 Control Plane으로 취급하며, upgrade는 preflight·backup·checksum 검증 뒤에만 수행한다. |
| Git Push | 자동화에 Push 권한 부여 | Commit과 Push API·권한·remote/branch 검증은 분리하고, Push 결과와 재시도 상태를 receipt로 남긴다. |
| Agent 인터페이스 | 자유형 Agent가 CLI, MCP 서버, 작업 폴더 및 하위 Agent 호출 사용 가능 | MCP를 기본 구조화 인터페이스로, CLI를 배치·복구 경로로 제공한다. 하위 Agent는 lock/lease/checkpoint 계약을 지킨다. |

### 15.1 구현 체크리스트

- [ ] **승인자 인증·Active Gate**
  - [~] 설치 설정 또는 인증 adapter에서 단일 `knowledge-owner` 승인자를 식별한다.
    - [x] 설치별 `approval.knowledge_owner` 설정과 빈 값의 안전한 기본 차단 상태 구현
    - [ ] 인증 adapter가 확인한 사용자 주체와 설정 Owner를 결합
  - [x] `approved` 후보를 Active로 전환하는 전용 API를 구현하고 Owner 승인 및 Security Review receipt를 강제한다.
  - [~] 인증되지 않은 actor·self-approval·일반 revision API 우회 승격 회귀 테스트를 추가한다.
    - [x] 일반 revision API 우회 승격 차단
    - [x] 생성 actor의 자기 승인 차단
    - [x] Owner 미설정·불일치 actor·Security receipt 누락 차단
    - [ ] 상위 인증 adapter 미확인 actor 차단

- [ ] **자율형 Agent와 하위 Agent 계약**
  - [ ] `dawn-curation`/외부 Agent adapter가 typed Curation MCP/CLI API만 호출하도록 fixture와 checksum 계약을 구현한다.
  - [~] 모델 호출 adapter의 provider, model, command, timeout, retry를 설치 config에서 로드하고 health receipt를 기록한다.
    - [x] provider, model, command, timeout, retry를 설치 config에서 로드
    - [ ] health receipt 영속화
  - [ ] 하위 Agent 작업의 lock, lease, checkpoint, retry, dead-letter와 dry-run을 구현한다.

- [ ] **운영본 PII 재검사 작업 패키지**
  - [~] 운영 Agent가 실행할 read-only inventory·scanner 입력·결과 receipt·격리·rollback runbook을 생성한다.
    - [x] 운영본 boolean-only PII 상태 read-only inventory 산출
    - [x] PII 재검사·격리·rollback runbook 작성
    - [ ] 운영 scanner 입력 패키지와 결과 receipt 실행 묶음 생성
  - [ ] 운영 Agent가 기존 Evidence를 재검사하고 `passed|masked|needs_review` 결과 및 영향 평가를 기록한다.
  - [ ] 보안 담당자가 운영본 결과를 독립 검증한 뒤 false attestation 이슈를 종료한다.

- [ ] **설치·upgrade 배포 절차**
  - [~] 설치 배포본 모델을 ADR로 확정하고 source/runtime checksum, config migration, backup/rollback receipt를 묶는다.
    - [x] 설치 배포본 모델 ADR 확정
    - [x] source/runtime checksum 기반 preflight와 backup 후 upgrade 구현
    - [ ] 명시적 on-disk config migration과 rollback receipt 구현
  - [ ] 운영본 upgrade 후 canonical Runtime 단일성, config 의미 보존, URI·검색·발행 격리 회귀 테스트를 수행한다.

- [ ] **Push 권한 운영 경계**
  - [x] Commit과 Push를 별도 MCP/CLI API로 분리하고 branch·remote allowlist 및 동시 실행 lock을 강제한다.
  - [~] Push 성공·실패·재시도·`commit_pending_push` 상태를 receipt로 기록하고 부분 실패 복구 테스트를 추가한다.
    - [x] 성공·실패의 commit별 receipt와 `commit_pending_push` 재시도 상태 구현
    - [ ] dirty tree와 부분 실패 복구 운영 테스트

- [ ] **Agent 사용 경로 문서화**
  - [x] Hermes 등 자유형 Agent의 MCP 기본 경로와 CLI 배치/복구 경로를 운영 entrypoint에 명시한다.
  - [x] Agent가 작업 폴더에서 읽을 초기 기동 문서에 하위 Agent 호출 범위, 권한, PII/Active/Push Gate를 추가한다.
