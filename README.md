# Circled Wiki

이 저장소는 조직의 내부 지식과 이를 운영하는 Circled Wiki 설계를 함께 보관하는 Git 기반 기준 저장소다.

`circled-wiki`가 유일한 CLI 이름이고 `circled_wiki`가 유일한 Python package 이름이다.

## 목적

- 지식 저장소(Obsidian Vault)를 프로젝트 루트 아래에 둔다.
- 설계 문서, 운영 규칙, 런타임 구조를 함께 버전 관리한다.
- 저장소 전체를 Git으로 관리하여 유실 없이 복원, 유지보수, 이력 추적이 가능하게 한다.

## 루트 구조

```text
circled-wiki/
├── AGENTS.md
├── PRODUCT_ENGINEERING_RULES.md
├── product-agent-rules/
├── OPERATING_RULES.md
├── agent-rules/
├── README.md
├── docs/
├── knowledge/
└── workspace/
```

## 핵심 원칙

- 루트 Git 저장소 전체가 복구 단위이며 Knowledge Source of Truth는 Git Repository다.
- 실제 지식 볼트는 `knowledge/` 폴더다.
- 설계 기준 문서는 `docs/` 폴더다.
- 이 source repository의 Product Agent는 `PRODUCT_ENGINEERING_RULES.md`와 `product-agent-rules/`를 사용한다.
- 설치본 Runtime Agent의 배포 원본은 `OPERATING_RULES.md`, `.circled-wiki/AGENT_ROUTER.md`와
  `agent-rules/`이며 Product Profile을 설치본에 배포하지 않는다.
- `workspace/`는 제품 작업·운영 Issue 개선 이력을 위한 Working Plane이며 공식 지식이 아니다.
- 구현체는 `src/circled_wiki/`에 두며 Core, CLI, MCP, worker의 책임을 분리한다.
- 저장소 문서, 설정, 예시는 절대 경로 대신 프로젝트 루트 상대 경로를 사용한다.
- `knowledge/bundles/`와 Evidence Record, `.circled-wiki/templates/`, `.circled-wiki/schemas/`, `.circled-wiki/policies/`의 관리 문서는 YAML Frontmatter가 있는 OKF 구조를 유지한다.
- 용어의 규범적 의미는 `OPERATING_RULES.md`의 Terminology Contract를 따른다.
- `knowledge/inbox/`, `knowledge/.raw/`, `knowledge/evidence/`에는 `pdf`, `xlsx`, 이미지 등 비Markdown 원본도 들어올 수 있다.

## 주요 경로

- 설계 문서: `docs/`
- 지식 저장소: `knowledge/`
- 전역 운영 규칙: `OPERATING_RULES.md`
- 작업별 Agent Rule Profile: `agent-rules/`
- 제품 Agent 규칙: `PRODUCT_ENGINEERING_RULES.md`, `product-agent-rules/`
- 제품 Issue 작업 큐: `workspace/issue/`
- 처리 중 원본/임시 상태: `knowledge/.raw/`
- MVP 이후 작업: `docs/13-future-work.md`
- 사람 사용자 가이드: `docs/17-human-guide.md`
- AI Agent 실행 가이드: `docs/18-agent-guide.md`
- 전역 운영 규약·Reference Traceability: `OPERATING_RULES.md`
- Codex 루트 지침: `AGENTS.md`
- Claude 루트 지침: `CLAUDE.md`
- Hermes 루트 지침: `HERMES.md`

## 운영 방식

1. 사람은 Obsidian으로 `knowledge/`를 연다.
2. 저장소 전체는 Git으로 관리한다.
3. 문서 변경, 지식 변경, 운영 규칙 변경을 모두 같은 저장소에서 추적한다.

## 빠른 시작

프로젝트 루트에서 실행한다. 현재 구현은 별도 서버 설치 없이 `PYTHONPATH=src`로 실행한다.

```sh
# 구현 및 기존 지식 문서의 적합성 확인
python3 -m pytest
PYTHONPATH=src python3 -m circled_wiki.cli validate
```

`validated=<수> invalid=0`이면 현재 관리 문서가 OKF 최소 규칙과 설치별 Organization Profile을 통과한 상태다.

## 사람 운영 가이드

### 1. 원본을 Evidence로 보존

1. 처리할 원본 파일을 `knowledge/inbox/<provider>/`에 소스별로 넣는다.
2. 아래 명령을 실행한다. `provider`에는 수기 입력이면 `manual`을 사용한다.
3. 출력된 Evidence URI를 다음 단계에서 사용한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli ingest-evidence \
  --provider manual \
  --file knowledge/inbox/manual/refund-policy.txt \
  --title "예약 환불 정책 원본" \
  --why-collected "환불 정책 Bundle을 갱신하기 위한 근거" \
  --intended-use refund-policy \
  --source-url "https://source.example/refund-policy" \
  --source-locator "page=12;section=Refund"
