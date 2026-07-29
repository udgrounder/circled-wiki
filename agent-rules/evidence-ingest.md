# Evidence Ingest Profile

## Trigger

`accepted` Inbox 항목을 추적 가능한 Evidence로 변환한다.

## Input

- 승인된 Inbox Item, 검사 기록, 외부 문서의 `source_ref`

## Allowed Actions

- `.raw/` 경유
- source UUID와 Evidence ID 발급
- Embedded Evidence Document 또는 Evidence Original+External-file Evidence Manifest 생성
- 원본 checksum과 출처 보존
- **Inbox를 읽어 Evidence를 만들기 직전** 주민등록번호·계좌/카드번호와 API key·password·token·private key 등 자격증명을 다시 점검한다. 텍스트 Inbox에서 발견하면 실제 값 없이 범주만 결과에 기록하고 `********`로 마스킹한 안전한 Evidence 입력을 생성한다.
- 실제 PII Scan을 완료했다면 `record-evidence-pii-scan` 또는 동등한 원자적 기록 작업으로 `pii_scanned`와 `extensions.pii_scan` 영수증을 함께 기록한다. 영수증은 scanner·version·시각·결과·검토자·receipt·현재 checksum을 포함한다.

## Checks

- idempotency key로 기존 Evidence 재사용 여부
- 저장 크기와 보존 방식
- Inbox Item과 변환할 텍스트를 직접 다시 읽어 자격증명·PII 평문, 과소 마스킹과 문맥상 재식별 가능성을 확인
- 파일형 입력은 불변 원본과 Evidence에 사용할 마스킹 파생본이 분리되어 있는지 확인

## Gates

- Inbox 상태 `accepted`
- 승인된 검사 기록
- Evidence Schema와 원본 checksum 일치
- 처리 Agent의 마스킹 재확인 통과; 평문·고위험·판단 불가 항목은 Evidence를 생성하지 않고 `needs_review`
- 수집 Agent의 1차 점검 결과와 무관하게 Ingest Agent의 재검수·안전한 텍스트 파생본 생성 완료. 이 재검수는 Evidence 변환 작업의 일부이며 PII Scan 영수증이나 Draft·Commit·Push Gate를 만들지 않는다.
- PII Scan 결과가 `passed` 또는 `masked`이면 같은 변경의 영수증 `source_checksum`이 현재 Evidence checksum과 일치한다. `needs_review`이면 `pii_scanned: false`다.

## Output

Evidence ID와 보존 경로. 실제 PII Scan을 수행했으면 checksum 결합 PII Scan 영수증.

## Failure State

Inbox 원본과 필요 시 `.raw/`를 유지하고 Evidence 변환 실패를 반환한다. 마스킹 재확인 실패 시 발견한 값 자체를
로그·Issue·응답에 복사하지 않고 범주와 재검토 조건만 기록한다.
실제 Scan 영수증을 만들 수 없으면 `pii_scanned: false`를 유지하고 검토 대기로 남긴다.

## Prohibited

- Bundle 생성·수정
- 의미 기반 정제 또는 자동 승격
- `pending`, `needs_review` 입력 ingest
- 평문 자격증명·PII가 남은 입력 또는 안전한 마스킹 파생본이 없는 파일 ingest
- 마스킹 재확인만으로 `pii_scanned: true` 기록
- `pii_scanned: true`만 기록하고 scanner·version·시각·결과·검토자·receipt·현재 checksum이 있는 `pii_scan` 영수증을 같은 변경에 남기지 않기
