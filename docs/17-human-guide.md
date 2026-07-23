# 사람 사용자를 위한 Circled Wiki 및 Workflow 가이드

## 1. 이 문서의 대상

이 문서는 조직 구성원이 Hermes와 Circled Wiki를 사용해 기존 회사 지식으로 업무를 수행하고,
결과와 피드백을 다음 작업에 재사용할 수 있게 남기는 방법을 설명한다.

일반 사용자는 저장소 구조나 MCP Tool 이름을 외울 필요가 없다. Hermes에 업무 목적을 설명하고,
부족한 정보를 제공하고, 승인 지점에서 판단하고, 마지막에 결과와 피드백을 확인하면 된다.

운영자와 지식 편집자는 이 문서 후반의 CLI 및 Runbook 작성 절차를 함께 사용한다.

## 2. 가장 간단한 사용 방법

Hermes에 원하는 결과를 업무 요청 형태로 작성한다.

좋은 요청 예시:

```text
8월 가족 캠핑 이벤트에 사용할 모바일 앱 포스터를 만들고 싶어.
대상은 초등학생 자녀가 있는 가족이고, 8월 5일까지 첫 시안이 필요해.
기존 브랜드 가이드와 과거 여름 이벤트 사례를 사용해줘.
최종 이미지 생성 전에 제작 브리프를 나에게 승인받아줘.
```

```text
신규 캠핑장 등록을 진행하려고 해.
처음 하는 업무라 기존 등록 사례와 반려 사례를 바탕으로 단계별로 안내해줘.
계약과 가격 정보는 담당자 승인을 받은 뒤 등록하도록 해줘.
```

Hermes는 다음 순서로 처리해야 한다.

1. 요청에 맞는 활성 Runbook을 찾는다.
2. 필요한 정보 중 아직 없는 항목만 질문한다.
3. 관련 정책, Guide, Decision, 과거 Evidence를 함께 조회한다.
4. 실행 단계와 사람 승인 지점을 보여준다.
5. 단계별 작업을 안내하거나 허용된 Agent에 위임한다.
6. 완료 기준으로 결과를 검증한다.
7. 결과, 피드백, 새로 배운 내용을 Evidence로 남긴다.

## 3. 요청할 때 포함하면 좋은 정보

처음부터 모든 정보를 알 필요는 없다. 다음 항목을 가능한 범위에서 제공하면 Hermes가 불필요한 질문을 줄일 수 있다.

- 원하는 최종 결과
- 업무 대상과 사용 목적
- 대상 고객 또는 이해관계자
- 마감일과 우선순위
- 반드시 지켜야 하는 조건
- 사용할 채널 또는 시스템
- 참고할 과거 작업이나 문서
- 최종 승인자
- 생성해야 할 산출물
- 자동 실행해도 되는 범위와 반드시 확인받아야 하는 범위

불확실한 내용은 추측해서 채우지 말고 `미정`, `담당자 확인 필요`처럼 표시한다.

## 4. Workflow 선택 확인

Hermes가 실행 가능한 Runbook 후보를 제시하면 다음을 확인한다.

- 내가 하려는 업무와 목적이 같은가
- 신규 작업과 수정 작업이 구분되어 있는가
- 현재 조직과 도메인에 적용되는 절차인가
- `active` 상태의 공식 Runbook인가
- 관련 정책이나 승인 절차가 누락되지 않았는가

후보가 여러 개이고 차이를 이해하기 어렵다면 Hermes에 각 Workflow의 사용 조건과 결과 차이를 설명해 달라고 요청한다.

적절한 Workflow가 없다면 Hermes가 임의로 공식 절차를 만들게 해서는 안 된다. 기존 Guide와 사례를 기반으로
일회성 계획을 만들고 사람 검토로 실행한 뒤, 결과를 신규 Runbook 후보 Evidence로 남긴다.

## 5. 필수 입력 제공

Task가 생성되면 Hermes는 `missing_inputs`에 있는 항목만 질문해야 한다. 답변할 수 없는 항목은 담당자 확인이
필요하다고 표시한다.

포스터 제작 예시:

