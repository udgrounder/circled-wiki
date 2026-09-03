# 사용자 알림 즉시 정리 변경 계획서

**상태:** Implemented — source 검증 완료, release·운영본 배포 대기  
**대상:** Circled Wiki Runtime의 `workspace/notifications/`  
**결정:** 해결된 사용자 알림은 archive로 이동하지 않고 즉시 삭제한다.

## 1. 배경과 목표

현재 Runtime은 Curation Review 등이 해결되면 열린 알림을
`workspace/notifications/archive/notification-<uuid>.json`으로 이동한다. 이 파일은 실제
결정이나 지식의 정본이 아니라 사용자에게 보여 주기 위한 projection이다. Curation Review의 결정은
`knowledge/curation-reviews/.archive/`에, Bundle 변경의 근거는 Bundle과 그 provenance에, Inbox
검토 결과는 해당 작업 receipt에 남는다.

운영 설치본에서 확인한 archive 알림은 모두 해결된 `review_requested` 이벤트이며, 원본 Review가
이미 정본으로 남아 있다. 따라서 동일한 정보를 다시 보존하는 notification archive는 운영 자료를
불필요하게 늘리고, 검색·리포트가 잘못된 경로를 훑을 위험을 높인다.

이 변경의 목표는 다음과 같다.

- 열린 사용자 알림만 `workspace/notifications/inbox/`에 유지한다.
- source workflow가 해결되거나 사용자가 명시적으로 철회한 알림은 파일을 즉시 삭제한다.
- 승인 여부와 업무 결정의 정본은 기존 Curation Review·taxonomy proposal·Bundle·작업 receipt에
  계속 남긴다.
- 기존 설치본의 `workspace/`는 upgrade가 수정하거나 삭제하지 않는다.

## 2. 범위와 비범위

| 구분 | 포함 | 제외 |
| --- | --- | --- |
| Runtime | 알림 해소 시 archive 이동 대신 안전한 삭제 | Curation Review·Bundle·Evidence·Inbox 작업 receipt의 archive 정책 변경 |
| 규칙·문서 | `RB-NOTIFY-001`, Bootstrap 설명, 사용자 안내의 알림 수명주기 동기화 | 운영 지식(`knowledge/`)의 내용 변경 |
| CLI·API | archive라는 용어와 결과를 삭제 의미에 맞게 정리 | 알림 생성 이벤트·dedupe·acknowledgement의 의미 변경 |
| 기존 데이터 | 별도 승인된 운영 정리 절차를 위한 read-only inventory 제공 가능 | upgrade 또는 Runtime 자동 실행으로 기존 `workspace/notifications/archive/` 삭제 |

기존 archive를 지우는 작업은 사용자 소유 운영 Workspace를 변경하는 별도 작업이다. 이 제품 변경의
release·upgrade 범위에 포함하지 않는다.

## 3. 목표 상태와 수명주기

```text
알림 생성
  -> workspace/notifications/inbox/notification-<uuid>.json
  -> acknowledgement (선택 사항)
  -> 원본 workflow 해결 또는 명시적 철회
  -> 알림 JSON + acknowledgement JSON 삭제

결정·감사 근거
  -> Curation Review / taxonomy proposal / Bundle / Inbox 작업 receipt에 계속 보존
```

`workspace/notifications/archive/`는 새 Runtime이 만들거나 읽지 않는 legacy 경로가 된다. 기본
알림 조회와 dedupe는 언제나 inbox만 대상으로 한다.

## 4. 설계 결정

### 4.1 정본과 projection의 분리

알림 JSON에는 `resource_ref`, 제목, 요약, 다음 행동만 남는다. 이 값은 원본 workflow 상태를
대체하지 않으므로, 원본이 해결된 뒤 보존할 필요가 없다. 삭제 실패는 원본 Curation Review·Bundle
결정을 되돌리거나 실패로 바꾸지 않는다.

### 4.2 acknowledgement 처리

acknowledgement는 열린 알림에 대한 보조 기록이다. 알림이 해소·철회되면 동일한
`notification_id`의 acknowledgement도 함께 삭제한다. 이로써 삭제된 알림 ID만 참조하는 orphan
acknowledgement가 남지 않는다.

`require_acknowledged_user_notification()`처럼 아직 열려 있는 알림의 acknowledgement를 Gate로
사용하는 경로는 유지한다. 해당 Gate를 통과한 뒤 workflow가 해결될 때에만 두 파일을 정리한다.

### 4.3 공개 API와 CLI 호환성

현재 `archive_user_notification()` 및 `archive_notifications_for_resource()`는 내부적으로 archive
파일을 만드는 이름이다. 구현 시에는 다음 중 하나를 확정한다.

1. 새 `dismiss_user_notification()` 및 `dismiss_notifications_for_resource()`를 정식 API로 제공하고,
   이전 archive 함수는 같은 삭제 동작을 수행하는 호환 wrapper로 한 release 유지한다.