```

`--source-url`과 `--source-locator`를 알면 반드시 기록한다. 이후 Hermes와 MCP는 외부 원문 URL과
위치를 1차 근거로, 로컬 Evidence URI·보존 원본을 검증용 보조 근거로 반환한다. 성공하면 원본은 `knowledge/evidence/<provider>/<YYYY>/<MM>/<DD>/`로 이동하고, 같은 basename의
`.md` External-file Evidence Manifest가 생성된다. 처리 중에는 `.raw/`를 거치며, 10MiB를 넘는 원본은 Git에 넣지 않고
`.raw/`에 보존한다. 외부 저장소에 보관한 후 External-file Evidence Manifest를 별도로 처리해야 한다.

Codex·Hermes가 네이티브하게 생성한 대화처럼 Obsidian에서 직접 읽어야 하는 UTF-8 텍스트는 단일
self-contained Markdown으로 수집한다. `capture-conversation`은 원문과 수집 메타데이터를
`inbox/<provider>/`에 적재하고 `pending` 영수증만 반환한다. 이 단계에서는 Evidence 변환, 정제 제안,
전체 저장소 테스트를 실행하지 않는다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli capture-conversation \
  --provider codex \
  --file conversation.md \
  --title "디지털 메뉴 이미지 생성 대화" \
  --why-collected "작업 Outcome과 Runbook 개선 근거" \
  --intended-use ai-digital-menu-image-production \
  --idempotency-key "thread-123:turns-1-14" \
  --sensitivity-review completed
```

별도 Scheduler나 Agent가 검사, 승인, Evidence 변환과 정제를 각각 실행한다. 검사는 읽기 전용이며,
승인은 실제 검사자 actor를 기록한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli inspect-inbox --limit 100
PYTHONPATH=src python3 -m circled_wiki.cli accept-inbox \
  --intake inbox://<organization-id>/codex/<intake-uuid> \
  --actor inspection-agent
PYTHONPATH=src python3 -m circled_wiki.cli ingest-accepted --limit 100
PYTHONPATH=src python3 -m circled_wiki.cli propose-pending --limit 100
```

변환된 Embedded Evidence는 Frontmatter와 원문을 한 `.md` 파일에 저장한다. checksum은 파일 전체가 아니라
`ORIGINAL_CONTENT` 마커 사이의 불변 원문만 검증한다. PDF·이미지·스프레드시트와 외부에서 받은 기존
파일은 기존 Evidence Original+External-file Evidence Manifest 방식을 유지한다. `--sensitivity-review` 기본값은 `required`이며 실제 검토가
끝난 경우에만 `completed`로 지정한다.

Notion·Slack 등 외부 연동체는 인증값을 이 저장소에 저장하지 않고, 수집한 원문을 공통 Inbox 계약으로
전달한다. 외부 문서는 `capture-document`를 사용해 source URL과 locator를 함께 보존한다.
일정 실행기는 `circled_wiki.integrations.collector.CollectedItem`과 `collect_items`를 사용해 전일 변경
목록을 provider별 `pending` Inbox Item으로 바꾸고 Capture Receipt를 반환한다. Notion API 호출·토큰 보관·실제 스케줄은 이 경계 밖의
Adapter가 담당한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli capture-document \
  --provider notion \
  --file changed-page.md \
  --title "변경된 고객 응대 절차" \
  --why-collected "전일 변경된 Notion 문서 수집" \
  --intended-use customer-support \
  --idempotency-key "notion:page-123:revision-456" \
  --source-url "https://www.notion.so/page-123" \
  --source-locator "page_id=page-123"
```

이미 Evidence로 변환됐지만 정제 호출을 놓친 항목은 다음 Batch 명령으로 다시 제안할 수 있다.
동일 상태에서는 결과가 반복 가능하며, 공식 Bundle은 자동 변경하지 않는다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli propose-pending --limit 100
```

### 2. Evidence를 검토하고 Bundle 초안 만들기

먼저 기존 Bundle을 갱신할지 신규 Bundle을 만들지 검토한다. 이 명령은 파일을 수정하지 않는다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli propose-update \
  --evidence evidence://<organization-id>/manual/2026/07/10/<source-uuid>
```

`policy`, `guide`, `decision`, `spec`, `reference`, `report`는 신규 공식 지식 후보로 직접 Draft를 생성할 수 있다. `--evidence`에는
위에서 생성된 URI를 그대로 넣는다. `manual`과 `runbook`은 아래 자동 정제와 같은
Review 카드·독립 승인 흐름을 사용한다. 직접 생성한 Draft도 `active` 전환 전에는 동일한 Review·독립 Owner
승인·Security Gate를 거쳐야 한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli create-bundle \
  --domain cs \
  --slug refund-policy \
  --title "예약 환불 정책" \
  --type policy \
  --summary "예약 취소와 환불의 기준을 설명한다." \
  --evidence evidence://<organization-id>/manual/2026/07/10/<source-uuid>
```

생성된 Bundle은 `draft` 상태다. 본문을 Obsidian에서 보완한 뒤 항상 검증한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli validate
```

자동 정제가 만든 후보는 `draft`와 `extensions.review_state`로 별도 관리하며, 기본 지식 조회에는 포함되지 않는다.
후보를 확인하고 검토 기록을 남길 수 있다. `approve`는 Active 전환이 아니라 검토 완료 상태만 기록하며, Active 전환은
Owner와 Publication Security Gate를 통과하는 별도 작업이다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli list-curation-candidates
PYTHONPATH=src python3 -m circled_wiki.cli review-curation-candidate \
  --bundle knowledge://<organization-id>/cs/refund-policy_<bundle-uuid> \
  --action approve \
  --actor <reviewer-id>