- 대상 고객
- 게시 채널
- 이미지 크기
- 필수 문구
- 마감일
- 브랜드 또는 캠페인

캠핑장 등록 예시:

- 신규 등록 또는 수정 여부
- 캠핑장 기본 정보
- 사업자·계약 확인 상태
- 주소와 위치
- 시설·사이트 정보
- 가격과 수수료
- 등록 승인자

필수 입력이 남아 있는 동안 Hermes는 실행 단계로 넘어가면 안 된다.

## 6. 단계 진행과 사람 승인

Hermes는 Runbook 순서대로 단계를 진행한다. 각 단계에서 사람은 다음을 확인한다.

- 사용한 입력과 근거가 맞는가
- Hermes가 수행한 작업과 결과가 명확한가
- 다음 단계로 넘어가도 되는가
- 민감한 정보나 외부 전송이 포함되는가
- 승인 권한이 있는 사람이 확인했는가

Approval 단계에서는 Hermes가 스스로 승인자로 행동할 수 없다. 승인자는 승인 또는 반려 이유를 명확히 남긴다.

승인 예시:

```text
제작 브리프를 승인해. 모바일 앱 배너 규격 1080×1350을 사용하고,
메인 문구는 “우리 가족의 여름 캠핑”으로 확정해.
승인자: marketing-owner
```

반려 예시:

```text
브리프를 반려해. 가격 할인 표현이 현재 프로모션 정책과 일치하지 않아.
CS와 마케팅 정책 담당자 확인 후 다시 요청해줘.
```

## 7. 결과 확인과 완료

작업 완료 전 Runbook의 `completion_criteria`를 확인한다.

Runbook이 만료된 경우 Hermes는 원래 업무를 바로 실행하지 않고 Refresh Task를 먼저 제시한다. 사용자가
“최신 정책으로 확인해줘”, “이 절차를 최신화해줘”처럼 요청하면 유효기간이 남아 있어도 즉시 최신 Evidence
확인과 Owner 검토를 시작한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli prepare-runbook-refresh \
  --workflow poster-production \
  --request "현재 정책 기준으로 최신화해줘" \
  --requested-by marketing-user \
  --reason user_requested
```

최신화 결과는 반드시 내용 변경일 필요가 없다. 최신 원본에 변화가 없으면 `no_change`, 원본이 부족하면
`insufficient_evidence`로 기록한다. 변경안 또는 무변경 갱신안은 작성 Agent와 다른 Agent가 검증한 뒤
Runbook Owner가 승인한다.

더 좋은 레퍼런스를 찾았다면 먼저 원본을 Evidence로 수집한 뒤 대상 Workflow에 제출한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli submit-runbook-reference \
  --workflow poster-production \
  --evidence evidence://example-org/user/2026/07/14/{source_uuid} \
  --submitted-by marketing-user \
  --note "최근 승인된 디자인 가이드이며 기존 기준과 비교가 필요함"
```

제출 자료는 즉시 정답으로 채택되지 않는다. 열린 Refresh Task가 있으면 그 Task에 합쳐지고, 출처·최신성·
적용 범위와 기존 근거의 충돌을 검토한 뒤 독립 Agent 검증과 Owner 승인으로 반영 여부를 결정한다.
검토 결과는 전체 채택, 부분 채택, 비채택, 추가 근거 필요로 구분한다. 중요한 결정은 결정자와 근거를,
후속 작업은 담당자와 완료 기준을, 미해결 질문은 확인 Owner를 명시한다.

운영자는 `audit-knowledge`로 만료·근거·역참조·열린 Task 문제를 확인하고
`list-knowledge-inventory`로 Domain·상태·Owner·검토 기한을 조회할 수 있다. Inventory는 Frontmatter에서
계산되므로 별도 수동 목록을 편집하지 않는다.

실제 업무에서 남긴 성공·실패·피드백은 Outcome Evidence로 누적된다. 실패, 사용자 피드백 또는 Runbook에
설정한 Outcome 임계치가 발생하면 개선 검토 Task가 생성되지만, 최신 원본 확인 없이 Runbook 본문을 자동
수정하지 않는다.

