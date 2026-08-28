# 2026-08 Inbox Issue Improvement Plan (Draft)

## 목적과 상태

`workspace/issues/inbox/campingtalk-wiki/`의 5개 수집 이슈를 안전한 기록만으로 검토해, 제품 개선 후보와
설치본/운영 조치 후보를 분리한다. 이 문서는 구현 승인이나 Workspace Issue의 `accepted` 전환을 뜻하지 않는
계획 초안이다. 각 Issue의 `review` receipt가 비어 있으므로, 아래 분류는 사용자 승인 전의 제안으로만 취급한다.

## 검토 결과

| Source issue | 제안 분류 | 관계 | 우선순위 | 제안 disposition |
| --- | --- | --- | --- | --- |
| `issue-20260819T191149Z-c35fec4a` | `product_defect` | `regression` — 2026-08-06 한글 credential detector 보강의 미지원 Markdown/병렬 라벨 형식 | P0 | 구현 후보 |
| `issue-20260820T192235Z-84e4ff6f` | `product_defect` | `new` — 유효하지 않은 Inbox 후보에서 예외 이름이 미해결되어 전체 배치가 실패 | P1 | 구현 후보 |
| `issue-20260821T091700Z-6dc1fdee` | `product_defect` | `related` — Runbook active Gate는 존재하지만 승인 전 발견성이 부족 | P1 | 구현 후보 |
| `issue-20260821T091720Z-708ae02c` | `product_documentation_or_discoverability` | `related` — 현재 `list-curation-candidates`가 approved+draft를 이미 반환 | P2 | Curation Gate 개선과 함께 처리 |
| `issue-20260826T235128Z-d9b749b6` | `installation_configuration` | `new` — 외부 wiki agent의 비구조화 YAML 판별 실패 | P1 | 대표 설치본에서 운영 수정·검증 |

`issue-20260819T191149Z-c35fec4a`는 synthetic 재현으로 확인했다. 현재 구현은 줄바꿈 구분만 마스킹하며,
`**비밀번호**`와 `아이디 / 비번` 병렬 형식은 마스킹하지 않는다. 실제 credential 또는 고객 원문은 이 계획서와
테스트에 기록하지 않는다.

`issue-20260820T192235Z-84e4ff6f`의 원인은 현재 source에서도 재현 가능한 코드 결함이다. `ingest.py`가
`FrontmatterError`를 except 절에서 참조하지만 import하지 않는다. 잘못된 Inbox 후보를 건너뛰려는 여러 순회
경로가 `NameError`로 바뀔 수 있다.

## 작업 묶음 A — Credential scanner regression (P0)

### 범위

- `src/circled_wiki/runtime/core/sensitive_data.py`의 한국어 credential pattern을 Markdown 강조 표기와
  같은 줄의 병렬 라벨/값 쌍을 안전하게 처리하도록 보강한다.
- 기존 영문 assignment, URL/OAuth, private key와 disabled hard-mask category 동작은 바꾸지 않는다.
- `tests/unit/test_sensitive_data.py`에 synthetic-only 회귀 사례와 이미 마스킹된 값의 idempotency 사례를 추가한다.

### 수용 기준

1. `비밀번호`·`비번` 라벨에 선택적 `**` Markdown 강조가 있어도 synthetic 값이 `********`로 바뀐다.
2. `아이디: user / 비번: synthetic-value`에서 비밀번호 값만 마스킹되며, 사용자 식별자까지 과도하게 지우지 않는다.
3. label 없이 일반 문장에 나온 단어·값을 credential로 오탐하지 않는다.
4. credential hard mask가 명시적으로 비활성화되면 새 형식도 자동 마스킹하지 않는다.

## 작업 묶음 B — Malformed Inbox resilience (P1)

### 범위

- `ingest.py`에서 실제 frontmatter 예외 타입을 명시적으로 import한다.
- 유효하지 않은 `.md` Inbox 후보와 정상 후보를 함께 둔 synthetic fixture에서 Data Protection 관련 순회가
  정상 후보를 계속 처리하는지 검증한다.
- 동일한 except 패턴을 사용하는 경로를 점검하되, 전역 예외 포착으로 범위를 넓히지 않는다.

### 수용 기준