```

외부 Curator가 야간에 처리한 결과는 Bundle 대신 Git 추적 검토카드 `knowledge/curation-reviews/`에 먼저 저장된다.
카드는 Evidence ID·상대 경로·checksum을 함께 기록하며, `approve` 전에는 Bundle을 만들지 않는다.
신규 Draft Bundle 생성 승인이 성공하면 승인 정보는 Bundle의 Curation metadata로 옮기고 소비된 검토카드는 삭제한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli list-curation-reviews
PYTHONPATH=src python3 -m circled_wiki.cli decide-curation-review \
  --review review-<id> --action approve --actor <reviewer-id>
```

자동 정제 결과는 유형·신뢰도와 무관하게 항상 `curation-reviews/` Review 카드로 먼저 생성된다.
`manual`과 `runbook`은 Review 카드와 독립 Owner 승인을 거쳐야 Draft를 만들 수 있다.
`policy`, `guide`, `decision`, `spec`, `reference`, `report`는 Evidence·PII Gate를 통과한 경우 직접 Draft 생성도 가능하지만,
모든 Draft의 `active` 전환은 Owner·Security Gate를 거친 전용 Promotion만 사용한다.

### 3. 지식 조회

```sh
# 키워드 검색
PYTHONPATH=src python3 -m circled_wiki.cli search --query 환불

# 특정 종류만 검색
PYTHONPATH=src python3 -m circled_wiki.cli search --query 환불 --type policy

# Bundle 전문 읽기
PYTHONPATH=src python3 -m circled_wiki.cli read-bundle \
  --bundle knowledge://<organization-id>/cs/refund-policy_<bundle-uuid>
```

### 4. Workflow로 작업 준비 및 결과 환류

실행 Runbook은 `knowledge/bundles/<domain>/runbooks/`에 저장한다. 활성 `runbook`은
`extensions.workflow`에 필수 입력, 단계, 승인 지점, 완료 기준을 가진다. Hermes 또는
운영자는 사용자 요청에 맞는 실행 가능한 Runbook을 찾고 공식 지식과 분리된 Runtime Task를 만든다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli find-workflow --request "이벤트 포스터를 만들고 싶어"

PYTHONPATH=src python3 -m circled_wiki.cli prepare-task \
  --workflow poster-production \
  --request "여름 이벤트 포스터를 만들어줘" \
  --inputs '{"audience":"가족 캠퍼"}'
```

만료된 Runbook이면 `prepare-task`는 원래 업무 대신 Refresh Task를 반환한다. 사용자가 즉시 최신화를
요청하면 유효기간이 남아 있어도 아래 명령으로 검토를 시작한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli prepare-runbook-refresh \
  --workflow poster-production \
  --request "현재 정책 기준으로 최신화해줘" \
  --requested-by marketing-user
```

Refresh는 내용 변경을 강제하지 않는다. 최신 원본 비교 결과를 `update_required`, `no_change`,
`insufficient_evidence`로 기록하고, 작성 Agent와 다른 Agent의 독립 검증 및 Owner 승인을 거친다.
일반 업무 Outcome은 Inbox 검토·승인 후 Evidence로 누적되며 실패·피드백·설정 임계치가 발생하면 중복 없는
개선 Refresh Task를 생성한다.

Task는 `.runtime/tasks/`에 저장되고 Git에서 제외된다. 작업 종료 후 결과, 피드백, 학습, 대용량
산출물의 내부 참조를 Outcome Inbox로 수집하고, 승인 후 Outcome Evidence로 변환한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli record-outcome \
  --task <task-uuid> \
  --status completed \
  --summary "포스터 시안을 만들고 승인을 완료했다" \
  --learning "모바일 채널은 큰 제목을 우선한다" \
  --artifacts '[{"name":"poster.png","uri":"internal-storage://design/poster.png","availability":"metadata_only"}]'
```

결과는 `provider: hermes` Evidence가 되며, 보안 검토와 Curator 판단을 거친 뒤 Runbook 또는 관련
Bundle 개선 근거로 사용할 수 있다. 상세 모델은 [Workflow 실행 및 지식 환류 설계](docs/16-workflow-execution.md)를 따른다.

## Hermes 설치 및 초기 설정

Hermes는 저장소 구조를 직접 조작하는 대신 Knowledge MCP 또는 CLI를 사용한다. 외부 시스템
(Notion·Slack·GitHub)의 인증·수집 설정은 Hermes 운영 환경에서 담당하며 이 저장소에는 비밀값을
저장하지 않는다.

모든 Agent는 [Circled Wiki Operating Rules](OPERATING_RULES.md)를 전역 운영 단일 기준으로 사용한다. Runtime Agent는
`docs/`를 읽지 않고 전역 운영 규약과 Knowledge MCP가 반환한 공식 Bundle로 동작한다. 일반 조직 구성원은
[사람 사용자 가이드](docs/17-human-guide.md)를 사용할 수 있다.

Hermes 런타임이 루트 지침 파일을 자동으로 읽지 않는 경우 시작 프롬프트 또는 프로젝트 지침에
`HERMES.md`를 먼저 읽고 따르도록 명시한다. 설치된 프로젝트의 `HERMES.md`는
`.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`와 전역 운영 규약으로 연결한다.

### 1. 실행 환경 준비

Hermes가 실행될 머신에서 이 저장소를 checkout한 뒤, **프로젝트 루트**에서 아래를 한 번 실행한다.
Python 3.9 이상이 필요하다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install "PyYAML>=6.0" "pytest>=8.0"
python -m pytest
PYTHONPATH=src python -m circled_wiki.cli validate
```

