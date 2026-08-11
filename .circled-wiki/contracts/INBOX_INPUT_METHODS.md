---
method_spec_version: v1
---

# Inbox 원문 입력 메소드 스펙

수집 Agent는 원문 종류에 맞는 메소드를 호출한다. Runtime 실행 권한이 없으면 같은 입력을 Wiki Agent에 전달해 대행 제출을 요청한다.

## `capture_document`

텍스트 문서를 Inbox에 등록한다.

필수: `content`(원문 텍스트), `provider`(수집 출처), `title`(제목), `why_collected`(수집 목적), `intended_use`(예상 활용 목록), `idempotency_key`(원문·revision 중복 방지 키).

선택: `source_url`(안정적인 원문 URL), `source_locator`(URL로 부족한 위치), `captured_from`(`api`, `webhook`, `manual`, `upload`, `sync`).

## `capture_conversation`

대화 transcript를 Inbox에 등록한다.

필수: `content`, `provider`, `title`, `why_collected`, `intended_use`, `idempotency_key`.

선택: `thread_ref`(대화 위치), `turn_from`, `turn_to`, `artifacts`.

## `capture_file`

원본 파일과 Inbox envelope를 함께 등록한다.

필수: `payload`(원본 bytes), `original_filename`, `provider`, `title`, `why_collected`, `intended_use`, `idempotency_key`.

선택: `source_url`, `source_locator`, `captured_from`.
