# Copilot 지침 — `files` 저장소

목적: 이 문서는 AI 코딩 에이전트가 이 저장소에서 빠르게 생산적으로 작업할 수 있도록, 핵심 아키텍처·실행 흐름·프로젝트 규약·통합 지점을 요약합니다.

**Repository Overview**
- **Entrypoint**: `deploy/main.py` — 주요 실행 흐름(설정 로드 → 작업 분배 → `RepoProcessor`로 복사/검증 → 요약 작성).
- **핵심 모듈**: `modules/git_manager.py`, `modules/file_manager.py`, `modules/repo_processor.py`, `modules/util.py`.
- **데이터/설정**: 주 설정 파일은 `deploy/config.yml` (코드에서 `load_config("config.yml")`로 읽음; 실행 CWD에 유의).
- **작업 목록**: `deploy/worklist.txt` (worklist 모드에서 사용).

**빅픽처 흐름**
- 시작: `deploy/main.py`가 `config.yml`을 읽음.
- worklist 모드(`is_worklist`)일 때: `load_worklist()` → `distribute_worklist_to_repos()`로 각 repo에 매칭.
- 각 repo는 `RepoProcessor.process_repo(repo)`로 처리되며, 처리 결과로 `exist_files`, `missing_files`, `raw_copy_list`, `copy_count_map` 등을 repo dict에 채움.
- 병렬 처리: `ThreadPoolExecutor(max_workers=5)`를 기본으로 사용(동시 실행 시 `FileManager`/로그 동기성에 주의).
- 완료 후 `write_summary()`가 `copy_dir/summary.log`를 생성.

**중요한 컨벤션 & 패턴 (이 프로젝트에 특화된 사항)**
- 경로 정규화: `deploy/main.py:normalize_path()`은 선행 `/`와 `gemswas/` 접두사를 제거 — 입력 경로 비교/매칭 시 항상 이 규칙을 따름.
- repo 구성 항목(예시):
  ```yaml
  - name: gemswas/some-repo
    worklist_prefixes: ["src/lib/", "assets/"]
    copy_list: ["src/lib/util.py"]
    execute: ["copy"]
  ```
  - `execute` 필드에 `all` 또는 `copy`가 포함되어야 요약/출력 대상이 됨.
- `analyze_copy_list()`는 `raw_copy_list`, `copy_count_map`, `unique_copy_list`를 repo dict에 추가.
- 에러/로깅: `process_single_repo()`는 예외를 `FileManager.dual_log()`로 기록 — 실패시 사용자에게 명확한 로그가 남음.

**통합 포인트 & 외부 의존성**
- GitHub 연동: `config.yml` 내 `github.server`, `github.token`, `github.branch` 필요 — `GitManager`가 사용.
- 외부 명령: `ant_cmd` (설정의 `paths.ant_cmd`)가 사용될 수 있으므로 CI/환경에서 `ant` 경로 확인 필요.
- 로컬 패키지: 저장소 내 `library/yaml` 등 자체 패키지가 포함되어 있을 수 있음 — 런타임 import 충돌 주의.

**실행 / 디버깅 요령**
- 간단 실행: 저장소 루트에서 `python deploy/main.py` 또는 `cd deploy && python main.py`.
- 실행 전 확인: `deploy/config.yml`의 경로(`paths.repo_dir`, `paths.copy_dir`, `paths.logs_dir`, `paths.back_dir`)와 `github` 섹션이 정확한지 확인.
- 실행 결과 확인: `copy_dir/summary.log`와 `logs_dir`에 생성된 로그를 확인.
- 로컬 디버그: `is_single: true`로 설정하면 순차 실행 → 디버깅이 쉬움.

**수정 안내 (에이전트에게)**
- 작은 변경을 할 때: 기존 로그/요약 형식을 깨지 않도록 주의 — `write_summary()`에 의존하는 스크립트가 있을 수 있음.
- 새 repo 추가: `deploy/config.yml`의 `repositories`에 위 예시 구조로 항목 추가.
- 병렬화 변경 시: `FileManager`와 로그 동시성, `RepoProcessor`의 상태 변경 지점을 먼저 검토.
- 외부 요청(토큰/비밀): 토큰 값은 코드에 직접 하드코딩하지 말고 `config.yml` 또는 CI 시크릿으로 관리하라.

**질문 포인트 (사용자에게 확인 필요)**
- `deploy/config.yml`의 위치/이름을 변경해도 되는가? (현재 `main.py`는 CWD에서 `config.yml`을 찾음)
- 로깅 형식의 보존/개선 여부: 요약 포맷(`summary.log`)의 호환성을 지킬 필요가 있는지?

참고: 구체적인 구현 세부(예: `FileManager` API, `RepoProcessor.process_repo` 내부 동작)는 `modules/`의 각 파일을 열어 확인해야 합니다. 변경 전 해당 파일들을 참조하세요.

---
피드백 요청: 이 내용에서 더 추가하거나 명확히 할 항목이 있나요? 특정 파일의 구현을 요약하길 원하면 알려주세요.