1. frontmatter가 깨진 파일 하나가 있을 때 대상과 무관한 전체 batch가 `NameError`로 중단되지 않는다.
2. 유효하지 않은 파일은 격리·건너뛰기라는 기존 계약을 유지하고, 정상 Inbox 항목의 결과는 처리된다.
3. `OSError` 및 기존 `ValueError` 처리 범위는 후퇴하지 않는다.

## 작업 묶음 C — 승인 후 promotion readiness (P1/P2)

### 범위

- Runbook/manual의 active 요건(`extensions.workflow.learning`, 비어 있지 않은 `## Workflow Summary`)을
  `review-curation-candidate --action approve` 단계에서 promotion 전에 검증할지 검토하고, 채택 시
  actionable error를 반환한다.
- schema에는 구조적으로 표현 가능한 `extensions.workflow.learning` 객체 계약을 문서화한다. 본문 heading의
  비어 있지 않음은 JSON Schema만으로는 충분히 표현하기 어려우므로 Validator/CLI 검증을 정본으로 둔다.
- 기존 `list-curation-candidates`를 approved+draft 항목의 machine-readable 조회 API로 문서화한다. 필요하면
  `list-pending-promotions` 별칭을 추가하되, 두 목록의 상태 의미가 갈리지 않도록 단일 구현을 공유한다.
- CLI 도움말과 운영 가이드에 “승인 ≠ 게시, Owner promotion과 security receipt가 별도”임을 명시한다.

### 수용 기준

1. 결함이 있는 Runbook은 승인 또는 promotion 전에 필요한 모든 누락 항목을 한 번에 알 수 있다.
2. approved+draft 후보가 구조화 JSON으로 조회되고, `pending` 후보와 혼동되지 않는다.
3. valid Runbook/manual의 기존 owner/security promotion Gate는 완화되지 않는다.
4. Validator와 schema/CLI 설명이 동일한 필수 항목을 가리킨다.

## 작업 묶음 D — Daily report source of truth (대표 설치본 조치)

이 항목은 현 source repository에 daily-report 구현 또는 Claude print-mode 호출 계약이 없으므로 제품 코드 작업으로
자동 전환하지 않는다. 사용자가 지정한 대표 Wiki에서 다음과 같이 조치한다.

1. daily-report가 LLM의 자연어 YAML 판별 대신 `list-curation-candidates`의 JSON 결과를 읽도록 변경한다.
2. pending review 목록은 `review_state == "pending"`만, 승인 후 미게시 목록은
   `review_state == "approved" and status == "draft"`만 표시한다.
3. approved draft, pending draft, active bundle을 각각 가진 synthetic 또는 비민감 fixture로 리포트를 검증한다.
4. 설치본 변경은 Runtime Router와 deployment receipt 절차를 별도로 따른다.

## 권장 순서와 Gate

1. 사용자 review receipt로 A–C의 Issue를 `accepted` 또는 보류로 결정한다.
2. accepted 항목만 Triage에 `classification`, `history_relation`, `linked_work`를 기록한다.
3. A, B를 먼저 구현·단위 테스트한다. 보안 누락과 batch 중단을 같은 변경에서 결합하지 않는다.
4. C를 별도 변경으로 구현한다. CLI 동작·Validator·schema·문서를 함께 갱신한다.
5. 각 제품 변경마다 관련 단위/통합 테스트, `PYTHONPATH=src python3 -m circled_wiki.cli validate`,
   `PYTHONPATH=src python3 -m unittest discover -s tests -q`를 실행한다.
6. 소스 검증 결과를 Issue의 `source_commit_verification` 또는 `worktree_verification`에 남긴 뒤에만
   `resolved` archive를 검토한다. release와 대표 설치본 검증은 별도 Gate다.

## 비범위와 위험

- 실제 자격증명, Notion 캡처, 설치 경로 및 설치별 설정은 source 계획서·테스트에 추가하지 않는다.
- Scanner는 고신뢰도 패턴만 확장한다. Markdown 제거를 전처리로 일반화하면 본문 보존·오탐 범위가 커질 수 있으므로
  label 주변의 제한된 표기만 다룬다.
- Issue E의 런타임 수정은 대표 설치본과 사용자 승인이 없으면 수행하지 않는다.