`.venv/`는 Git에서 제외된다. 마지막 명령이 `invalid=0`으로 끝나야 MCP를 등록한다.

### 2. Hermes에 stdio MCP 등록

Hermes의 MCP 설정에 아래와 동등한 서버 항목을 추가한다. 설정 파일의 실제 키 이름은 Hermes가
지원하는 MCP 클라이언트 형식에 맞추되, 핵심은 `cwd`를 프로젝트 루트로 두고 가상환경 Python에
`PYTHONPATH=src`를 전달하는 것이다.

```json
{
  "mcpServers": {
    "example-org-knowledge": {
      "command": ".venv/bin/python",
      "args": ["-m", "circled_wiki.mcp.server"],
      "cwd": ".",
      "env": {
        "PYTHONPATH": "src",
        "KNOWLEDGE_MCP_MODE": "operator"
      }
    }
  }
}
```

위 예시는 **저장소 루트에서 Hermes를 시작하는 경우**의 상대 경로 설정이다. Hermes가 `cwd` 필드를
지원하지 않으면 Hermes 런처의 작업 디렉터리를 프로젝트 루트로 설정한다. 기계별 절대 경로를 저장소에
기록하거나 API 키를 `env` 예시에 추가하지 않는다.

`KNOWLEDGE_MCP_MODE`의 기본값은 `read_only`다. 위 `operator` 설정은 저장소와 `.runtime/`에 쓰는 Hermes
또는 Hermes가 작업 범위·기간을 한정해 위임한 내부 Agent 실행 컨텍스트에 사용한다. 일반 소비자 MCP에는
이 값을 설정하지 않으며, 정식 사용자 인증이 도입되기 전에는 외부 네트워크 서비스로 노출하지 않는다.

### 3. 연결 확인

Hermes를 재시작한 후 MCP 클라이언트에서 `tools/list`를 호출한다. 아래 Tool이 표시되면
초기 설정이 완료된 것이다. 기본 read-only 모드는 아래 조회·검증 Tool 중 13개를 노출하고,
`operator` 모드는 전체 32개를 노출한다.

- `search_knowledge`
- `read_bundle`
- `prepare_context`
- `propose_update`
- `propose_pending`
- `ingest_evidence`
- `capture_conversation`
- `capture_document`
- `capture_file`
- `inspect_inbox`
- `review_inbox_sensitivity`
- `accept_inbox`
- `ingest_accepted`
- `create_draft_bundle`
- `apply_bundle_revision`
- `validate_result`
- `publish_changes`
- `find_workflow`
- `prepare_task`
- `prepare_runbook_refresh`
- `submit_runbook_reference`
- `record_reference_assessment`
- `confirm_runbook_revision`
- `audit_knowledge`
- `list_knowledge_inventory`
- `validate_claim_support`
- `measure_runbook_effectiveness`
- `get_task`
- `update_task_inputs`
- `record_task_step`
- `record_refresh_decision`
- `record_outcome`

`audit_knowledge`는 상태를 변경하지 않으므로 read-only와 operator 양쪽에서 제공된다. `tools/list` 결과를 고정 목록과
비교하기보다 현재 access mode에서 필요한 Tool이 노출되는지 확인한다.

문제가 생기면 Hermes 밖에서 같은 명령을 직접 실행해 표준 출력에 JSON-RPC 응답이 나오는지 먼저 확인한다.

```sh
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | PYTHONPATH=src .venv/bin/python -m circled_wiki.mcp.server
```

### 4. Hermes 운영 순서

1. 사용자·지정 Batch·Hermes가 원본을 `knowledge/inbox/<provider>/`에 넣는다.
2. 대화는 `capture_conversation`, URL에서 가져온 텍스트·HTML은 `capture_document`, PDF·Word·기타 파일은 `capture_file`로 적재한 뒤 `inspect_inbox`, 필요 시 `review_inbox_sensitivity`, `accept_inbox`, `ingest_accepted`를 순서대로 실행한다. URL만 저장하지 않고, 수집기가 실제로 읽은 원문과 URL·locator를 함께 보존한다.
3. `propose_pending` 또는 `propose_update`로 기존 Bundle 후보와 신규 초안을 검토한다.
4. LLM/하위 Agent Curation 결과는 먼저 Git 추적 검토카드로 저장한다. 사용자 reviewer가 `decide_curation_review`로 승인한 신규 후보만 PII-cleared Draft를 만들며, 생성 성공 후 승인 기록은 Draft로 이동하고 소비된 검토카드는 삭제한다. 기존 Bundle 보완은 expected revision을 확인한 별도 `apply_bundle_revision`으로만 적용한다.
5. 미처리 검토카드는 `list_curation_reviews`로 확인하고, 이미 생성된 Draft 후보는 `list_curation_candidates`와 `review_curation_candidate`로 검토한다. Active 전환은 설정된 `approval.knowledge_owner`가 독립된 Security receipt와 함께 `promote_curation_candidate`로만 수행한다.
6. `validate_result` 또는 CLI `validate`와 보안 게이트가 통과하면 Hermes가 변경된 `knowledge/`를 자동 Git commit하고 결과를 로그에 남긴다.
7. 사용자 작업 요청은 `find_workflow`와 `prepare_task`로 실행하고, 종료 결과는 `record_outcome`으로 `pending` Inbox에 환류한다. 이후에도 같은 `inspect_inbox -> review_inbox_sensitivity -> accept_inbox -> ingest_accepted -> propose_pending` 흐름을 적용한다.

