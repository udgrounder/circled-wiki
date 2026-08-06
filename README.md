# Circled Wiki

Circled Wiki는 Git과 Markdown을 기반으로 조직 지식을 수집·검토·발행하고, AI Agent가 안전하게 조회·운영할 수 있게 하는 Python 기반 Knowledge Operating System입니다.

이 저장소는 **제품의 Source of Truth**입니다. 여기서 구현, Runtime 규칙, 설치·업그레이드 도구, 테스트와 제품 문서를 관리합니다. 실제 조직 지식과 운영 중 생성되는 작업물은 설치된 Wiki의 `knowledge/`와 `workspace/`에 속하며, 일반 업그레이드가 이를 덮어쓰지 않습니다.

## 구성

```text
circled-wiki/
├── src/circled_wiki/
│   ├── runtime/       # 설치 Wiki에서 실행되는 CLI, Core, MCP, worker
│   └── engineering/   # Source repository 전용 Issue·release·receipt 도구
├── tests/             # 단위·통합 테스트
├── docs/              # 제품 기획·설계 Reference
├── agent-rules/       # 설치 Wiki Runtime 작업 Profile
├── product-agent-rules/ # 제품 개발·release·배포 Profile
├── OPERATING_RULES.md # Runtime 전역 운영 규약
├── PRODUCT_ENGINEERING_RULES.md
├── workspace/         # 제품 Issue·release 이력 Working Plane
└── pyproject.toml
```

경계는 다음과 같습니다.

| 구분 | 정본 | 역할 |
| --- | --- | --- |
| 제품 개발 | `PRODUCT_ENGINEERING_RULES.md`, `product-agent-rules/` | 구현·테스트·release·배포 절차 |
| 설치 Wiki 운영 | `OPERATING_RULES.md`, `agent-rules/` | 지식 수집·검토·발행·조회 규칙 |
| 공식 지식 | 설치 Wiki의 `knowledge/` | Bundle과 Evidence |
| 제품 작업 이력 | `workspace/` | 운영 Issue, release manifest, receipt |

`circled-wiki`는 Runtime CLI 이름이고, `circled_wiki`는 Python package 이름입니다. 제품 전용 CLI는 `circled-wiki-product`입니다.

## 시작하기

Python 3.9 이상이 필요합니다. 개발 환경에서는 editable 설치와 개발 의존성을 함께 설치합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

설치하지 않고 저장소에서 바로 실행할 수도 있습니다.

```sh
PYTHONPATH=src python3 -m circled_wiki.runtime.cli.__main__ --help
PYTHONPATH=src python3 -m circled_wiki.engineering.cli --help
```

## 검증

변경 전후에는 Runtime Validator와 전체 테스트를 실행합니다.

```sh
PYTHONPATH=src python3 -m circled_wiki.runtime.cli.__main__ validate
PYTHONPATH=src python3 -m unittest discover -s tests -q
```

개발 의존성을 설치했다면 아래 명령도 사용할 수 있습니다.

```sh
python3 -m pytest
```

## 새 Wiki 설치 또는 안전한 업그레이드

대상은 `knowledge/` 폴더 자체가 아니라 이를 포함할 프로젝트 루트입니다. 먼저 변경 계획을 확인하고, 결과를 검토한 뒤에만 `--apply`를 사용합니다.

```sh
circled-wiki bootstrap-circled-wiki --target /path/to/wiki-project
circled-wiki bootstrap-circled-wiki --target /path/to/wiki-project --apply
```

설치·업그레이드는 관리 자산만 갱신하며, 기존 `knowledge/`, `workspace/`, 설치 로컬 설정은 보존합니다. 자세한 Gate와 복구 절차는 [bootstrap-circled-wiki.md](product-agent-rules/bootstrap-circled-wiki.md)를 따릅니다.

## Runtime의 기본 흐름

```text
원본 수집 → Inbox 검사·민감정보 검토 → Evidence 변환
       → Curation 후보·검토 → Bundle 발행 → 검색·Workflow 활용
```

대표 명령은 다음과 같습니다. 실제 운영에서는 설치 Wiki의 Runtime 규칙과 단계별 Profile을 먼저 확인해야 합니다.

```sh
# 현재 관리 문서 검증
circled-wiki validate

# 원본을 Inbox에 수집
circled-wiki capture-document --help

# Inbox 상태 검사 및 처리
circled-wiki inspect-inbox --limit 100
circled-wiki reconcile-inbox --actor <operator> --limit 100

# 공식 지식 검색 및 읽기
circled-wiki search --help
circled-wiki read-bundle --help
```

운영 절차는 [사람 사용자 가이드](docs/17-human-guide.md), [Agent 가이드](docs/18-agent-guide.md), [Runtime 작업 Profile](agent-rules/README.md)을 참고합니다. `OPERATING_RULES.md`가 Runtime 규약의 유일한 정본이며, 문서 설명과 충돌할 경우 규약과 Validator를 우선합니다.

## 제품 Issue·release 작업

운영에서 발견된 문제를 제품 개선으로 연결할 때는 다음 순서를 지킵니다.

```text
명시적 Issue 수집 → 사용자 검토 → triage → 구현·회귀 테스트
→ release 준비 → 승인된 배포 → 독립 Runtime 검증
```

제품 CLI는 `workspace/`를 기본 작업 위치로 사용합니다.

```sh
circled-wiki-product --help
circled-wiki-product intake-operational-issue --help
circled-wiki-product prepare-release --help
```

Issue 수집·triage·release·배포는 각각 별도의 Profile과 Gate를 따릅니다. 제품 변경이 완료됐다는 사실만으로 설치 Wiki의 운영 문제가 해결됐다고 처리하지 않습니다.

## 주요 문서

- [제품 개발 규칙](PRODUCT_ENGINEERING_RULES.md)
- [제품 작업 Profile](product-agent-rules/README.md)
- [Runtime 전역 운영 규약](OPERATING_RULES.md)
- [Runtime 작업 Profile](agent-rules/README.md)
- [설계 문서 인덱스](docs/README.md)
- [구현 계획](docs/15-implementation-plan.md)
- [MVP 이후 작업](docs/13-future-work.md)

## 개발 원칙

- 조직명, 자격 증명, 사용자 원문, 머신 절대 경로를 제품 기본값에 넣지 않습니다.
- `knowledge/`와 설치된 Wiki의 `workspace/`는 사용자 관리 자산으로 취급합니다.
- Runtime 배포물에 Product Profile과 source-only 제품 문서를 포함하지 않습니다.
- 커밋·push·외부 배포는 명시적으로 승인된 범위에서만 수행합니다.
