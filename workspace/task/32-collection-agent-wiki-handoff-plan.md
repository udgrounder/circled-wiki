# 수집 Agent → Wiki Agent 공식 Handoff 계획서

**상태:** In progress  
**작성일:** 2026-08-11  
**적용 대상:** Circled Wiki Runtime, 설치본 Bootstrap 자산, 외부 수집 Agent Adapter  
**목적:** 수집 Agent가 오래된 규칙·의존성·실행 환경을 가정하지 않고, 시작·release 변경·오류 시 Wiki Agent의 현재 수집 계약을 조회한 뒤 허용된 새 Inbox 파일만 생성하게 한다.

> 문서 현황: `docs/02-architecture.md`, `docs/05-hermes-architecture.md`, `docs/12-runtime-architecture.md`,
> `docs/18-agent-guide.md`에는 역할·구조 설명이 분산되어 있다. 하지만 사용자가 외부 수집 Agent의 연결 방식,
> 최소 권한, 주입 지침, 장애 대응을 한 문서에서 설정할 수 있는 운영 안내서는 없다. 본 계획은 이를 별도 산출물로 만든다.

## 1. 결론

수집 Agent는 기존 Inbox Rule이 정한 provider의 새 Inbox 파일 생성 외의 `knowledge/inbox/` 변경이나 자체 Python 환경에서
Schema·민감정보 정책을 해석하지 않는다.
각 수집 작업은 아래 두 단계로 분리한다.

```text
1. handoff 계약 조회 (Agent 시작·release 변경·오류 시, 원문 없음)
   Collection Agent → Wiki Agent: 현재 공식 수집 방식·release·필수 입력 문의
   Wiki Agent → Collection Agent: versioned handoff 계약과 현재 상태 응답

2. external Inbox handoff (원문 전달)
   Collection Agent → 허용된 provider의 새 Inbox 파일: 표준 envelope·원문·출처·수집 목적·idempotency key 적재
   Runtime/Wiki Agent → Collection Agent: 기존 Inbox Inspection·Data Protection 절차로 후속 상태 처리
```

이 방식에서 Wiki Agent가 현재 release, Data Protection 정책, Schema, Inbox 전이와 Receipt를 단일 정본으로 관리한다.
수집 Agent는 전달·재시도·상태 보고만 담당한다.

### 결정 기록 (2026-08-11)

1. **외부 Agent의 Inbox 파일 생성 허용** — 외부 Collection Agent는 기존 Inbox Rule이 정한 provider에 따라
   `knowledge/inbox/<provider>/`에 새 Inbox 파일을 직접 생성할 수 있다. 기존 Inbox·Evidence·Bundle의 수정·이동·삭제는
   허용하지 않는다.
2. **원문 내용 제한 없음** — Wiki는 외부 Agent가 적재하는 원문의 내용·형식을 Capture 이전에 제한하거나 하드 마스킹을
   강제하지 않는다. 외부 Agent의 수집 규칙을 존중한다. 해당 파일은 `untrusted_external_handoff`로 취급하며 Evidence,
   Bundle, 검색, Context에는 후속 Data Protection·Inbox Inspection Gate가 끝날 때까지 포함하지 않는다.
4. **형식 밖 수집 보존** — 표준 envelope를 만들 수 없는 원문도 허용된 Inbox에 새 파일로 보존한다. 이는 실패가 아니라
   `pending` 정규화 대상이며, Wiki Agent가 기존 `capture-file --inbox-file <provider/원본파일명>`로 envelope화한 뒤 동일한 Inspection·Data Protection Gate를 적용한다.
5. **수집 행동 지침** — handoff는 기존 Inbox Rule의 위치 기준, 출처·시점·결정 맥락 등 가치 있는 자료를 더 잘 수집하기 위한
   지침과 권장 Frontmatter를 전달한다. 필수 입력이나 수집 성공 Gate가 아니며, 없는 정보는 추정하지 않고 원문을 보존한다.