MCP Tool은 수집·지식 변경·검증과 Workflow 실행 준비를 수행한다. `prepare_task`는 Git에서 제외된
`.runtime/`만 변경하고, `record_outcome`은 작업 결과를 Inbox에 수집한다. `publish_changes`는 전체
Validator 통과 후 `knowledge/` 변경만 자동 Git commit한다.

Draft Bundle은 기본 질의·Workflow 실행 대상이 아니다. Agent는 공식 답변과 실행에는 `search_knowledge`와
`find_workflow`의 Active 결과만 사용하고, 후보 검토에는 별도 `list_curation_candidates` 및
`review_curation_candidate` 경로를 사용한다.

제공 Tool은 다음과 같다.

| Tool | Hermes 사용 시점 | 변경 여부 |
| --- | --- | --- |
| `search_knowledge` | 관련 Bundle/Evidence 탐색 | 없음 |
| `read_bundle` | 특정 공식 지식 전문 확인 | 없음 |
| `prepare_context` | 하위 Agent에 출처 포함 문맥 전달 | 없음 |
| `propose_update` | Evidence 기반 신규/갱신 후보 생성 | 없음 |
| `propose_pending` | 대기 Evidence를 Batch로 정제 제안 | 없음 |
| `ingest_evidence` | inbox 원본을 Evidence로 수집 | `knowledge/evidence/` |
| `capture_conversation` | 대화를 소스별 Inbox에 `pending` 상태로 적재 | `knowledge/inbox/<provider>/` |
| `capture_document` | 외부 문서와 source URL·locator를 소스별 Inbox에 `pending` 상태로 적재 | `knowledge/inbox/<provider>/` |
| `capture_file` | PDF·Word·HTML 파일 등 원본 파일과 자기완결형 envelope를 소스별 Inbox에 `pending` 상태로 적재 | `knowledge/inbox/<provider>/` |
| `inspect_inbox` | 대기 대화·문서·파일의 메타데이터·경로·checksum·민감정보 Gate 검사 | 없음 |
| `review_inbox_sensitivity` | 식별된 사람이 민감정보 검토 완료·비해당 결정을 기록 | `knowledge/inbox/<provider>/` |
| `accept_inbox` | 검사자 actor와 함께 통과 항목을 `accepted`로 승인 | `knowledge/inbox/<provider>/` |
| `ingest_accepted` | 승인된 입력만 Evidence로 변환 | `knowledge/inbox/<provider>/`, `knowledge/evidence/` |
| `create_draft_bundle` | `policy`·`decision`·`spec`·`reference` 신규 Draft 생성 (`guide`/Manual·`runbook`은 Review 카드 필요) | `knowledge/bundles/`, Evidence 역참조 |
| `materialize_curation_candidate` | 내부 Curation Review 승인 처리에서만 사용하는 구현 경로; Runtime MCP에는 노출하지 않음 | `knowledge/bundles/`, Evidence 역참조 |
| `list_curation_reviews` | Git 추적 검토카드와 Evidence 위치·상태 확인 | 없음 |
| `decide_curation_review` | 승인·불필요·수정 요청을 기록하고 승인된 신규 후보만 Draft 생성; 생성 성공 시 소비된 카드 삭제 | 검토카드, Evidence, 필요 시 Draft Bundle |
| `list_curation_candidates` | Draft 후보와 검토 상태 확인 | 없음 |
| `review_curation_candidate` | 후보 검토·승인·거절·병합 기록 | `knowledge/bundles/` |
| `promote_curation_candidate` | 설정 Owner와 Security receipt로 approved 후보 Active 승격 | `knowledge/bundles/` |
| `apply_bundle_revision` | revision 충돌 검사 후 Bundle 변경 | Bundle, Evidence 역참조 |
| `validate_result` | 발행 전 전체 적합성 확인 | 없음 |
| `publish_changes` | Validator 통과 변경의 자동 Git commit | `knowledge/` commit |
| `find_workflow` | 사용자 요청과 관련 있는 실행 Runbook 탐색 | 없음 |
| `prepare_task` | Workflow 실행 상태와 누락 입력 준비 | `.runtime/` |
| `prepare_runbook_refresh` | 만료·명시적 요청 기반 Runbook 최신화 Task 준비 | `.runtime/` |
| `submit_runbook_reference` | 사용자 제공 Evidence를 Runbook 갱신 후보로 병합 | `.runtime/` |
| `record_reference_assessment` | Candidate Evidence의 독립 검증된 비교 결과 기록 | `.runtime/` |
| `confirm_runbook_revision` | Refresh 종료 전 실제 Runbook revision 증가 확인 | `.runtime/` |
| `audit_knowledge` | 지식·Evidence·최신성·열린 Task 읽기 전용 감사 | 없음 |
| `list_knowledge_inventory` | Frontmatter 기반 지식 현황 조회 | 없음 |
| `validate_claim_support` | 중요 주장과 Evidence 지원 상태 검사 | 없음 |
| `measure_runbook_effectiveness` | Outcome을 Runbook revision별로 집계 | 없음 |
| `get_task` | Runtime Task 상태 조회 | 없음 |
| `update_task_inputs` | 누락된 Workflow Definition 입력 보완 | `.runtime/` |
| `record_task_step` | 단계 실행과 사람 승인 결과 기록 | `.runtime/` |
| `record_refresh_decision` | 최신 Evidence 기반 변경·무변경·근거부족 판정 | `.runtime/` |
| `record_outcome` | 결과·결정·실행 항목·미해결 질문을 `pending` Inbox로 환류 | `knowledge/inbox/hermes/`, `.runtime/` |

