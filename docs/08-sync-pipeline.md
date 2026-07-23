# 수집 및 동기화 파이프라인

## 1. 목적

사용자·지정 Batch·Hermes가 제공한 원본을 Evidence로 안정적으로 수집·축적해 회사 전용 지식 라이브러리를 갱신하는 파이프라인을 정의한다.

## 2. 입력 소스

- Notion
- Slack
- GitHub PR / Issue
- Jira
- 회의록
- 수기 업로드

입력 파일 예시:

- `md`
- `pdf`
- `xlsx`
- `csv`
- `json`
- 이미지 파일
- 압축파일

## 3. 단계

### 단계 1: 수집

- 사용자·지정 Batch·Hermes는 `capture_conversation`, `capture_document`, `capture_file` 중 입력에 맞는 Capture API를 사용한다.
- Capture는 원문과 메타데이터를 `pending` Inbox Item으로 저장하고 Capture Receipt를 반환한다.
- 지정 Batch는 자체 스케줄·watermark로 변경분을 수집하고 안정적인 `idempotency_key`를 전달한다.
- 수집 시 `source_ref`, `why_collected`, `intended_use`를 확보한다.
- 이 단계에서는 Evidence를 생성하거나 정제하지 않는다.
- Circled Wiki는 Provider 스케줄러를 소유하지 않고 공통 Capture 이후만 책임진다.

### 단계 2: Inbox 검사와 승인

- `inspect_inbox`가 checksum, 필수 메타데이터, provider 폴더와 Inbox Sensitive Data Review 상태를 검사한다.
- `sensitivity_review: required`는 식별된 사람이 `review_inbox_sensitivity`로 완료·비해당 결정을 기록한다.
- 모든 Gate를 통과한 Inbox Item만 `accept_inbox`로 `accepted` 상태가 된다.
- Capture Agent는 자신이 수집한 항목을 자동 승인하지 않는다.

### 단계 3: Evidence 변환 준비

- `ingest_accepted`가 `accepted` Inbox Item만 처리한다.
- 처리 중 원문을 `inbox/`에서 `.raw/`로 이동한다.
- 이동 시 `source_uuid` 발급
- provider 공통 필드와 URI·timestamp를 정규화
- 처리 단위별 작업 상태와 락 정보 기록 가능
- `source_ref` 보존
- 외부 ID와 내부 UUID 매핑
- 작업 파일명 또는 작업 메타데이터에 `source_uuid` 기록

### 단계 4: Evidence 생성

- 저장 경로 결정
- checksum 생성
- 상태 `new` 기록
- Evidence 파일명과 `source_uuid` 일치
- Evidence 파일 경로는 `{name}_{source_uuid}.{ext}` 패턴을 사용
- 외부 파일은 Evidence Original을 `evidence/`에 보존하고 동일 basename의 External-file Evidence Manifest를 생성
- 시스템 생성 텍스트는 Evidence Record와 Evidence Original을 합친 Embedded Evidence Document로 생성
- 외부 Evidence Original이 10MB 이하이면 External-file Evidence Manifest와 함께 Git에 추적
- 외부 Evidence Original이 10MB를 초과하면 Git에서 제외하고 별도 원본 저장소에 보존하며 External-file Evidence Manifest에는 checksum과 보관 위치를 기록
- `source_ref`와 `curated_into` 초기화
- `extensions.capture_context`에 수집 이유와 적용 업무 기록

### 단계 5: 큐레이션 요청

- Hermes Curator에 작업 위임

### 단계 6: 결과 반영

- Bundle 생성/갱신
- 실행 절차는 해당 도메인의 `runbooks/`에 Runbook으로 생성·갱신
- 장기 미해결 사항은 Inquiry 후보로 분리
- Evidence 상태 변경
- 인덱스 갱신 트리거
- 처리 성공 시 `.raw/` 항목 즉시 삭제
- 처리 실패 또는 검토 필요 시 `.raw/` 항목 보존
- Bundle과 운영 로그에 동일 `source_uuid` 연결
- OKF/Profile Validator 통과 시 자동 Commit
- Validator 실패 시 Commit 금지

## 4. 상태 전이

```text
inbox
  -> inspect / accept
  -> .raw
  -> Evidence Record + Evidence Original
  -> bundles
```

상태 의미:

- `inbox`: 검사·승인을 기다리는 Inbox Item 저장 공간
- `.raw`: 처리 시작 후 UUID가 발급된 원본 작업 공간
- `evidence`: Evidence Original과 Evidence Record의 보존 위치
- `bundles`: Evidence를 기반으로 정제된 공식 지식

주의:

- `inbox`와 `.raw`에는 `pdf`, `xlsx`, 이미지 같은 비Markdown 파일이 들어올 수 있다.
- `evidence`에도 보존 대상 원본 파일은 비Markdown 형태로 저장될 수 있다.
- `evidence`의 비Markdown 원본도 10MB 이하이면 Git에 추적할 수 있다. 10MB 초과 원본은 Git에서 제외하고 별도 원본 저장소에 보존한다.
- `bundles`에는 정제된 OKF Markdown 문서만 저장한다.

## 5. 파이프라인 정책

- 재실행 가능해야 한다.
- 중복 입력 감지가 가능해야 한다.
- Batch는 외부 객체와 revision을 식별하는 안정적인 `idempotency_key`를 사용한다.
- 동일 키·동일 checksum은 기존 Evidence를 재사용하고, 동일 키·다른 checksum은 충돌로 처리한다.
- 실패한 항목은 재처리 가능해야 한다.
- 사람 검토가 필요한 항목은 분리 큐로 보낸다.
- `.raw/` 항목은 처리 중단 후에도 복구 가능해야 한다.
- 처리 성공 상태가 확정되면 `.raw/` 항목은 즉시 삭제한다.
- 처리 실패, 검토 필요, 중단 상태에서는 `.raw/` 항목을 보존한다.
- UUID는 작업 시작 시 한 번만 발급하고 후속 단계에서 재사용해야 한다.
- 수집 목적이 없는 입력은 자동 큐레이션하지 않고 보완 입력을 요청한다.

## 6. 운영 고려사항

- API rate limit 대응(스케줄 폴링 주기로 상당 부분 완화됨)
- provider별 watermark/cursor 저장소 관리
- 외부 원본의 변경 시점, 외부 ID, 수집 시점 및 스냅샷 관계 관리
- 첨부파일/이미지/OCR 처리 범위
- 민감정보 마스킹
- 작업 중간 산출물의 실패/검토 상태 보존 정책
