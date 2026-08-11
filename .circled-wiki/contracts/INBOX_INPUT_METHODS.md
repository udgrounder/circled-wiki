---
method_spec_version: v1
---

# Inbox 원문 입력 메소드 스펙

수집 Agent는 원문 종류에 맞는 메소드를 호출한다. Runtime 실행 권한이 없으면 같은 입력을 Wiki Agent에 전달해 대행 제출을 요청한다. 새 Inbox 등록 또는 기존 Inbox 재사용 시 `intake_id`, `inbox_path`, `checksum`, `status: pending`을 반환한다. 이미 Evidence로 전환된 동일 원문을 재사용하면 `evidence_id`, `evidence_path`, `status: ingested`를 반환한다. 같은 `idempotency_key`와 다른 원문이면 충돌 오류를 반환한다.

## `capture_document`

텍스트 문서를 Inbox에 등록한다.

```text
capture_document(content, provider, *, title, why_collected, intended_use,
                 idempotency_key, source_url=None, source_locator=None,
                 captured_from="sync")
```

| 파라미터 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `content` | string | 예 | 원문 텍스트 |
| `provider` | string | 예 | 소문자·숫자·`_`·`-`로 구성된 수집 출처 |
| `title` | string | 예 | 원문 제목 |
| `why_collected` | string | 예 | 수집 목적 |
| `intended_use` | string[] | 예 | 예상 활용 목록 |
| `idempotency_key` | string | 예 | 원문 객체와 revision을 식별하는 키 |
| `source_url` | string | 아니오 | 안정적인 원문 URL |
| `source_locator` | string | 아니오 | URL로 부족한 원문 위치 |
| `captured_from` | enum | 아니오 | `api`, `webhook`, `manual`, `upload`, `sync` 중 수집 경로 |

## `capture_conversation`

대화 transcript를 Inbox에 등록한다.

```text
capture_conversation(content, provider, *, title, why_collected, intended_use,
                     idempotency_key, thread_ref=None, turn_from=None,
                     turn_to=None, artifacts=None)
```

| 파라미터 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `content` | string | 예 | 정리된 대화 transcript |
| `provider` | string | 예 | 수집 출처 |
| `title` | string | 예 | 대화 제목 |
| `why_collected` | string | 예 | 수집 목적 |
| `intended_use` | string[] | 예 | 예상 활용 목록 |
| `idempotency_key` | string | 예 | 대화와 revision을 식별하는 키 |
| `thread_ref` | string | 아니오 | 채널·thread 등 대화 위치 |
| `turn_from`, `turn_to` | integer | 아니오 | 포함한 turn 범위; 0 이상이며 `turn_to`는 `turn_from` 이상 |
| `artifacts` | object[] | 아니오 | 첨부·링크 등 관련 artifact 메타데이터 |

## `capture_file`

원본 파일과 Inbox envelope를 함께 등록한다.

```text
capture_file(payload, original_filename, provider, *, title, why_collected,
             intended_use, idempotency_key, source_url=None,
             source_locator=None, captured_from="upload")
```

| 파라미터 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `payload` | bytes | 예 | 변경하지 않은 원본 파일 bytes |
| `original_filename` | string | 예 | 경로 없이 파일명만 포함한 원본 이름 |
| `provider` | string | 예 | 수집 출처 |
| `title` | string | 예 | 원문 제목 |
| `why_collected` | string | 예 | 수집 목적 |
| `intended_use` | string[] | 예 | 예상 활용 목록 |
| `idempotency_key` | string | 예 | 원문 객체와 revision을 식별하는 키 |
| `source_url` | string | 아니오 | 안정적인 원문 URL |
| `source_locator` | string | 아니오 | URL로 부족한 원문 위치 |
| `captured_from` | enum | 아니오 | `api`, `webhook`, `manual`, `upload`, `sync` 중 수집 경로 |

## 공통 오류

- 필수값·타입·provider 형식 오류: Inbox를 만들지 않고 입력 오류를 반환한다.
- 동일 `idempotency_key`와 다른 원문: 기존 Intake 정보만 포함한 충돌 오류를 반환한다.
- Runtime 실행 불가: 같은 입력을 Wiki Agent에 전달해 대행 제출을 요청한다.