Hermes가 수집한 원본과 Workflow Outcome은 `knowledge/inbox/hermes/`에 Inbox Item으로 적재한 후 같은 Inbox 검사,
Inbox Sensitive Data Review, 승인과 Evidence 변환을 거친다.
`propose_update`의 결과는 판단 보조 자료이므로, 실제 내용의 정합성 판단과 Bundle 본문 작성은 Hermes 또는
사람이 수행한다. 검증 실패한 결과는 발행하거나 Git commit하지 않는다.

## 안전 규칙

- Bundle은 반드시 하나 이상의 Evidence를 참조해야 한다.
- Evidence와 Bundle의 `curated_into` / `evidence` 참조는 양방향으로 유지한다.
- `knowledge/bundles/`의 공식 지식은 검증 없이 수정·발행하지 않는다.
- 원본·토큰·API 키·개인정보를 README, frontmatter, Git commit에 기록하지 않는다.
- `knowledge/.raw/`는 성공 시 비워지며, 실패·검토 필요·대용량 원본은 원인 확인 전까지 보존한다.
- `.raw/`와 `inbox/`는 Git에서 제외한다. 상세 보안 절차는 [Agent and Knowledge Security Policy](.circled-wiki/policies/agent-security.md)를 따른다.

## 기본 처리 흐름

`capture_conversation -> inspect_inbox -> review_inbox_sensitivity -> accept_inbox -> ingest_accepted -> knowledge/evidence/ -> propose_pending -> Curator -> knowledge/bundles/`

- 시스템 생성 대화·Outcome 텍스트: Inbox의 단일 self-contained Markdown 원문, 승인 후 단일 Embedded Evidence Markdown
- 외부 파일·바이너리: Evidence Original + External-file Evidence Manifest

`knowledge/bundles/`에 들어가는 문서는 정제된 공식 지식이며 반드시 OKF 구조를 따라야 한다.
`knowledge/evidence/`는 정제본이 아니라 원본 파일 자체를 보존하고 Bundle이 참조할 수 있는 근거 앵커를 제공한다.
10MiB 이하 외부 Evidence Original은 External-file Evidence Manifest와 함께 Git에 추적한다. 10MiB를 초과하는
Evidence Original은 Git에서 제외하고 별도 원본 저장소에 보존하며 External-file Evidence Manifest만 추적한다.

MVP 검색은 OS 파일 검색, Frontmatter 필터, Markdown 링크 추적, Evidence Record 검색으로 제공한다.

## 현재 구현된 MVP

- YAML Frontmatter 파싱과 OKF v0.1 최소 적합성 검증
- 설치별 Organization Profile 검증과 Evidence/Bundle 참조 확인
- `knowledge/inbox/<provider>/` 원본의 `.raw/` 경유, SHA-256 기록, Evidence 원본·manifest 생성
- Evidence를 근거로 하는 draft Bundle 생성 및 양방향 참조 갱신
- `rg` 우선, Python fallback 기반 키워드·Frontmatter 필터 검색
- Core를 호출하는 얇은 CLI
- 안전한 curation proposal과 stdio MCP (`search_knowledge`, `read_bundle`, `prepare_context`, `propose_update`, `validate_result`)
- 외부 scheduler에서 재실행 가능한 worker 유지보수 작업
- 실행 가능한 Runbook Profile과 Workflow 탐색
- 도메인별 `runbooks/` 배치와 목적 기반 Evidence 수집
- Business Rulebook·Inquiry·Organization Context 템플릿
- Active Bundle Owner·신선도 Governance 검증
- Git 지식과 분리된 `.runtime/tasks/` Runtime Task 상태
- 작업 결과·피드백·산출물 참조의 Outcome Inbox 환류 및 승인 후 Evidence 정제

## 다른 폴더에 운영 OS 설치·업그레이드

Agent에 대상 프로젝트 root 폴더를 지정해 설치를 요청할 때는 먼저 계획만 확인한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli bootstrap-circled-wiki \
  --target /path/to/team-knowledge
```

대화형 터미널의 최초 설치는 조직 ID, 조직 표시 이름, 운영 Agent와 Graphify 사용 여부를 질문한다. 자동 설치
스크립트에서는 네 값을 모두 명시한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli bootstrap-circled-wiki \
  --target /path/to/team-knowledge \
  --organization-id acme \
  --organization-name "Acme Corporation" \
  --operator-agent hermes \
  --graphify enabled
```

조직 ID는 URI namespace가 되므로 최초 지식 생성 전에 확정한다. 설치 후 값은 `.circled-wiki/config.yaml`에
보존되며 upgrade가 덮어쓰지 않는다. 비대화형 최초 설치에서 값을 생략하면 기본값을 추정하지 않고 실패한다.
새 설치 설정에는 `workflow.default_owners: []`와 `publication.allowed_paths: [knowledge]`가 명시된다. 기존
설정에 이 선택 항목이 없으면 같은 안전 기본값을 사용한다. 기본 Owner가 비어 있으므로 Bundle을 `active`로
발행하기 전에는 설치별 Owner를 설정하거나 문서에 명시해야 하며, 발행 경로는 설정으로 `knowledge/` 밖까지 넓힐
수 없다. 관리되는 Inbox·Evidence·Bundle ID가 생성된 뒤 `organization.id`를 변경하면
`operational-preflight`와 새 ID를 생성하는 수집·정제 작업이 차단된다.