포스터라면 다음을 확인할 수 있다.

- 규격과 채널 요구사항
- 필수 문구의 정확성
- 브랜드 색상과 표현
- 모바일 가독성
- 저작권과 개인정보
- 최종 승인 여부

캠핑장 등록이라면 다음을 확인할 수 있다.

- 필수 정보 입력 완료
- 중복 등록 여부
- 주소와 위치 정확성
- 계약·가격 승인
- 시설 정보와 이미지 품질
- 게시 후 노출 확인

모든 단계와 승인이 끝난 뒤에만 `completed` 결과로 종료한다. 중단되거나 불확실하면 `failed` 또는
`needs_review`로 기록한다.

## 8. 결과와 피드백 남기기

작업이 끝나면 다음 내용을 Hermes에 전달한다.

- 최종 결과 요약
- 성공 또는 실패 여부
- 생성된 산출물의 내부 위치
- 사용자의 피드백
- 예상과 달랐던 예외
- 다음 작업에서 재사용할 교훈
- Runbook에서 고쳐야 할 부분

예시:

```text
작업을 완료했어.
최종 파일: internal-storage://design/2026-summer-poster.png
피드백: 모바일에서는 부제목이 작아 첫 시안에서 읽기 어려웠어.
학습: 모바일 포스터는 부제목을 최소 44px로 검증하는 항목을 추가하면 좋겠어.
이 내용을 결과 Evidence로 남기고 Runbook 개선 후보로 보내줘.
```

대용량 파일은 Git에 복사하지 않고 내부 저장소 URI와 `metadata_only` 또는 실제 availability 상태만 기록한다.

## 9. Evidence를 읽을 수 없는 경우

Hermes가 다음 상태를 표시할 수 있다.

- `available`: 원본을 읽고 확인할 수 있음
- `metadata_only`: 메타데이터만 있고 원본 내용은 확인하지 못함
- `temporarily_unavailable`: 일시적으로 원본에 접근할 수 없음
- `access_denied`: 현재 사용자 또는 Agent에게 권한이 없음
- `missing`: 원본 참조가 없어졌음

`metadata_only`, `access_denied`, `missing` 근거만 있는 경우 Hermes의 답변을 원본 검증이 완료된 사실로
취급하지 않는다. 중요한 결정은 원본 확인 또는 담당자 승인을 거친다.

## 10. 지식 편집자가 새 Runbook을 만드는 방법

공식 Runbook은 반드시 실제 회사 Evidence를 근거로 만들어야 한다.

### 10.1 근거 수집

과거 작업 문서, 체크리스트, 승인 기록, 결과물 참조, 반려 사례를 `knowledge/inbox/`에 넣고 Evidence로 수집한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli ingest-evidence \
  --provider manual \
  --file knowledge/inbox/poster-workflow-source.md \
  --title "포스터 제작 절차 근거" \
  --why-collected "반복되는 포스터 제작 업무를 표준화하기 위한 근거" \
  --intended-use poster-production
```

### 10.2 Runbook Draft 생성

Runbook과 Manual 성격의 Guide는 직접 `create-bundle`로 만들지 않는다. Evidence 기반 정제 결과가
`knowledge/curation-reviews/`에 만든 Review 카드를 Owner가 검토·승인한 뒤 Draft를 생성한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli list-curation-reviews
PYTHONPATH=src python3 -m circled_wiki.cli decide-curation-review \
  --review review-<id> --action approve --actor <owner-id>
```

승인 뒤 생성된 `draft` Runbook을 Obsidian에서 열고
[Runbook Template](../.circled-wiki/templates/runbook.md)을 기준으로 `extensions.workflow`와 본문을 작성한다.
파일은 `knowledge/bundles/marketing/runbooks/`에 생성된다.

### 10.3 검토와 활성화

다음을 확인한 뒤 생성자와 다른 Owner가 Curation Review를 승인하고, Security Receipt를 포함한 전용
Promotion Gate로 `active` 전환한다. Frontmatter의 `status`를 직접 변경하거나 일반 revision API를 사용하지 않는다.

