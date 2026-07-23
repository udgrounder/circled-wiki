# Workspace

개선 작업의 계획·검증 자산을 모으는 작업 영역이다.

- `task/`: 구현·개선·운영 변경을 위한 작업 계획서
- `tests/`: 제품 코드의 unit·integration 테스트

실행 예:

```bash
python3 -m pytest workspace/tests
PYTHONPATH=src python3 -m unittest discover -s workspace/tests -q
```