6. **Runtime 장애와 수집 분리** — `jsonschema` 등 Wiki Runtime 오류로 handoff 안내를 읽지 못해도 수집 Agent는
   사전에 배정된 provider Inbox에 새 raw 원문을 보존한다. 오류는 정제 지연일 뿐 수집 차단 사유가 아니며, 복구 뒤
   Capture·Inspection으로 `pending` 정규화한다.

## 2. 배경과 문제

수집 Agent와 Wiki 관리 Agent는 서로 다른 실행 프로세스·컨텍스트를 사용한다. Wiki Runtime이 upgrade되면 수집 Agent가 이전에
읽은 규칙이나 Python 의존성 상태를 계속 가정할 수 있다. 이 상태에서 수집 Agent가 Runtime 내부 API 또는 파일 경로를 직접 사용하면
다음 문제가 생긴다.

- 현재 설치본이 요구하는 `jsonschema`·PyYAML·Schema version과 다른 환경을 사용한다.
- 새 Capture 필수 입력, 민감정보 정책, idempotency 규칙을 누락한다.
- Inbox·Evidence·Receipt 전이를 우회하거나 실패를 실제 수집 완료로 오인한다.
- upgrade 직후의 정책 변경이 다음 수집 작업에 반영되지 않는다.

## 3. 목표와 비목표

### 목표

1. 수집 Agent는 시작·release 변경·오류 시 Wiki Agent가 제공한 현재 계약을 확인한다.
2. 원문은 계약 조회 단계에 포함하지 않고, 검증된 Capture handoff에만 전달한다.
3. Wiki Agent는 설치본 launcher와 Runtime을 통해 현재 release·설정·의존성을 검사한다.
4. Capture 결과는 `intake_id`, 상태, 재시도 가능 여부와 안전한 다음 행동으로 반환한다.
5. 계약 버전 또는 release가 바뀌면 수집 Agent는 stale 계약을 재사용하지 않고 다시 조회한다.
6. 실패·차단·재시도는 공통 notification 또는 운영 Issue에 안전한 요약만 남긴다.

### 비목표

- 수집 Agent에 Wiki 정책·Schema·민감정보 판단 로직을 복제
- handoff 스펙이 허용한 새 Inbox 파일 외의 `knowledge/`, 모든 `workspace/`, `.circled-wiki/config.yaml` 직접 수정
- 계약 조회 메시지에 원문·자격증명·활성 PII를 포함
- Wiki Agent가 수집 Agent의 외부 인증·스케줄러·tmux 실행 상태를 관리
- 수집 성공을 Evidence 변환·Bundle 생성·발행 성공과 동일시

## 4. 역할과 책임

| 역할 | 책임 | 금지 |
| --- | --- | --- |
| Collection Agent | 원문 획득, 출처·수집 목적·idempotency key 작성, allowlist가 허용한 provider의 새 Inbox 파일 생성, 결과 기록·안전 재시도 | 기존 Inbox·Evidence·Bundle 수정·이동·삭제, 정책·Schema 자체 판정 |
| Wiki Agent | 현재 위치 기준·수집 안내 응답, Data Protection·Inbox Gate·Receipt 관리 | 외부 수집 스케줄러 제어, 원문 없는 안내 조회만으로 수집 완료 주장 |
| Runtime | Capture 및 상태 전이 구현 | 수집 Agent의 안내 조회에 설정·Schema 의존성을 강제 |
| 운영 사용자 | 신규 수집 source 권한, `awaiting_user` 등 사용자만 할 수 있는 판단 제공 | Agent가 대신 승인하도록 위임 |

## 5. Handoff 계약

### 5.1 계약 조회: `get-collection-handoff`

초기 구현은 Wiki Agent가 설치본 launcher를 통해 이 읽기 전용 요청을 처리한다. 이후 CLI·MCP에 동일한 read-only 명령을
추가해 대화형 문의 없이도 기계적으로 호출할 수 있게 한다.

정상 응답의 최소 계약은 다음과 같다.

