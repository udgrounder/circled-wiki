# System Issue Triage Profile

## Trigger

사용자가 검토·승인한 Workspace Issue를 제품 결함, 설치 설정, 데이터, 운영 절차 또는 외부 의존성으로 분류한다.

## Input

- `accepted` Workspace Issue와 사용자 review receipt
- Archive 유사 이력과 관계 판정
- 안전한 재현 정보와 관찰 release

## Allowed Actions

- 재현 가능성, 영향, 우선순위와 담당 역할 평가
- `recurrence`, `regression`, `duplicate`, `related`, `new`, `undetermined` 관계 기록
- 기존 해결책·회귀 테스트·검증 결과를 후속 작업 입력으로 연결

## Checks

- 과거 fixed release의 실제 배포 여부
- 기존 회귀 테스트의 현재 release 결과
- 제품 변경 완료는 검증된 커밋 revision, 검증자와 테스트·Validator 결과
- 설치본 검증이 필요하면 현재 release ID, 검증자와 재현 불가를 보이는 명령·결과
- 설치본 확인은 사용자가 지정한 대표 Wiki 하나로 충분하며, 같은 제품 Issue의 모든 설치본을 개별 추적하지 않는다.
- 설정·schema·Runtime drift와 다른 원인 가능성

## Gates

- 민감정보가 있으면 제품 작업 생성 금지
- 사용자 review receipt 없으면 Triage 금지
- 원인 근거가 없으면 가설로 유지
- `resolved` archive는 검증된 source commit, 기존 release·deployment·독립 검증 Receipt 또는 현재 release의 식별된 검증 근거를 기록할 것
- `product_defect`가 아니면 Repository Engineering 자동 전환 금지

## Output

- 분류, 관계, 우선순위와 다음 Profile
- 재사용·추가할 회귀 테스트 범위

## Failure State

근거가 부족하면 `needs_information` 또는 `undetermined`로 Inbox에 유지한다.

## Prohibited

- 과거 해결책 자동 재적용
- 증상 유사성만으로 recurrence 확정
- Triage 결과만으로 운영 Issue 해결 주장
