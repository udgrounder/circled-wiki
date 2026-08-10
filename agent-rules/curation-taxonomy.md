# Curation Taxonomy Profile

## Trigger

설치별 `curation-taxonomy.yaml`을 만들거나 검토·갱신하거나, 이를 근거로 Bundle 재분류를 제안한다.

## Input

- 설치별 taxonomy 파일 또는 파일 부재 사실
- 관련 Bundle의 제목·요약·type·domain·태그·경로
- 사용자 승인된 taxonomy와, 기존 재분류에는 해당 영향 알림 뒤의 사용자 명시 요청

## Allowed Actions

- JSON Schema에 맞는 YAML taxonomy 초안·검토 제안
- 기존 Bundle의 read-only 재분류 proposal
- 승인된 taxonomy 갱신, 그리고 별도 사용자 요청에 따른 revision-bound 재분류 적용

## Source of Truth

- `.circled-wiki/curation-taxonomy.yaml`: 설치별 taxonomy 규칙
- `.circled-wiki/schemas/schema-registry.json`과 현재 버전의 `curation-taxonomy.schema.v<version>.json`: 기계 검증 형식
- `OPERATING_RULES.md` RB-KNW-027: 권한·부재 처리·재분류 불변식
- `OPERATING_RULES.md` RB-NOTIFY-001: taxonomy 개선·재분류 영향 알림 형식과 승인 경계

## Rules

- `match_terms`는 Evidence 제목 또는 `intended_use`에 모두 나타날 때만 rule 후보가 된다.
- `domains`는 설치별 승인 domain 카탈로그이며 각 `id`의 필수 `description`이 Agent의 분류 경계다. rule의 `domain`은 반드시 등록된 domain이어야 한다. `bundle_type`, `slug_prefix`는 새 문서 또는 재분류의 힌트이며, 기존 Bundle 후보 탐색과 의미 검증을 대체하지 않는다. `routing_hints`는 이 설치별 정책을 제안 결과로 보인 것이며 `suggested_bundle_type`보다 분류 정책상 우선하지만 기존 Bundle을 선택하거나 재분류하지는 않는다. `candidate_bundles`는 탐색 후보일 뿐 빈 목록도 부재 증명이 아니다. `auto_create: true`는 단일 rule이 일치하고 발견된 후보가 없을 때만 `creation_authorized`로 신규 Draft 검토를 허용하며, 생성 결과의 사용자 알림을 Bundle Curation 이력에 기록한다.
- 파일이 없으면 관련 Bundle의 제목·요약·type·domain·태그·경로를 조사해 초안을 제시하고, 사용자 승인 전에는 파일을 만들지 않는다.
- taxonomy 승인과 새 domain·Bundle 생성은 앞으로의 분류에만 적용한다. 영향 Bundle 목록은 자동으로 제안·알림할 수 있지만, 기존 Bundle의 domain·type·경로는 바꾸지 않는다.
- Agent는 한 번의 Evidence나 Bundle만으로 규칙을 일반화하지 않는다. 충돌·예외·불충분 근거는 rule을 만들지 않고 `needs_review`로 남긴다.
- 기존 Bundle 재분류는 사용자가 영향 알림을 확인한 뒤 명시적으로 요청한 경우에만 `propose-bundle-reclassification`으로 영향·현재 revision을 확인하고, acknowledgement가 존재하는 해당 `reclassification_ready` notification ID, 명시적 actor·rationale을 모두 기록한 `apply-bundle-reclassification`만 사용한다. 적용 target은 승인된 taxonomy domain 및 그 notification의 영향 목록·제안 route와 일치해야 한다.

## Checks

- Registry가 가리키는 `curation-taxonomy.schema.v<version>.json`의 형식과 안전한 식별자 규칙. 현재 v1 domain과 Rule은 Agent가 분류 경계를 이해할 수 있는 비어 있지 않은 `description`을 반드시 포함하며, 모든 Rule domain은 catalog에 존재해야 한다.
- rule 간 중복·상충과 기존 Bundle 분류와의 차이
- 재분류 대상의 현재 revision, ID·UUID·Evidence 참조 보존

## Gates

- taxonomy 신규 생성·변경에는 사용자 승인
- 기존 Bundle 이동에는 사용자 명시 요청, acknowledgement된 영향 notification ID, read-only proposal과 일치하는 expected revision·actor·rationale
- 적용 후 전체 Validator 통과

## Output

- 승인 대기 taxonomy 초안 또는 검증된 taxonomy 변경
- 영향·이전/새 경로·복구 조건을 가진 재분류 proposal 또는 적용 결과
- taxonomy 개선 제안 또는 재분류 준비 시 RB-NOTIFY-001 형식의 `user_notification`

## Failure State

근거가 불충분하거나 rule이 충돌하면 taxonomy를 변경하지 않고 `needs_review`로 유지한다. Validator 실패 시 재분류는 원복하고 원인을 반환한다.

## Prohibited

- taxonomy rule만으로 기존 Bundle 탐색·의미 검증·발행·재분류 Gate를 우회
- Bundle ID, UUID, Evidence 관계를 바꾸는 재분류
- 설치별 taxonomy를 제품 기본값 또는 다른 Wiki에 복사
