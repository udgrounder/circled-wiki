# 외부 수집 Agent 연결 설정

외부 수집 Agent는 Wiki Runtime을 실행하거나 정책을 복제하지 않는다. Wiki Agent가 현재 설치의 계약을 조회하고, 수집 Agent는 그 계약에 따라 원문을 전달한다.

```text
Collection Agent ── 계약 조회 ──> Wiki Agent / Runtime
Collection Agent <── release·allowlist·다음 행동 ── Wiki Agent / Runtime
```

## 설정

설치 root를 수집 Agent의 `WIKI_ROOT`로 제공한다. Agent에는 `.circled-wiki/AGENT_BOOTSTRAP.md`,
`.circled-wiki/AGENT_ROUTER.md`, `.circled-wiki/OPERATING_RULES.md` 읽기만 기본 허용한다.

`.circled-wiki/collection-handoff.yaml`은 설치별 allowlist다. 기본값은 빈 목록이며 외부 handoff를 허용하지 않는다.

```yaml
schema_version: 1
collectors:
  - collector_id: support_collector
    providers: [support]
    inbox_write: true
    guidance:
      - "가능하면 원문의 출처 URL 또는 대화 맥락을 함께 보존한다."
      - "결정·제약·시점이 드러나는 원문 구간을 우선 수집한다."
```

변경 뒤 Wiki Agent가 설치 root에서 다음을 실행해 구조를 확인한다.

```sh
circled-wiki validate-configuration
circled-wiki get-collection-handoff --collector-id support_collector
```

수집 Agent는 시작 시, Wiki release 변경 시 또는 오류 뒤에 원문·credential·활성 PII 없이 계약을 요청한다. 응답의
`collection_guidance`와 `recommended_fields`는 수집 품질을 높이기 위한 행동 지침이며, 수집 성공의 필수 조건은 아니다.
`authorization.inbox_write`가 `true`이면 `allowed_providers`의 `knowledge/inbox/<provider>/`에 **새 Markdown 파일만** 만든다.
기존 Inbox 파일, Evidence, Bundle, `workspace/`, `.circled-wiki/`는 변경하지 않는다. 파일은 기존 Inbox 형식의 필수
frontmatter(`id`, `title`, `provider`, `captured_at`, `status: pending`, `checksum`, `idempotency_key`, `why_collected`,
`intended_use`, `sensitivity_review: required`)와 `<!-- INBOX_CONTENT_START -->` / `<!-- INBOX_CONTENT_END -->`
사이의 원문을 사용한다. 원문은 사전 제한·마스킹하지 않으며, Inbox Inspection과 Data Protection이 후속 처리를 결정한다.

`authorization.inbox_write`가 `false`이면 수집 완료를 주장하지 않고 Wiki Agent에 다음 절차를 요청한다. 단, `jsonschema` 등
Wiki Runtime 오류로 계약 조회 자체가 실패해도 수집을 중단하지 않는다. 설치 설정 시 사전에 배정한 provider Inbox에 새 raw 파일을
보존하고 `pending` 정규화로 남긴다. Runtime 복구 뒤 Wiki Agent가 이를 Capture·Inspection으로 처리한다.

### 형식 밖 수집

수집 Agent는 원문을 버리거나 수집을 중단하지 않는다. 표준 frontmatter를 만들 수 없거나 수집 Agent 자체 형식이 있으면,
허용 provider의 Inbox에 원본 파일을 새로 보존하고 최소한 `collector_id`·provider·수집 시각·출처를 안전한 작업 로그에 남긴다.
Wiki Agent는 기존 `capture-file --inbox-file <provider/원본파일명>`로 그 파일을 self-contained Inbox envelope로 만들고,
이후 동일한 Inbox Inspection·Data Protection 절차를 적용한다. 형식 오류는 수집 실패가 아니라 `pending` 정규화 작업이다.

따라서 수집 Agent는 안내에 따라 출처, 시점, 결정 배경, 활용 목적을 함께 가져올 수 있으면 포함하되, 없는 정보 때문에
원문을 누락하거나 추정해서 채우지 않는다.

## 현재 지원 범위

현재 release는 allowlist와 release-aware 계약 조회를 제공한다. 수집 Agent는 허용된 provider 폴더에 새 파일을 생성하고,
기존 Inbox Inspection이 이를 처리한다. 파일 단위 승인·일회성 handoff ID·발급 경로는 사용하지 않는다. 이 경계는 원문이
Data Protection과 Inbox Inspection을 거치기 전에 Evidence·Bundle·검색에 노출되지 않게 하기 위한 것이다.

업그레이드 뒤에는 수집 Agent가 캐시한 계약을 재사용하지 말고 다음 수집 전에 다시 조회한다. 오류 로그에는 collector ID,
release ID, 오류 분류와 다음 행동만 기록하며 원문·credential·PII는 기록하지 않는다.