```json
{
  "contract_version": "v1",
  "release_id": "v1-...",
  "operation": "collection_guidance",
  "location_rules": {
    "inbox_path_template": "knowledge/inbox/<provider>/",
    "write_policy": "new_files_only"
  },
  "recommended_fields": [
    "content", "provider", "title", "why_collected",
    "intended_use", "idempotency_key"
  ],
  "recommended_frontmatter": {
    "source_url": "가능하면 원문의 안정적 URL",
    "source_locator": "원문 내 위치 또는 외부 참조"
  },
  "next_action": "collect_to_inbox"
}
```

- `release_id`와 `contract_version`은 작업 로그에 함께 기록한다.
- 수집 Agent는 시작·release 변경·오류 시 안내를 다시 조회한다. Schema 오류가 나도 기존 Inbox Rule에 따라 raw 원문을 보존한다.
- 위치·권장 Frontmatter·raw fallback은 기존 Inbox Rule을 요약한 안내이며 수집 성공 Gate가 아니다.

### 5.2 External Inbox handoff

수집 Agent는 계약의 `location_rules`에 따라 `knowledge/inbox/<provider>/`에 새 파일을 생성한다. 권장 Frontmatter는
가능하면 포함하고, 없으면 raw 원문을 보존한다.

```json
{
  "contract_version": "v1",
  "release_id": "v1-...",
  "content": "수집한 원문",
  "provider": "approved-provider",
  "title": "안전한 제목",
  "why_collected": "수집 목적",
  "intended_use": ["적용 업무"],
  "idempotency_key": "stable-source-revision-key"
}
```

`content`는 이 단계에서만 전달한다. Wiki는 원문의 하드 마스킹 여부나 허용 내용을 Capture 이전에 판단하지 않는다.
대신 생성 파일을 `untrusted_external_handoff`·`sensitivity_review: required` 상태로 두고, 현재 Data Protection와
Inbox Inspection이 안전한 Evidence 변환 여부를 결정한다. handoff 파일은 새로운 파일만 생성할 수 있으며,
provider와 표준 Inbox envelope가 일치하면 후속 Inspection 대상이 된다.
Collection Agent는 Inbox 파일 생성 성공을 Evidence·Bundle·발행 성공으로 해석하지 않는다.

### 5.3 결과 계약

| 결과 | Collection Agent 행동 |
| --- | --- |
| `pending` | Inbox 경로·provider·contract/release ID를 기록하고 정상 종료 |
| 기존 동일 intake 재사용 | 반환된 기존 `intake_id`를 기록하고 중복 제출을 멈춤 |
| `awaiting_user` / `needs_review` | 원문을 다시 전송하지 않고 안전한 다음 행동만 사용자·공통 notification에 전달 |
| `contract_version_mismatch` / `release_mismatch` | 계약을 한 번 다시 조회한 뒤 같은 idempotency key로 재시도 |
| preflight·Runtime 오류 | 사전 배정 provider가 있으면 새 raw 파일을 보존하고 `collection_handoff_blocked` notification을 남김 |
| 알 수 없는 오류 | 원문·credential을 로그에 복사하지 않고 오류 분류·release·명령 결과 요약을 운영 Issue에 기록 |

## 6. 구현 단계

### 구현 현황 (2026-08-11)

- 완료: `get-collection-handoff` 읽기 계약은 기존 Inbox Rule의 위치 기준, 권장 Frontmatter, raw fallback을 반환한다.
  설치별 allowlist·Schema·config는 사용하지 않으며, 기존 Inbox Inspection이 후속 격리·검토를 수행한다.

### Phase 0 — 사용자 설정 문서와 현재 경계 고정

1. `docs/30-collection-agent-integration-setup.md`를 작성한다. 이 문서는 사용자·운영자를 대상으로 전체 구성도,
   Collection Agent/Wiki Agent/Runtime의 책임, 지원 transport, 설치 root 지정, 최소 권한, 주입 지침, 정상·차단·재시도
   흐름, release upgrade 뒤 재조회, 설치별 Collector allowlist 설정, untrusted external handoff의 후속 처리와 문제 해결을 설명한다.
