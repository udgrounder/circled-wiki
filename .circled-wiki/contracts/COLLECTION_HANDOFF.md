---
handoff_version: v1
---

# 외부 원문 수집 Handoff

수집 Agent는 Handoff 응답의 메소드 스펙 문서를 읽고 원문 종류에 맞는 입력을 제출한다. Runtime이 정식 Inbox 항목을 생성·검사한다. Runtime을 실행할 수 없으면 같은 원문·메타데이터를 Wiki Agent에 전달해 대행 제출을 요청한다. 대행은 원문을 재해석하거나 빠진 값을 추정하지 않는다.

## 수집 품질

원문의 안정적 URL과 URL로 충분하지 않은 위치 정보, 수집 목적, 활용 목적, 원문 객체와 revision을 식별하는 idempotency key를 알 수 있으면 함께 보존한다. presigned URL은 query token·서명을 제외한 안정적인 URL을 사용한다.

## 중복·재수집

- 같은 provider와 `idempotency_key`에서 checksum 충돌이 나면 기존 항목을 먼저 확인한다.
- 실제 새 revision이라는 근거가 있을 때만 새 `idempotency_key`로 다시 전달한다.
- provider별 key 형식은 수집 Agent가 관리하되, 원문 객체와 revision을 함께 식별할 수 있어야 한다.

## 대화 Transcript 생성

대화 transcript는 전달용 파생본이다. 원본 세션 식별자와 수집 시각을 알 수 있으면 함께 보존한다.

- 첨부·링크·파일 참조가 없는 공백·줄바꿈 메시지는 제외할 수 있다.
- 명시적인 type 또는 sender 표식으로 확인된 세션 메타데이터와 크론 자동 전달 메시지는 제외할 수 있다. 내용만 보고 추정해서 제외하지 않는다.
- 같은 thread에서 바로 연속하고 role과 정규화된 본문이 같은 메시지만 중복 제거한다. 시간·thread·message ID가 다르면 제거하지 않는다.
- 오류 원인·운영 판단·사용자 요청 결과가 담긴 tool 결과와 첨부·링크·파일 참조가 있는 메시지는 제외하지 않는다.

## Provider별 출처 맥락

- Notion: 안정적인 페이지 URL과 페이지 식별자를 `source_url`, `source_locator`에 남긴다.
- Slack: 채널·thread 등 대화 위치를 `source_locator`에 남긴다. 대화 전체를 수집했다면 그 사실을 메타데이터에 표시한다.
