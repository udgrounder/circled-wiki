# Circled Wiki Agent Bootstrap

이 파일은 설치된 대상 프로젝트에서 Circled Wiki를 운영하는 AI Agent의 시작 지점이다. Agent는 작업을 시작할 때
`.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`, `.circled-wiki/OPERATING_RULES.md`와
`.circled-wiki/AGENT_ROUTER.md`를 읽고, 요청 목적에 맞는 `.circled-wiki/agent-rules/` Profile을 선택한다.
`contracts/index.yaml`에 등록된 자동 복구 요청은 명시된 Profile을 순서대로 적용한다. Profile의 Check와 Gate를
통과하기 전에는 다음 단계나 지식 발행을 진행하지 않는다.

Circled Wiki 개발 저장소의 Product Agent는 `PRODUCT_ENGINEERING_RULES.md`와 `product-agent-rules/`를 따른다.
Runtime 배포 원본은 `OPERATING_RULES.md`, `.circled-wiki/AGENT_ROUTER.md`와 `agent-rules/`이며 Product Profile은
대상 프로젝트에 설치하지 않는다.

대상 root의 `AGENTS.md`와 `CLAUDE.md`는 이 문서를 가리키는 Agent 자동 발견용 진입점이다. Bootstrap은 파일이
없으면 참조 전용 파일을 생성하며, 조직이 이미 작성한 파일에는 운영 규칙 참조가 없을 때만 짧은 참조 블록을 추가한다.

## Local CLI

