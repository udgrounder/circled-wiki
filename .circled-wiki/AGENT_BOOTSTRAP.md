# Circled Wiki Agent Bootstrap

이 파일은 설치된 대상 프로젝트에서 Circled Wiki를 운영하는 AI Agent의 시작 지점이다. Agent는 작업을 시작할 때
`.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`, `.circled-wiki/OPERATING_RULES.md`와
`.circled-wiki/AGENT_ROUTER.md`를 읽고, 요청 목적에 맞는 `.circled-wiki/agent-rules/` Profile 하나를 선택한다.
Profile의 Check와 Gate를 통과하기 전에는 다음 단계나 지식 발행을 진행하지 않는다.

Circled Wiki 개발 저장소의 Product Agent는 `PRODUCT_ENGINEERING_RULES.md`와 `product-agent-rules/`를 따른다.
Runtime 배포 원본은 `OPERATING_RULES.md`, `.circled-wiki/AGENT_ROUTER.md`와 `agent-rules/`이며 Product Profile은
대상 프로젝트에 설치하지 않는다.

대상 root의 `AGENTS.md`와 `CLAUDE.md`는 이 문서를 가리키는 Agent 자동 발견용 진입점이다. Bootstrap은 파일이
없으면 참조 전용 파일을 생성하며, 조직이 이미 작성한 파일에는 운영 규칙 참조가 없을 때만 짧은 참조 블록을 추가한다.

## Local CLI

프로젝트 root에서 다음 명령으로 대상 프로젝트에 포함된 Runtime을 실행한다.

```sh
python3 .circled-wiki/bin/circled-wiki.py validate
python3 .circled-wiki/bin/circled-wiki.py operational-preflight
python3 .circled-wiki/bin/circled-wiki.py search --query "검색어"
python3 .circled-wiki/bin/circled-wiki.py find-workflow --request "사용자 요청"
```

Launcher는 현재 작업 디렉터리에 관계없이 이 프로젝트 root와 `.circled-wiki/runtime/`을 사용한다. Python 3.9 이상과
`PyYAML`이 필요하다. Runtime과 운영 규칙은 OS 관리 자산이므로 직접 수정하지 않고, 변경은 OS upgrade 또는
`.circled-wiki/proposals/` 제안본을 통해 검토한다.

설치별 조직 ID, 운영 Agent와 선택적 Graphify 경계는 `.circled-wiki/config.yaml`에서 확인한다. 이 파일은 설치 시
생성되고 이후 upgrade에서 덮어쓰지 않는 설치 로컬 설정이다.

## Agent Operation

1. 지식 질문은 `knowledge-query` Profile을 선택하고 `search`, `read-bundle`로 근거를 조회한다.
2. 단계가 있는 업무는 `workflow-execution` Profile을 선택하고 `find-workflow`부터 시작한다. Workflow가 모호하거나
   필수 입력이 부족하면 실행하지 않고 사용자에게 필요한 내용만 질문한다.
3. 대화·문서·URL·파일 수집은 `inbox-capture` Profile로 `knowledge/inbox/<provider>/`에만 적재한다. 수집과 정제,
   승인, 발행은 각각의 Profile·Gate를 분리해 처리한다.
4. 수정·발행·외부 전송·승인이 필요한 작업은 `OPERATING_RULES.md`의 권한과 Approval 규칙을 따른다. Agent는
   승인자를 대신하지 않는다.
5. CLI 실패, Validator 오류, 예상과 다른 결과, 사용자·Agent·운영자·자동화의 운영 문제 또는 개선 요청을 발견하면
   `system-observation` Profile을 선택하고 `workspace/issues/`에 `record-system-issue`로 기록한다. 사용자 제기는
   `--reported-from user`, Agent가 발견한 문제는 `--reported-from agent`를 사용한다. 이슈는 개선 입력이며 자동 수정
   권한이 아니다. 이슈 기록 또는 복구가 실패하면 완료를 주장하지 않고 원인을 보고한다.
6. Codex·Claude 등 외부 Agent CLI가 시작·실행에 실패해도 Inbox·Evidence를 직접 우회 수정하지 않는다. 먼저
   `operational-preflight`로 로컬 Runtime 준비 상태를 확인하고, 실패 사실을 Issue로 남긴 뒤, 사용자가 허용한
   안전한 로컬 CLI 또는 재시도 경로로 같은 Profile의 Gate를 다시 적용한다.
7. `capture-conversation`이 exit code 3과 `idempotency_checksum_conflict`를 반환하면 이는 원문 변경 보호다.
   응답의 `existing_intake_id`를 `inspect-inbox`로 확인한다. 기존 항목을 덮어쓰지 않으며, 변경된 원문이 의도된
   새 revision이라는 근거가 있을 때만 새 idempotency key로 다시 수집한다.

## Runtime Boundary

`.circled-wiki/runtime/`은 이 OS release에 포함된 CLI 구현이다. `knowledge/`는 조직 자료의 Data Plane이고
`workspace/`는 Issue, 작업 기록과 백업 같은 사용자 소유 Working Plane이다. 둘 다 공식 OS 관리 자산이 아니며
OS upgrade와 Runtime 배포가 수정하거나 Control Plane 백업에 포함하지 않는다. OS를 다른 프로젝트에 설치하려면 이 Launcher의
`bootstrap-circled-wiki` 명령을 사용할 수 있다.