계획을 검토한 뒤에만 `--apply`를 붙인다. 운영 템플릿·스키마·시스템 정책은 모두 `.circled-wiki/` 아래에
설치한다. 업그레이드는 `knowledge/` 아래의 기존 문서·Evidence·Bundle을 읽어 OS 소유로 등록하거나 이동, 삭제,
이름 변경, 덮어쓰지 않는다. 이전 checksum과 일치하는 Control Plane 파일만 업그레이드하고, 수정된 운영 파일은
그대로 보존한 채 새 버전을 `.circled-wiki/proposals/`에 제안본으로 둔다. 계획 보고서의 `backup_required`가
`true`이면 적용 전에 기존 `.circled-wiki/` 전체를 `.circled-wiki-backups/<기존-version>-<UTC timestamp>/`에
복사한다. 백업에 실패하면 기존 OS 파일을 쓰기 전에 업그레이드를 중단한다.

대상 root의 `.gitignore`는 사용자 규칙을 보존한다. Circled Wiki가 관리하는
`# BEGIN circled-wiki:generated-artifacts`와 `# END circled-wiki:generated-artifacts` 사이만 릴리스의 기대 line과
비교하며, 누락·변경이 있으면 해당 영역만 치환한다. 기대 목록은 Python 코드가 아니라 배포되는
`.circled-wiki/templates/.gitignore`에서 읽는다. 영역 밖의 조직별 ignore 규칙은 수정하지 않는다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli bootstrap-circled-wiki \
  --target /path/to/team-knowledge \
  --organization-id acme \
  --organization-name "Acme Corporation" \
  --operator-agent hermes \
  --graphify enabled \
  --apply
```

### 대상 폴더에서 독립 실행

설치된 대상은 원본 개발 저장소 없이 자체 Runtime을 포함한다. 대상 프로젝트 root에서 다음 명령을 실행한다.
`operational-preflight`는 설치 release ID, 실제 실행 모듈 경로, manifest checksum과 Runtime 자산 drift를 함께
보고한다. 설치 Runtime 밖에서 실행되거나 `src/circled_wiki`와 설치 Runtime이 중복되거나 checksum이 다르면
`ready=false`이며, 복구 또는 검토된 upgrade 전에는 mutation 명령을 실행하지 않는다. Upgrade가 사용자 수정
Control Plane을 보존하고 proposal을 만들면 manifest의 `pending_proposals`에 기록한다. 미해결 proposal이 있거나
Agent 진입점·Router·canonical launcher 참조가 깨져 있어도 preflight는 `ready=false`로 mutation을 차단한다.
검토자가 proposal 내용을 대상 파일에 반영한 뒤 bootstrap을 다시 적용하면 현재 release checksum을 채택하고
해결된 proposal을 manifest 대기 목록에서 제거한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py validate
python3 .circled-wiki/bin/circled-wiki.py search --query "환불 절차"
python3 .circled-wiki/bin/circled-wiki.py find-workflow --request "사용자 요청"
```

Python 3.9 이상과 `PyYAML`이 필요하다. AI Agent는 작업 시작 시
root `AGENTS.md`, `CLAUDE.md` 또는 `HERMES.md`, `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`,
`.circled-wiki/AGENT_BOOTSTRAP.md`, `.circled-wiki/AGENT_ROUTER.md`,
`.circled-wiki/OPERATING_RULES.md`, 그리고 요청에 맞는
`.circled-wiki/agent-rules/` Profile을 순서대로 읽고, 위 Launcher로 해당 프로젝트의 CLI를 호출한다.
Runtime과 Agent Bootstrap은 OS 관리 자산이므로 업그레이드 시 checksum·백업·충돌 제안 정책을 동일하게 적용한다.
`AGENTS.md`, `CLAUDE.md`, `HERMES.md`는 Agent 자동 발견용 참조 진입점이지만 OS 관리 자산은 아니다. 파일이 없으면 참조 전용으로 생성하고,
기존 파일에 `.circled-wiki/AGENT_ROUTER.md` 참조가 없으면 표시된 Circled Wiki 참조 블록만 끝에 추가한다.
실제 운영 규칙·절차·명령은 `.circled-wiki/`에만 두며 기존 조직의 내용은 덮어쓰거나 manifest에 등록하지 않는다.
신규 설치는 사용자 소유 `workspace/` root만 만들고, 이후 upgrade와 Control Plane backup은 `knowledge/`와
`workspace/` 내부를 읽어 관리 자산으로 등록하거나 변경·백업하지 않는다.
기존 설치에 `workspace/`가 없다면 일반 upgrade는 생성하지 않는다. 별도 초기화 계획을 확인한 뒤 명시적으로
생성한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py initialize-operational-workspace
python3 .circled-wiki/bin/circled-wiki.py initialize-operational-workspace --apply
```

### 선택적 Graphify

Graphify는 Circled Wiki와 별도 설치하는 파생 관계 인덱스다. Bootstrap은 패키지나 자격증명을 설치하지 않고
`.circled-wiki/GRAPHIFY.md`와 Agent 사용 경계만 제공한다. 설치 시 Graphify를 활성화해도 graph 파일이 없으면
`operational-preflight`가 `graphify.ready: false`로 보고한다. Agent는 Graphify로 후보를 찾을 수 있지만 최종 답변은
항상 Knowledge MCP의 공식 Bundle과 Evidence로 재검증해야 한다.

### 운영 이슈와 사용자 피드백

운영 중 발생한 오류·불편·개선 제안과 사용자가 제기한 문제는 사용자 소유 `workspace/issues/`에 기록한다.
Runtime 운영 중 legacy `.circled-wiki/issues/`는 기존 기록을 제자리에서 읽고 상태 갱신할 수 있지만 일반 upgrade가 이동하지 않는다. Product Agent는 사용자가 특정 Issue 수집 또는 migration을 명시적으로 요청한 경우에만 Git Gate를 거쳐 이동할 수 있다.
CLI에서는
`--reported-from user`로 사용자 제기를 구분한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py record-system-issue \
  --title "사용자가 제기한 문제 제목" \
  --summary "관찰된 문제와 영향" \
  --reported-by "user-id" \
  --reported-from user \
  --area agent_rules \
  --severity medium
```

