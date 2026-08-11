# 외부 수집 Agent 연결 설정

외부 수집 Agent는 현재 v1 계약에 따라 원문과 수집 시점 메타데이터를 전달한다. Runtime을 실행할 수 있으면 직접 capture하고, 실행할 수 없으면 Wiki Agent가 같은 입력으로 대행한다.

```text
Collection Agent ── 안내 문서 경로 요청 ──> Wiki Agent / Runtime
Collection Agent <── 경로·버전, 필요 시 본문 ── Wiki Agent / Runtime
```

## 설정

설치 root를 수집 Agent의 `WIKI_ROOT`로 제공한다. Agent에는 `.circled-wiki/AGENT_BOOTSTRAP.md`,
`.circled-wiki/AGENT_ROUTER.md`, `.circled-wiki/OPERATING_RULES.md` 읽기만 기본 허용한다.

수집 Agent는 설치 root의 아래 문서를 읽어 현재 실행 기준을 받는다.

```sh
cat .circled-wiki/contracts/COLLECTION_HANDOFF.md
```

수집 Agent는 시작 시, Wiki release 변경 시 또는 오류 뒤에 원문·credential·활성 PII 없이 현재 메소드 스펙과 가이드 문서 경로를 요청한다.
`get-collection-handoff`은 Handoff 버전, 메소드 스펙 문서 경로와 수집 가이드 문서 경로만 반환한다. 원문 종류별 메소드명, 필수·선택 파라미터와 설명은 메소드 스펙 문서에서, 상세 품질 규칙은 수집 가이드 문서에서 참고한다.
수집 Agent는 `.circled-wiki/schemas/inbox-submission.schema.v1.json`의 입력 계약을 참고해 `capture_document`,
`capture_conversation`, `capture_file` 중 맞는 Runtime 작업을 호출한다. Inbox Markdown의 Frontmatter, content marker와
checksum은 Runtime이 생성·검사한다. 직접 실행이 불가능하면 같은 v1 입력을 Wiki Agent에 전달한다. Wiki Agent는 대행으로
동일한 capture 작업을 호출하며, 빠진 값을 추정하거나 원문을 재구성하지 않는다.

가이드는 다음 정보를 함께 수집하도록 안내한다. 이 중 누락된 값은 추정하지 않는다.

| 항목 | 수집 가치 |
| --- | --- |
| `provider`, `title`, `captured_at` | 출처·식별·시점의 기본 맥락 |
| `why_collected`, `intended_use` | 정제 우선순위와 활용 맥락 |
| `idempotency_key` | 같은 원문의 중복 수집 방지 |
| `source_url`, `source_locator` | 원문 재확인과 위치 추적 |
| `captured_from` | API·webhook·수동·업로드·동기화 등 수집 경로 |

가이드는 Notion/Slack 등 대화형 provider의 transcript 생성, 중복·재수집과 출처 맥락 보존 규칙도 포함한다. 이는 수집 Agent가
전달 전에 적용하는 규칙이다. Inbox 승인, 민감정보 검토 확정, Evidence 변환, `no_bundle`과 Bundle 정제는 Wiki 내부 운영 절차이므로
수집 Agent 안내에 포함하지 않는다.

계약 조회나 Runtime 실행 오류는 수집 Agent가 수집 시점에 보유한 원문과 메타데이터를 Wiki Agent에 전달해 대행 capture를 요청하는 사유다.
오류 응답은 빠진 필드 또는 idempotency 충돌을 식별하므로, 수집 Agent는 원문 접근이 가능한 동안 이를 보완해 재시도한다.

### 형식 밖 수집

수집 Agent는 원문을 버리거나 수집을 중단하지 않는다. 표준 Inbox 파일을 수작업으로 만들 필요는 없으며, 원문·알고 있는 출처 정보·계약 버전을
Wiki Agent에 전달하면 된다. Wiki Agent가 capture 성공·오류를 회신하고, 오류면 수집 Agent가 수집 시점의 정보를 보완한다.

따라서 수집 Agent는 안내에 따라 출처, 시점, 결정 배경, 활용 목적을 함께 가져올 수 있으면 포함하되, 없는 정보 때문에
원문을 누락하거나 추정해서 채우지 않는다.

## 현재 지원 범위

현재 release는 v1 입력 계약·Runtime 생성·Wiki Agent 대행을 제공한다. 파일 단위 승인·일회성 handoff ID·발급 경로는 사용하지 않는다. 이 경계는 원문이
Data Protection과 Inbox Inspection을 거치기 전에 Evidence·Bundle·검색에 노출되지 않게 하기 위한 것이다.

업그레이드 뒤에는 수집 Agent가 캐시한 계약을 재사용하지 말고 다음 수집 전에 다시 조회한다. 오류 로그에는 collector ID,
release ID, 오류 분류와 다음 행동만 기록하며 원문·credential·PII는 기록하지 않는다.