프로젝트 root에서 다음 명령으로 대상 프로젝트에 포함된 Runtime을 실행한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py validate
python3 .circled-wiki/bin/circled-wiki.py search --query "검색어"
python3 .circled-wiki/bin/circled-wiki.py find-workflow --request "사용자 요청"
python3 .circled-wiki/bin/circled-wiki.py reconcile-inbox --actor <operator> --limit 100
python3 .circled-wiki/bin/circled-wiki.py reconcile-curation --limit 100
```

Launcher는 현재 작업 디렉터리에 관계없이 이 프로젝트 root와 `.circled-wiki/runtime/`을 사용한다. Python 3.9 이상과
`PyYAML`이 필요하다. Runtime과 운영 규칙은 OS 관리 자산이므로 직접 수정하지 않고, 변경은 OS upgrade 또는
`.circled-wiki/proposals/` 제안본을 통해 검토한다.

배포 자산의 checksum·proposal·backup은 Product Agent의 upgrade dry-run과 manifest·Receipt 대조에서 확인한다.
일상 운영은 선택한 Profile의 입력·권한·Evidence·revision Gate와 필요한 경우 `validate`만 적용한다.

설치별 조직 ID, 운영 Agent와 선택적 Graphify 경계는 `.circled-wiki/config.yaml`에서 확인한다. 이 파일은 설치 시
생성되고 이후 upgrade에서 덮어쓰지 않는 설치 로컬 설정이다.

## Agent Operation

1. 지식 질문은 `knowledge-query` Profile을 선택하고 `search`, `read-bundle`로 근거를 조회한다. 직접 `find`,
   `grep`, `rg` 탐색은 공식 경로가 실패하거나 결과가 불충분할 때 작업을 계속하기 위한 최후 수단으로 허용하며,
   fallback 결과를 개별 분류해 지침 부재·모호성 또는 Runtime 결함으로 판단된 경우에만 `system-observation`
   Profile의 `record-system-issue`로 남긴다. fallback 사유와 사용한 범위는 결과에 기록한다.
2. 단계가 있는 업무는 `workflow-execution` Profile을 선택하고 `find-workflow`부터 시작한다. Workflow가 모호하거나
   필수 입력이 부족하면 실행하지 않고 사용자에게 필요한 내용만 질문한다.
3. 대화·문서·URL·파일 수집은 `inbox-capture` Profile로 `knowledge/inbox/<provider>/`에만 적재한다. 모든 수집
   Agent와 Source Adapter는 공통 Capture API의 민감정보 사전 점검(주민등록번호·계좌/카드번호·자격증명)을 먼저 거친다.
   수집과 정제, 승인, 발행은 각각의 Profile·Gate를 분리해 처리한다. `reconcile-inbox`는
   `agent-rules/contracts/inbox.yaml`을 적용해 이미 충족한 Inbox 검사·Evidence 변환 Gate만 순서대로 재수행한다.
   `review-data-protection`이 PII Scan과 Data Protection Review를 하나의 단계로 실행한다. 먼저 실제 Inbox 후보에서
   `hard_mask_categories: true`인 하드 PII를 마스킹하고, 민감도 판단 단계에서 같은 활성 범주를 다시 확인해
   놓친 값을 보완하며 Agent가 판단 가능한 급여·평가·징계·미공개 사업정보·보안 구성과 명시적인 불법 행위 실행·조장·은폐 또는 타인의
   권리·안전을 침해하는 구체적 지시만 선택적으로 마스킹한 뒤
   최종 후보를 다시 스캔해 본문 checksum과 본문·복사 메타데이터 fingerprint에 결합된 하나의
   checksum-bound `data_protection_receipt`를 기록한다. `false`인 하드 스캔 범주는 이 자동 보호 경로에서
   처리하지 않으며, 휴대전화·이메일은 기본 템플릿에서 `false`다. 민감도 정책이 별도로 적용되는 범주는
   승인된 업무 맥락을 확인한 뒤 보존한다. 계약·법률 자문·분쟁·소송·규제 대응과 그 결정은 법무 업무라는 이유만으로
   제한하지 않는다. 명시적 불법성이 확인되지 않은 법률·계약 내용은 `unlawful_content`로 추정하지 않는다. 실제 마스킹 대상의 범위·처리 방식·업무 맥락을 판단할 근거가 없거나 PII Scan 결과가 `needs_review`이면 Inbox를 `awaiting_user`로 유지하고
   안전한 다음 행동만 기존 Review Queue에 기록한다. Evidence 단계는 이 Receipt와 후보 checksum을 검증한 뒤
   생성하며 Evidence 변환에서는 이 Receipt와 checksum·생성 스키마·전환 산출물만 확인한다.
   Curation adapter가 활성화된 경우에만 `reconcile-curation`으로 Queue를 분석한 뒤 `no_bundle` Receipt, Review handoff, 자동 Gate를
   통과한 published 또는 Gate 실패 Draft를 결과 상태로 기록한다. Adapter·Gate 실패는 큐에 남긴다. 의미 변경
   승인과 revision 적용은 자동 처리하지 않는다. adapter가 비활성화되면 `list-curation-queue`로 대기 항목만 확인하고 설정 필요 상태를 반환한다.
4. 수정·발행·외부 전송·승인이 필요한 작업은 `OPERATING_RULES.md`의 권한과 Approval 규칙을 따른다. Agent는
   승인자를 대신하지 않는다.
5. CLI 실패, Validator 오류, 예상과 다른 결과는 정상 입력·권한·이미 안내된 Gate 결과인지, 업무 지침 부재·모호성인지,
   Runtime·도구 결함인지 먼저 개별 분류한다. 후자 둘로 판단한 경우에만 `system-observation` Profile을 선택해
   `workspace/issues/`에 `record-system-issue`로 기록한다. 사용자 제기는 `--reported-from user`, Agent가 발견한
   문제는 `--reported-from agent`를 사용한다. 이슈는 개선 입력이며 자동 수정 권한이 아니다. 근거가 부족하면 결함을
   추정하지 않고 현재 사실과 안전한 다음 행동만 보고한다.
6. Codex·Claude 등 외부 Agent CLI가 시작·실행에 실패해도 Inbox·Evidence를 직접 우회 수정하지 않는다. 해당 명령의
   입력·권한·선택한 Profile Gate와 필요한 `validate` 결과를 확인한 뒤, 사용자가 허용한 안전한 로컬 CLI 또는 재시도
   경로로 같은 Profile의 Gate를 다시 적용한다. 지침 부재·모호성 또는 Runtime 결함으로 판단된 경우에만 이슈를 기록한다.
7. `capture-conversation`이 exit code 3과 `idempotency_checksum_conflict`를 반환하면 이는 원문 변경 보호다.
   응답의 `existing_intake_id`를 `inspect-inbox`로 확인한다. 기존 항목을 덮어쓰지 않으며, 변경된 원문이 의도된
   새 revision이라는 근거가 있을 때만 새 idempotency key로 다시 수집한다.
8. 여러 단계 Pipeline은 독립·제한된 하위 작업을 먼저 식별하고, 사용할 수 있는 위임 수단이 있으면 위임을 권장한다.
   위임한 작업도 원래 Profile의 Gate·승인·최종 책임을 유지하며, 안전하게 분리할 수 없거나 위임 수단이 없으면 직접
   수행할 수 있다. 위임 여부만으로 작업을 차단하지 않는다.
9. Bundle 파일명·Frontmatter `id`·`bundle_uuid` 요청은 `.circled-wiki/AGENT_ROUTER.md`의 **Bundle Identity Routing**을
   먼저 적용한다. 규칙 확인 또는 충돌 점검은 read-only이며, Router와 `OPERATING_RULES.md`의 RB-KNW-026을 읽기 전에
   Bundle 본문·저장소 전체를 shell 검색하지 않는다. 정본 규칙이 없거나 불충분하면 실패 사유·범위를 밝힌 제한 검색으로
   fallback하고, 저장소 전체 검색은 그 fallback도 부족할 때만 사용한다. 일괄 정규화는 대상·ID·UUID·참조·rollback 계획과
   사용자 승인 뒤에만 Publication Profile로 전환한다.
10. Circled Wiki OS version의 release 준비·배포·rollback 요청은 이 설치본의 Runtime Agent 권한이 아니다. 대상에서
   Runtime을 직접 바꾸거나 전체 검색으로 배포 절차를 추정하지 않고, 제품 source repository의 `AGENTS.md` Routing
   Table에서 `release-preparation` 또는 `deployment-coordination` Profile로 전환한다. 대상 Runtime Agent는 배포 후
   `runtime-upgrade-verification`만 독립적으로 수행한다.

## Runtime Boundary

`.circled-wiki/runtime/`은 이 OS release에 포함된 CLI 구현이다. `knowledge/`는 조직 자료의 Data Plane이고
`workspace/`는 Issue, 작업 기록과 백업 같은 사용자 소유 Working Plane이다. 둘 다 공식 OS 관리 자산이 아니며
OS upgrade와 Runtime 배포가 수정하거나 Control Plane 백업에 포함하지 않는다. OS를 다른 프로젝트에 설치하려면 이 Launcher의
`bootstrap-circled-wiki` 명령을 사용할 수 있다.
