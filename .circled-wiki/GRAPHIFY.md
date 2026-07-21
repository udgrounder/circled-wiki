# Optional Graphify Integration

Graphify는 Knowledge OS와 별도로 설치·업그레이드하는 선택적 로컬 지식 그래프다. Knowledge OS의 Source of Truth나
발행 Gate를 대체하지 않는다.

## Install Separately

Graphify 공식 문서가 안내하는 패키지 이름은 `graphifyy`다. 운영 머신의 격리된 tool 환경에 설치한다.
설치 전 [공식 Quickstart](https://graphify.com/docs)와 [CLI reference](https://graphify.com/docs/cli)를 확인한다.

```sh
uv tool install graphifyy
graphify install
```

설치 명령은 Knowledge OS bootstrap이 자동 실행하지 않는다. 버전, 라이선스, 외부 LLM 사용 여부와 데이터 반출
정책을 운영자가 확인한 뒤 실행한다.

## Build and Serve

프로젝트 root에서 Graphify skill 또는 CLI로 `.circled-wiki/config.yaml`의 `graphify.source_paths`만 인덱싱한다.
기본값은 `knowledge/bundles/`뿐이다. `knowledge/evidence/`, `knowledge/inbox/`, `knowledge/.raw/`, `.runtime/`은
민감 원문과 실행 상태를 포함할 수 있으므로 기본 graph 입력에서 제외한다. Evidence를 추가하려면 별도 보안 검토와
보존 정책 승인을 거친다. 생성 위치는 `graphify.graph_path`와 일치시키며 기본값은 `graphify-out/graph.json`이다.

stdio MCP 예시:

```json
{
  "mcpServers": {
    "circled-wiki": {
      "command": "python3",
      "args": ["-m", "knowledge_os.mcp.server"],
      "cwd": ".",
      "env": {
        "PYTHONPATH": ".circled-wiki/runtime",
        "KNOWLEDGE_MCP_MODE": "operator"
      }
    },
    "graphify": {
      "command": "graphify-mcp",
      "args": ["graphify-out/graph.json"]
    }
  }
}
```

일반 질의 전용 Agent에는 `KNOWLEDGE_MCP_MODE`를 생략해 read-only로 등록한다. 운영 Agent의 단일 로컬 프로세스에만
`operator`를 부여한다. Graphify MCP 도구와 실행법은 [공식 MCP 도구 문서](https://graphify.com/docs/mcp-tools)를 따른다.

## Agent Policy

1. Graphify `query_graph` 등으로 관련 개념과 문서 후보를 찾는다.
2. 후보의 공식 상태와 최신성은 Knowledge MCP `search_knowledge`, `read_bundle`, `prepare_context`로 확인한다.
3. 최종 답변은 Bundle과 Evidence source를 인용한다.
4. Graphify 결과와 공식 Bundle이 충돌하면 Bundle을 자동 수정하지 않고 `needs_review`로 보고한다.

Graphify를 끄려면 `.circled-wiki/config.yaml`의 `graphify.enabled`를 `false`로 유지하고 Graphify MCP 등록을 제거한다.