2. 제품 `README.md`에는 위 문서로 연결되는 짧은 설정 안내와 복사 가능한 Collection Agent 주입 지침을 둔다.
3. 문서에는 설치별 절대 경로·조직명·credential을 예시 기본값으로 넣지 않는다. `WIKI_ROOT` 같은 사용자 관리 환경 변수와
   프로젝트 상대 launcher 경로만 사용한다.
4. 수집 Agent Adapter에서 `knowledge/inbox/` 직접 쓰기와 Runtime 내부 모듈 import를 inventory한다.
5. 직접 쓰기는 handoff 스펙 기반 새 파일 생성으로만 허용하고, 기존 파일 mutation 경로는 제거한다.
6. 현재 `capture_conversation` 필수 입력과 응답 및 external handoff 파일 형식을 canonical contract로 문서화한다.

**완료 조건:** 사용자가 단일 설정 문서와 README의 주입 지침만으로 수집 Agent의 대상 root·권한·공식 handoff 경계를
확인할 수 있고, 수집 Agent의 변경 권한이 allowlist가 허용한 provider의 새 Inbox 파일 생성과 안전한 작업 로그로 제한된다.

### Phase 1 — Runtime 계약 조회 구현

1. `get-collection-handoff` read-only CLI·MCP·Service 경로를 추가한다.
2. 응답은 `contract_version`, 설치 release, 공식 operation, 필수 입력, preflight 상태와 다음 행동만 반환한다.
3. 설치 로컬 `.circled-wiki/collection-handoff.yaml`과 동명 JSON Schema·Schema Registry 항목을 추가한다. 이 파일은
   `collector_id`, 허용 provider, `inbox_write`만 관리하며 upgrade에서 보존한다.
4. 조회 시 `load_settings()`·collection handoff Schema 검증·allowlist 확인을 사용하고, 실패는 구조화된 차단 결과로 반환한다.
5. `AGENT_BOOTSTRAP`, `AGENT_ROUTER`, `inbox-capture` Profile에 “수집 Agent는 계약 조회 후 스펙 기반 Inbox handoff” 규칙을 추가한다.

**완료 조건:** release upgrade 뒤 새 설치본에서 조회한 계약이 현재 history release 및 Runtime 의존성 검사 결과와 일치한다.

### Phase 2 — Capture 계약 결합

1. external handoff 파일의 `collector_id`, provider, idempotency key와 표준 Inbox envelope를 검증하는 Runtime 소비 경로를 추가한다.
2. 값이 현재 계약·allowlist와 다르면 해당 파일을 Evidence로 변환하지 않고 `contract_version_mismatch`,
   `release_mismatch` 또는 `collector_not_authorized`를 반환한다.
3. 정상 handoff는 untrusted·`sensitivity_review: required` Inbox 상태로 등록하고, 후속 Data Protection·Inbox Inspection이
   Evidence 변환을 결정한다. 외부 Agent의 원문은 이 단계에서 내용 제한·하드 마스킹을 강제하지 않는다.
4. handoff Receipt에는 contract/release/collector/handoff 식별자만 기록하며, 원문·credential·활성 PII를 복사하지 않는다.
5. idempotency conflict는 기존 `intake_id` 반환 규칙을 유지한다.

**완료 조건:** stale 계약으로는 Inbox mutation이 불가능하고, 계약 재조회 뒤의 같은 handoff는 한 번만 적재된다.

### Phase 3 — Collection Agent Adapter 전환

1. 수집 시작 시 계약 조회를 호출하고 `preflight`와 allowlist 권한이 정상일 때만 새 Inbox handoff 파일을 생성한다.
2. Collection Agent는 반환된 operation·상대 경로·handoff ID만 사용하며 내부 Python module import, 기존 파일 mutation,
   Runtime 정책·내용 제한 판단을 제거한다.
3. 작업 로그에는 source 식별자, contract/release ID, collector/handoff ID, Inbox 경로, 결과 상태만 기록한다.
4. 계약 조회·Capture 실패는 공통 notification에 `collection_handoff_blocked` 또는 `collection_handoff_retry`로 기록한다.
5. automation은 `awaiting_user`를 자동 승인하거나 원문을 반복 전송하지 않는다.