legacy 기록을 canonical Working Plane으로 옮길 때는 일반 upgrade와 분리된 migration 계획을 먼저 확인하고,
사용자 승인 후에만 `--apply`한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py migrate-legacy-system-issues \
  --issue issue-<id>
python3 .circled-wiki/bin/circled-wiki.py migrate-legacy-system-issues \
  --issue issue-<id> \
  --apply
```

이슈 기록은 후속 시스템 개선 검토의 입력이며 자동 수정·정책 변경·발행을 수행하지 않는다. 사용자가 특정
운영 프로젝트와 Issue를 명시해 수집을 요청하면 Git 추적·커밋·미변경 Gate를 확인한 뒤 source repository의
`workspace/issue/inbox/`로 이동한다. 사용자 검토와 Archive 유사 이력 확인 후 처리하고, 완료 항목은
`workspace/issue/archived/<canonical-key>/vNNNN.md`로 이동한다.

Product Workspace의 수집·검토·Triage·Archive와 Receipt 기록은 source repository에서만 다음 CLI로 수행한다.
설치본 `.circled-wiki/bin/circled-wiki.py`에는 이 Product Agent 명령을 배포하지 않는다.

```sh
PYTHONPATH=src python3 -m circled_wiki.product_cli intake-operational-issue \
  --source-project <운영-프로젝트-root> \
  --project-ref <safe-project-ref> \
  --issue issue-<id> \
  --requested-by <user> \
  --moved-by <agent>

PYTHONPATH=src python3 -m circled_wiki.product_cli review-workspace-issue \
  --item issue/inbox/<project-ref>/issue-<id>.md \
  --reviewed-by <user> \
  --decision accepted \
  --history-relation new
```

지정된 System Maintainer는 사실을 바꾸지 않고 상태 이력만 추가한다. 표준 흐름은
`open -> triaged -> mitigated -> verified -> resolved`이며, `verified`에는 실제 배포 release와 Deployment
Receipt, 독립 Verification Receipt가 필요하다.

```sh
python3 .circled-wiki/bin/circled-wiki.py update-system-issue \
  --issue issue-<id> \
  --status triaged \
  --actor system-maintainer \
  --note "영향과 수정 범위를 확인했다." \
  --classification product_defect \
  --next-action "재현 테스트와 제품 개선 작업을 준비한다."
```

설치 대상은 `knowledge/` 폴더가 아니라 그 폴더를 포함하는 프로젝트 root다. 최초 설치에서 `knowledge/`가 없을
때만 빈 `inbox/`, `evidence/`, `bundles/` scaffold를 만들고, manifest가 생긴 이후 업그레이드는 `knowledge/`를
완전히 건드리지 않는다. 최초 빈 설치에는 백업이 없으며, 변경 없는 재실행도 불필요한 백업을 만들지 않는다.
적용 보고서의 `backup_path`와 manifest의 `last_backup`으로 직전 스냅샷을 확인할 수 있다.

복구가 필요하면 추가 업그레이드를 중지하고 `backup_path`의 manifest와 파일을 먼저 검토한다. 현재
`.circled-wiki/`를 별도 보존한 뒤 선택한 백업 폴더를 `.circled-wiki/`로 복원한다. 이 복구 과정에서도
`knowledge/`와 `workspace/`는 이동하거나 덮어쓰지 않는다. Core의 `rollback_control_plane`도 선택한
Control Plane backup만 복원하며 rollback 직전 Control Plane을 별도 복구본으로 보존한다. 복원 후 프로젝트에서
다음 검증을 실행한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli validate
PYTHONPATH=src python3 -m unittest discover -s workspace/tests -q
```

설계, 단계별 완료 조건, 보류 범위는 [docs/15-implementation-plan.md](docs/15-implementation-plan.md)를 따른다.

## 경로 규칙

- 좋은 예: `knowledge/bundles/cs/refund-policy_7c9e6679-7425-40de-944b-e07fc1f90ae7.md`
- 좋은 예: `knowledge/bundles/marketing/runbooks/poster-production_7c9e6679-7425-40de-944b-e07fc1f90ae7.md`
- 좋은 예: `docs/03-okf-spec.md`
- 나쁜 예: `/Users/.../cpt-knowledge/knowledge/...`
- 나쁜 예: 특정 PC의 홈 디렉터리를 전제하는 경로
