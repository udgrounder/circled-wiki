# Suggested commands
- Full tests: `python3 -m pytest`
- Targeted tests: `python3 -m pytest tests/unit/test_<area>.py tests/integration/test_<area>.py`
- Runtime validator from source: `PYTHONPATH=src python3 -m circled_wiki.cli validate`
- CLI from source: `PYTHONPATH=src python3 -m circled_wiki.cli <command>`
- Inspect changes: `git status --short`; `git diff --stat`; `git diff -- <paths>`
- On Darwin, use a writable bytecode cache if needed: `PYTHONPYCACHEPREFIX=/tmp/<task-cache> python3 -m compileall -q src tests`.