2. CLI는 `archive-user-notification`의 명칭을 `dismiss-user-notification`으로 바꾸고, 이전 명령은
   deprecation 안내를 낸 뒤 다음 major release에서 제거한다.

호환 wrapper의 반환값에는 더 이상 `archived_at`·`archive_reason`을 쓰지 않는다. 대신
`deleted: true`, `notification_id`, `reason`만 반환해 호출자가 archive 파일의 존재를 기대하지 않도록
한다.

## 5. 구현 단계

1. **재현 테스트 추가**
   - 해결된 Curation Review의 알림이 inbox와 acknowledgement에서 제거되고 archive가 만들어지지
     않는 실패 테스트를 추가한다.
   - 명시적 알림 철회도 같은 정리를 수행하는지 검증한다.
   - acknowledgement가 필요한 reclassification Gate는 해소 전까지 계속 동작하는 회귀 테스트를
     추가한다.

2. **Runtime 저장소 변경**
   - `src/circled_wiki/runtime/core/notification_store.py`에 원자적 알림 삭제 helper를 만든다.
   - inbox 알림과 동일 ID acknowledgement를 함께 삭제하고, 이미 없는 acknowledgement는 성공으로
     취급한다.
   - resource 기준 일괄 해소 함수는 inbox의 일치 항목만 삭제한다.
   - archive 디렉터리를 생성하거나 새 JSON을 쓰는 코드를 제거한다.

3. **호출부·CLI 정리**
   - `curation_reviews.py`의 해결 후 알림 처리 호출을 새 삭제 API로 전환한다.
   - Runtime CLI의 명령·출력·도움말을 새 동작에 맞춘다. 호환 명령을 유지한다면 deprecation을
     명확히 출력한다.
   - Service/MCP에서 알림 archive 위치나 archive 결과를 노출하는 경로가 없는지 확인한다.

4. **규칙과 사용자 문서 동기화**
   - `OPERATING_RULES.md`의 RB-NOTIFY-001에서 “archive로 자동 이동”을 “inbox와 acknowledgement를
     삭제”로 바꾸고, 결정의 정본 위치를 명시한다.
   - `.circled-wiki/AGENT_BOOTSTRAP.md`, 필요 시 `docs/17-human-guide.md`의 알림 설명을 같은
     수명주기로 맞춘다.
   - archive retention을 전제로 한 테스트·예시·문서를 제거하거나 업데이트한다.

5. **기존 운영 archive의 별도 처리**
   - release에는 운영 Workspace를 건드리는 migration을 넣지 않는다.
   - 사용자가 요청한 설치본에 한해 `workspace/notifications/archive/`의 파일 수·이벤트·참조 대상
     inventory를 read-only로 제시한다.
   - 사용자가 별도로 승인하면, Git 상태와 대상 경로를 확인한 뒤 해당 설치본의 legacy archive와
     orphan acknowledgement만 삭제하고 결과를 보고한다.

## 6. 검증 기준

변경 후 다음을 검증한다.

- 새 `review_requested` 알림을 만들고 관련 Review를 해결하면 inbox 알림과 acknowledgement가
  사라지고 `workspace/notifications/archive/`가 생성되지 않는다.
- 알림 해소가 Curation Review의 archive·Bundle 생성·no-bundle receipt를 손상시키지 않는다.
- acknowledgement가 필요한 작업은 원본 workflow가 해결되기 전에는 계속 확인 가능하다.
- 동일 `dedupe_key`의 열린 알림은 기존처럼 하나로 재사용된다.
- archive가 이미 존재하는 설치본도 validate·일반 알림 조회·Runtime upgrade에서 실패하지 않으며,
  기존 파일은 변경되지 않는다.
- source repository에서 다음 Gate를 통과한다.

```sh
PYTHONPATH=src python3 -m circled_wiki.cli validate
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

## 7. 릴리스 및 운영 적용

이 변경은 Runtime 코드·규칙·CLI 동작 변경이므로 제품 source에서 release를 준비한 뒤, 승인된 절차로
설치본의 Control Plane만 upgrade한다. Canary에서는 새 Review 하나를 생성·해결하여 알림이 즉시
사라지고 Curation Review receipt가 보존되는지 확인한다.

기존 `workspace/notifications/archive/` 정리는 canary 검증과 독립된 명시적 운영 요청으로만 수행한다.
이 구분은 upgrade가 사용자 Workspace를 보존해야 한다는 제품 불변식을 지킨다.

## 8. 롤백

Runtime 변경 배포 후 알림 정리가 승인 Gate를 우회하거나 open 알림을 잘못 삭제하면, Control Plane
backup으로 Runtime을 rollback한다. 이미 삭제된 projection은 원본 workflow에서 다시 알림을 생성할 수
있지만, 그 전제는 원본 결정 receipt가 온전하다는 것이다. 따라서 rollout 전에는 Curation Review·taxonomy
approval·reclassification의 Gate 회귀 테스트가 필수다.