**완료 조건:** 업그레이드 전후 수집 Agent가 코드 변경 없이 현재 Wiki 계약을 재조회해 정상 수집한다.

### Phase 4 — 관측·운영 전환

1. release deployment 완료 시 `runtime_reload_required` notification을 생성한다.
2. 수집 Agent는 다음 수집 전 해당 notification 또는 release mismatch를 확인해 계약 조회를 강제한다.
3. 운영 리포트는 handoff 성공, idempotent reuse, 차단, 사용자 대기, 재시도 수를 분리해 표시한다.
4. 1개 canary Wiki에서 신규 flow를 확인한 뒤 다른 설치본에 배포한다.

**완료 조건:** Runtime upgrade와 수집 Agent의 stale 계약으로 인한 실패가 notification·Receipt·Issue 중 하나에 재현 가능하게 남는다.

## 7. 테스트와 수용 기준

1. `get-collection-handoff`는 현재 release, `v1`, 권장 수집 정보, allowlist 권한과 선택적 collection guidance를 반환한다.
2. 설정 Schema 또는 `jsonschema` 의존성이 없으면 계약 조회는 크래시하지 않고 raw 보존 fallback을 반환하며, 사전 배정 provider에는 새 raw 원문을 보존할 수 있다.
3. allowlist 밖 Collector는 정상 handoff 권한을 받지 않으며, 기존 Inbox·Evidence·Bundle을 변경할 수 없다.
4. 정상 handoff는 원문 내용 제한 없이 새 Inbox 파일 또는 raw 원문을 `pending` 정규화 대상으로 보존한다.
5. 원문에 hard PII·credential이 있더라도 handoff 파일은 Evidence·Bundle·검색·notification에 자동 노출되지 않으며,
   Data Protection·Inbox Inspection 결과 없이는 Evidence로 변환되지 않는다.
6. stale release 또는 계약 조회 실패는 정제 작업을 지연시킬 수 있어도 raw 수집을 중단시키지 않는다.
7. 정규화 뒤 동일 idempotency key 재시도는 정확히 하나의 Intake만 만든다.
8. `awaiting_user` 결과에서 Collection Agent가 원문을 재전송하거나 승인하지 않는다.
9. 계약 조회·오류 notification과 수집 로그에 원문·credential·활성 PII가 포함되지 않는다.
10. 설치 upgrade 뒤 canary Wiki에서 contract release와 `.circled-wiki/history/releases/<release>.json` asset map이 일치한다.
11. 전체 Repository Validator와 정본 전체 회귀 Gate를 통과한다.

## 8. 배포와 롤백

1. Runtime 계약 조회·Capture mismatch Gate·Agent 규칙·테스트를 하나의 제품 release로 준비한다.
2. canary 설치본에 upgrade dry-run, backup, apply, 독립 `validate-configuration`·`validate`를 수행한다.
3. canary Collection Agent는 계약 조회 → Capture → idempotent 재시도 → stale 계약 차단 시나리오를 검증한다.
4. 오류가 발생하면 Collection Agent의 Capture mutation을 중지하고 read-only 계약 조회·notification만 남긴다.
5. Runtime rollback은 Deployment Receipt의 실제 Control Plane backup만 사용하며 `knowledge/`와 `workspace/`는 rollback 대상에 포함하지 않는다.

## 9. 착수 전 결정 사항

1. Collection Agent와 Wiki Agent 사이에서 시작·release 변경·오류 시 handoff 안내를 요청·응답할 실제 transport: 승인된 메시지 Adapter, MCP Gateway 또는 동등한 원격 경로. 외부 Agent는 Runtime Python을 직접 실행하지 않는다.
2. `runtime_reload_required` notification의 delivery 대상과 acknowledgement 주체
3. handoff contract의 지원 기간·version migration·이전 수집 Agent 차단 정책
4. external handoff를 실제 Inbox 파일로 쓸 때의 원자적 생성 방식과 파일 소유권·권한 모델
