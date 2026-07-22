# Knowledge OS Bootstrap and Upgrade Profile

## Trigger

사용자가 지정한 폴더에 Knowledge OS 운영 구조를 최초 설치하거나 기존 운영 OS를 업그레이드해 달라고 요청한다.

## Input

- 사용자가 지정한 프로젝트 root 폴더
- 설치 또는 업그레이드 의도
- 필요하면 충돌 제안본에 대한 사람의 선택

## Allowed Actions

- 먼저 `bootstrap-knowledge-os --target <folder>`로 변경 계획만 생성
- 사용자 확인 뒤 `--apply`로 `.circled-wiki/` 아래 누락된 규칙·템플릿·정책·스키마·Portable CLI Runtime 생성
- 대상 root에 `AGENTS.md`가 없으면 OS 참조 전용 진입점 생성; 기존 파일에 운영 규칙 참조가 없으면 표시된 참조 전용 블록만 append
- 대상 root에 `CLAUDE.md`가 없으면 Claude용 OS 참조 전용 진입점 생성; 기존 파일에 운영 규칙 참조가 없으면 표시된 참조 전용 블록만 append
- 대상 root에 `HERMES.md`가 없으면 자율형 Agent 시작 문서 참조 전용 진입점 생성; 기존 파일은 보존하고 참조 블록만 append
- 대상 root `.gitignore`가 없으면 생성하고, 기존 파일에는 Circled Wiki 생성물 제외 `BEGIN/END` 영역만 append
- `.circled-wiki/templates/.gitignore`를 기대 목록의 파일 기반 Source of Truth로 읽음
- upgrade에서 관리 영역의 라인을 템플릿과 비교하고 누락·변경이 있으면 해당 영역만 치환
- 최초 설치 시 조직 ID·표시 이름·운영 Agent·Graphify 사용 여부를 질문하거나 비대화형 옵션으로 입력받아 `.circled-wiki/config.yaml` 생성
- 기존 `.circled-wiki/` 변경 전에 `.circled-wiki-backups/<기존-version>-<UTC timestamp>/`로 전체 스냅샷 생성
- 기존 `.knowledge-os/` 설치는 백업 후 `.circled-wiki/`로 이전
- 이전 설치 manifest checksum과 일치하는 관리 파일만 업그레이드
- 충돌한 관리 파일의 새 버전을 `.circled-wiki/proposals/`에 별도 제안본으로 생성

## Checks

- 대상 폴더, manifest 형식, 이전 checksum
- 기존 파일이 OS 관리 파일인지와 사용자의 수정 여부
- 생성·업그레이드·보존·제안 항목의 계획 보고서
- 백업 필요 여부, 기존 OS version, 적용 후 생성된 백업 경로
- `.circled-wiki/bin/knowledge-os.py validate` 실행 가능 여부와 Agent Bootstrap 문서 존재
- `operational-preflight`의 release ID·실행 모듈 경로·manifest Runtime checksum 일치 여부
- `.circled-wiki/AUTONOMOUS_AGENT_STARTUP.md`, `.circled-wiki/GRAPHIFY.md`, 설치 로컬 `config.yaml` 존재
- `.circled-wiki/issues/README.md`와 `system-observation` Profile 존재; 기존 이슈 기록의 보존 상태
- root `AGENTS.md`의 생성·운영 규칙 참조 append·기존 파일 보존 상태
- root `CLAUDE.md`의 생성·운영 규칙 참조 append·기존 파일 보존 상태
- root `.gitignore`의 생성·관리 영역 append·영역 치환·기존 사용자 규칙 보존 상태

## Gates

- `--apply` 전 계획 보고서 확인
- 기존 OS 변경이 필요하면 백업 완료 전 파일 쓰기 금지
- `preserve_and_propose` 항목은 사람의 병합·교체 결정 전 원본 변경 금지
- manifest가 손상되었으면 복구 전 업그레이드 중단
- 백업 생성에 실패하면 기존 OS를 변경하지 않고 업그레이드 중단
- 대상 Runtime의 Python 3.9 이상·PyYAML 의존성을 충족하지 못하면 설치는 유지하되 CLI 실행 불가 상태를 명시
- 기존 `knowledge/`가 있으면 설치·업그레이드 전후 checksum 불변 확인
- canonical Runtime provenance가 일치하지 않으면 mutation 준비 완료로 보고하지 않음

## Output

- OS release와 마지막 백업 경로가 포함된 `.circled-wiki/manifest.json` 기반 설치·업그레이드 보고서
- `.circled-wiki-backups/` 아래의 업그레이드 직전 버전별 Control Plane 스냅샷
- 대상 프로젝트에서 실행하는 Portable CLI와 `.circled-wiki/AGENT_BOOTSTRAP.md`
- 운영 이슈 안내가 있는 `.circled-wiki/issues/`와 이후 개선 검토용 사용자 이슈 기록
- 생성·운영 규칙 참조 append·보존 중 하나인 root `AGENTS.md` Agent 진입점 상태
- 생성·운영 규칙 참조 append·보존 중 하나인 root `CLAUDE.md` Claude 진입점 상태
- 생성·시작 문서 참조 append·보존 중 하나인 root `HERMES.md` 진입점 상태
- backup·Python cache·임시 파일·Obsidian UI 상태를 제외하는 root `.gitignore` 상태
- upgrade에서 덮어쓰지 않는 설치 로컬 `.circled-wiki/config.yaml`
- 기존 자료를 보존한 운영 구조와 충돌 제안본

## Failure State

원본 파일을 변경하지 않고 계획·충돌·manifest 오류를 보고한다.

## Prohibited

- 기존 문서·Evidence·Bundle의 이동, 삭제, 이름 변경 또는 덮어쓰기
- manifest에 없는 기존 파일을 OS 소유로 자동 선언
- 충돌한 템플릿·정책·규칙을 자동 병합
- 사용자 지정 밖 폴더 변경
- `.circled-wiki-backups/`에 `knowledge/` 또는 다른 사용자 자료 포함
- 기존 root `AGENTS.md`의 기존 내용 덮어쓰기·OS 관리 자산 등록
- 기존 root `CLAUDE.md`의 기존 내용 덮어쓰기·OS 관리 자산 등록
- 기존 root `HERMES.md`의 기존 내용 덮어쓰기·OS 관리 자산 등록
- 기존 root `.gitignore` 규칙의 삭제·덮어쓰기
- `.circled-wiki/issues/`의 기존 운영 이슈 기록 덮어쓰기·삭제·Control Plane 관리 자산 등록
- 업그레이드 중 `knowledge/` 아래 파일·폴더 생성 또는 수정
