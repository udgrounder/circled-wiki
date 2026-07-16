# System Observation Profile

## Trigger

Knowledge OS 운영 중 오류, 비정상 결과, 반복 수작업, 모호한 Agent 동작, 누락된 검증 또는 개선 기회를 발견했을 때,
또는 사용자가 대화·채널·문서에서 문제점과 개선 요청을 제기했을 때 사용한다.

## Input

- 관찰한 사실과 발생 시각
- 제기 출처(`user`, `agent`, `operator`, `automation`)와 제기자 식별자
- 영향 범위와 안전한 재현 정보
- 관련된 상대 경로·Runtime Task·Intake ID·CLI 명령 중 공개 가능한 참조

## Allowed Actions

- `.knowledge-os/issues/`에 `record-system-issue`로 `Status: open` 기록 생성
- 사용자 제기 내용은 `--reported-from user`로 원문 취지를 사실·요청·가설로 구분해 기록
- CLI 실패, Validator 오류, 예상과 다른 결과는 `--reported-from agent` 또는 실제 발생 주체로 기록하고 완료·해결을 주장하지 않음
- 사실·기대 결과·실제 결과·재현 문맥·개선 가설을 구분해 기록
- 같은 이슈의 기존 기록을 찾아 링크로 연결

## Checks

- 운영 규칙·정책·CLI·Runtime·Workflow 중 영향 영역
- 개인정보, credential, 고객 원문, 민감한 로그가 기록에서 제외되었는지
- 관찰 사실과 원인 가설이 분리되었는지

## Gates

- 민감정보가 남아 있으면 기록을 생성하거나 공유하지 않고 마스킹·사람 검토로 전환
- 이슈 기록만으로 OS·정책·Bundle·Runbook을 자동 변경하거나 발행하지 않음
- 재현하지 못한 원인은 가설로 표시하며 해결되었다고 주장하지 않음
- 이슈 기록 자체가 실패하면 작업 완료를 주장하지 않고 실패 원인과 안전한 재시도 조건을 사용자에게 보고

## Output

- `.knowledge-os/issues/<issue-id>-<slug>.md`의 `Status: open` 기록
- 이후 Repository Engineering 또는 Owner 검토가 사용할 개선 후보
- 원본 위치에 유지되는 이슈 기록과 업그레이드 직전 복구 스냅샷

## Failure State

기록할 정보가 민감하거나 사실을 분리할 수 없으면 이슈 파일을 만들지 않고 안전한 검토 경로를 요청한다.

## Prohibited

- API key, token, password, PII, 고객 원문 기록
- 이슈를 근거로 한 자동 코드·정책·Runbook 변경
- 기존 이슈의 해결 상태를 승인 없이 `resolved`로 변경
