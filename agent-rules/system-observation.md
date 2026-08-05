# System Observation Profile

## Trigger

Circled Wiki 운영 중 개별 오류·비정상 결과를 업무 지침의 부재·모호성 또는 Runtime·도구 결함으로 판단했을 때, 반복 수작업, 모호한 Agent 동작, 누락된 검증 또는 개선 기회를 발견했을 때,
또는 사용자가 대화·채널·문서에서 문제점과 개선 요청을 제기했을 때 사용한다. 이미 정의된 절차로 처리할 수 없는
절차 부재·모호성 때문에 사용자 의사 판단이 필요한 경우도, 향후 그런 실시간 판단을 줄이기 위한 관찰 이슈로 기록한다.

## Input

- 관찰한 사실과 발생 시각
- 제기 출처(`user`, `agent`, `operator`, `automation`)와 제기자 식별자
- 영향 범위와 안전한 재현 정보
- 관련된 상대 경로·Runtime Task·Intake ID·CLI 명령 중 공개 가능한 참조

## Allowed Actions

- `workspace/issues/`에 `record-system-issue`로 `Status: open` 기록 생성
- 사용자 제기 내용은 `--reported-from user`로 원문 취지를 사실·요청·가설로 구분해 기록
- CLI 실패·Validator 오류·예상과 다른 결과는 정상적인 입력·권한·Gate 결과, 업무 지침의 부재·모호성, Runtime·도구 결함으로 먼저 분류. 후자 둘로 판단한 경우에만 `--reported-from agent` 또는 실제 발생 주체로 기록하고 완료·해결을 주장하지 않음
- 기존 공식 절차로 처리할 수 없는 절차 부재·모호성으로 사용자 판단을 문의하는 경우에는 `--reported-from agent` 또는 실제 문의 주체를 사용하고, 문의 내용·막힌 작업 단계·부재하거나 모호한 절차·안전한 다음 행동을 사실과 가설로 구분해 기록
- 사실·기대 결과·실제 결과·재현 문맥·개선 가설을 구분해 기록
- 같은 이슈의 기존 `workspace/issues/` 기록과 legacy `.circled-wiki/issues/` 기록을 읽기 전용으로 찾아 연결
- 현재 설치 release와 관련 Deployment Receipt 또는 Bootstrap 적용 보고서를 안전한 범위에서 기록

## Checks

- 운영 규칙·정책·CLI·Runtime·Workflow 중 영향 영역
- 활성 하드 PII, credential, 고객 원문, 민감한 로그가 기록에서 제외되었는지. `non_sensitive_categories`로 분류된 회사·협력업체 업무 연락처는 내부 운영 기록에 필요한 경우 보존할 수 있다.
- 관찰 사실과 원인 가설이 분리되었는지

## Gates

- 활성 하드 PII·credential·`agent_mask_categories` 마스킹 대상이 남아 있으면 기록을 생성하거나 공유하지 않고 마스킹·사람 검토로 전환. 계약·법률 자문·분쟁·소송·규제 대응과 그 결정은 이 Gate만으로 차단하지 않으며, 비민감 업무 연락처도 이 Gate만으로 차단하지 않는다. 외부 공유 시 Publication Gate를 적용
- 이슈 기록만으로 OS·정책·Bundle·Runbook을 자동 변경하거나 발행하지 않음
- 일시적 입력 오류와 이미 안내된 Gate 거부는 이슈를 만들지 않고 현재 요청의 오류·다음 행동으로만 반환. 근거가 부족한 오류는 결함 또는 지침 부재로 추정하지 않음
- 이슈 기록만으로 기존 절차를 변경·차단하거나 새로운 확인 단계를 추가하지 않음
- 재현하지 못한 원인은 가설로 표시하며 해결되었다고 주장하지 않음
- 이슈 기록 자체가 실패하면 작업 완료를 주장하지 않고 실패 원인과 안전한 재시도 조건을 사용자에게 보고

## Output

- `workspace/issues/<issue-id>-<slug>.md`의 `Status: open` 기록
- 이후 Repository Engineering 또는 Owner 검토가 사용할 개선 후보
- Product Workspace로 이동되기 전까지 원본 위치에 유지되는 이슈 기록

## Failure State

기록할 정보가 민감하거나 사실을 분리할 수 없으면 이슈 파일을 만들지 않고 안전한 검토 경로를 요청한다.

## Prohibited

- API key, token, password, 활성 하드 PII, `agent_mask_categories` 마스킹 전 값, 고객 원문 기록
- 이슈를 근거로 한 자동 코드·정책·Runbook 변경
- 기존 이슈의 해결 상태를 승인 없이 `resolved`로 변경
- 제품 수정, config 변경 또는 upgrade 자동 시작
