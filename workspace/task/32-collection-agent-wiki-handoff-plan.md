# 수집 Agent → Wiki Agent Handoff 변경 계획서

**상태:** Proposed
**작성일:** 2026-08-11  
**목적:** 수집 Agent가 현재 적용해야 할 수집 방식을 Handoff 버전으로 관리하고, 원문 Inbox 등록은 Runtime이 일관되게 처리하게 한다.

## 1. 최종 절차

```text
Collection Agent
  → get-collection-handoff()
Wiki Runtime
  → handoff_version + 메소드 스펙 문서 위치 + 수집 가이드 문서 위치

Collection Agent
  → 저장한 handoff_version과 비교
    ├─ 처음이거나 변경됨: 두 문서를 읽고 수집 방식 갱신
    └─ 동일: 이미 적용한 방식 사용
  → 원문과 수집 시점 메타데이터 제출

Runtime ingest.py
  → 입력 검사 · 민감정보 사전 처리 · checksum · idempotency 확인
  → 정식 Inbox 생성 · 검토 Queue 등록 · 결과 회신
```

Runtime 실행 권한이 없는 Collection Agent는 같은 원문·메타데이터를 Wiki Agent에 전달한다. Wiki Agent가 동일한 Runtime 입력 메소드를 대행 호출한다.

## 2. Handoff 응답

`get-collection-handoff()`은 원문이나 문서 본문을 반환하지 않는다.

```json
{
  "handoff_version": "v1",
  "method_spec_document": ".circled-wiki/contracts/INBOX_INPUT_METHODS.md",
  "collection_guide_document": ".circled-wiki/contracts/COLLECTION_HANDOFF.md"
}
```

- `handoff_version`은 Collection Agent가 마지막으로 적용한 수집 방식을 갱신할지 판단하는 값이다.
- 버전이 같으면 문서를 다시 읽지 않는다.
- 버전이 없거나 달라지면 두 문서를 읽고 적용 상태를 갱신한다.
- Runtime은 제출 시점에 실제 입력을 검사한다. Collection Agent는 계약 버전을 입력값으로 넣거나 사전 검증하지 않는다.

## 3. 문서 책임

| 문서 | 정본 내용 | 독자 |
| --- | --- | --- |
| `INBOX_INPUT_METHODS.md` | `capture_document`, `capture_conversation`, `capture_file`의 목적, 필수·선택 파라미터, 각 파라미터 설명 | Collection Agent |
| `COLLECTION_HANDOFF.md` | 출처 맥락, idempotency, Transcript, Notion·Slack 수집 품질 규칙 | Collection Agent |
| `ingest.py` | 실제 입력 검사, 마스킹, checksum, 중복 방지, Inbox 생성 | Runtime |

Schema는 Runtime 내부의 구현·테스트 계약으로 유지할 수 있으나, Collection Agent가 직접 해석하거나 전달받는 절차에는 포함하지 않는다.

## 4. 구현 범위

1. `ingest.py`의 원문 등록 함수는 Collection Agent가 계약 버전을 전달하지 않아도 현재 Runtime 규칙으로 처리한다.
2. `.circled-wiki/contracts/INBOX_INPUT_METHODS.md`를 만들고, Runtime의 실제 입력 메소드와 동기화한다.
3. `get-collection-handoff()`은 문서 본문·세부 스펙 대신 Handoff 버전과 두 문서 경로만 반환한다.
4. Bootstrap·README·외부 수집 연결 문서는 위 절차와 동일한 표현으로 갱신한다.
5. Runtime 실행 불가 시 Wiki Agent 대행은 같은 메소드 입력을 사용하며, 원문을 추정·재작성하지 않는다.

## 5. 검증 계획

- Handoff 응답이 정확히 버전과 두 문서 경로만 반환하는지 단위 테스트한다.
- 버전 최초 수신·동일·변경의 Collection Agent 적용 시나리오를 문서 테스트로 확인한다.
- 세 원문 유형이 계약 버전 입력 없이 정상 Inbox·검토 Queue를 생성하는지 통합 테스트한다.
- 입력 누락·idempotency 충돌 시 Inbox 생성 없이 재시도 가능한 오류를 반환하는지 확인한다.
- `PYTHONPATH=src python3 -m circled_wiki.cli validate`와 전체 `unittest discover`를 실행한다.

## 6. 완료 기준

Collection Agent는 Handoff 버전만 비교해 수집 규칙을 갱신하고, 동일 버전에서는 기존 방식을 그대로 사용한다. 원문 등록의 형식·검증·Inbox 생성 책임은 Runtime 한 곳에 남으며, Runtime을 실행하지 못하는 경우에도 Wiki Agent 대행으로 같은 결과를 얻는다.