- Workflow ID와 version
- 필수 입력
- 단계 순서와 안정적인 step ID
- 사람 승인 단계
- 완료 기준
- 실패·예외 처리
- 관련 Policy, Guide, Decision 링크
- Evidence 연결
- owner, `reviewed_at`, `review_due_at`, `freshness_policy`
- 적용·제외 범위
- 성공·실패 Outcome Evidence 예시

```sh
PYTHONPATH=src python3 -m circled_wiki.cli validate
```

Validator가 통과한 뒤 보안 검토와 저장소 발행 정책을 따른다.

## 11. 운영자용 CLI 실행 예시

```sh
# 1. Workflow 탐색
PYTHONPATH=src python3 -m circled_wiki.cli find-workflow --request "포스터를 만들고 싶어"

# 2. Task 생성
PYTHONPATH=src python3 -m circled_wiki.cli prepare-task \
  --workflow poster-production \
  --request "여름 이벤트 포스터를 만들어줘" \
  --inputs '{"audience":"가족 캠퍼"}'

# 3. 누락 입력 보완
PYTHONPATH=src python3 -m circled_wiki.cli update-task-inputs \
  --task <task-uuid> \
  --inputs '{"channel":"mobile-app"}'

# 4. 실행 단계 기록
PYTHONPATH=src python3 -m circled_wiki.cli record-task-step \
  --task <task-uuid> \
  --step collect-inputs \
  --status completed \
  --result "필수 입력을 확인했다" \
  --actor hermes

# 5. 사람 승인 기록
PYTHONPATH=src python3 -m circled_wiki.cli record-task-step \
  --task <task-uuid> \
  --step approve-brief \
  --status approved \
  --result "마케팅 담당자가 제작 브리프를 승인했다" \
  --actor marketing-owner

# 6. 완료 기준 검증 기록
PYTHONPATH=src python3 -m circled_wiki.cli record-task-step \
  --task <task-uuid> \
  --step validate-output \
  --status completed \
  --result "규격과 브랜드 완료 기준을 통과했다" \
  --actor hermes

# 7. 현재 상태 확인
PYTHONPATH=src python3 -m circled_wiki.cli get-task --task <task-uuid>

# 8. 결과 Evidence 환류
PYTHONPATH=src python3 -m circled_wiki.cli record-outcome \
  --task <task-uuid> \
  --status completed \
  --summary "포스터 제작과 승인을 완료했다" \
  --feedback "모바일 가독성이 좋았다" \
  --learning "모바일에서는 큰 제목을 우선한다" \
  --artifacts '[{"name":"poster.png","uri":"internal-storage://design/poster.png","availability":"metadata_only"}]'
```

`completed` Outcome을 기록하려면 모든 action·validation 단계가 `completed`, 모든 approval 단계가
`approved` 상태여야 한다.

## 12. 문제가 생겼을 때

| 상황 | 조치 |
| --- | --- |
| Workflow가 검색되지 않음 | 일반 지식 검색 후 일회성 계획으로 진행하고 신규 Runbook 후보를 남긴다. |
| Runbook 후보가 여러 개 | 적용 조건과 결과 차이를 비교하고 사람이 선택한다. |
| 필수 입력을 알 수 없음 | 담당자 확인 또는 `needs_review`로 전환한다. |
| 다음 단계가 기록되지 않음 | 이전 단계가 `completed` 또는 `approved`인지 확인한다. |
| 승인자가 없음 | 자동 승인하지 않고 담당 owner에게 에스컬레이션한다. |
| 원본이 metadata only | 원문 검증 불가를 표시하고 중요한 결정은 담당자에게 확인한다. |
| 결과 Evidence가 Commit되지 않음 | `pii_scanned: false` 여부와 보안 검토 상태를 확인한다. |

## 13. 관련 문서

- [Workflow 실행 및 지식 환류 설계](16-workflow-execution.md)
- [Hermes 아키텍처](05-hermes-architecture.md)
- [Obsidian 편집 가이드](10-obsidian-guidelines.md)
- [Agent 및 지식 보안 정책](../.circled-wiki/policies/agent-security.md)
- [AI Agent 가이드](18-agent-guide.md)
