# 의존성 고정·취약점 검사 (D072 후속)
상태: done (2026-11-02) | 시작: 2026-11-02 | 근거: SECURITY_POLICY §8 (D072)

목표: `.venv`의 설치 목록이 `requirements.lock.txt`로 커밋되어 있고, `pip-audit`으로 첫 취약점 검사를 해서 결과가 기록되어 있다.
구조:
- `requirements.lock.txt` (새 파일) — `.venv`에서 `pip freeze` 결과. 앱 라이브러리와 개발 도구(pyinstaller·ruff·pip-audit)가 함께 들어간다
- `CLAUDE.md` — 명령 절의 빌드 줄에 "zip 전에 `pip-audit`" 한 마디 추가
- `docs/SECURITY_POLICY.md` §8 — 첫 검사 날짜와 결과 한 줄
전역 제약:
- `pip install`은 실행 전 확인 (D048). 코드(`core/`·`ui/`·`tools/`)는 바꾸지 않는다
- `pip-audit`은 설치 목록(패키지 이름·버전)을 PyPI·OSV 취약점 DB에 조회한다. 그 밖의 정보는 보내지 않는다
- 취약점이 나와도 이 계획에서 라이브러리를 올리지 않는다. OPEN에 새 질문으로 넣고 따로 정한다 (올리면 시험을 다시 해야 함)

## 작업
- [x] 1. `pip-audit` 설치 → lock 파일 생성 — `.venv\Scripts\python -m pip install pip-audit` 뒤 `.venv\Scripts\python -m pip freeze > requirements.lock.txt`. 설치를 먼저 해서 lock에 pip-audit까지 들어가게 한다 (나중에 다시 만들어도 같은 목록)
  - 확인: `.venv\Scripts\pip-audit --version` 출력, lock에 `PyChromecast==14.0.10`·`PySide6==6.12.0`·`pip-audit==` 줄 있음, `git check-ignore requirements.lock.txt` 출력 없음
  - 결과: pip-audit 2.10.1. 설치로 21개 추가, 기존 24개 버전 변경 없음. 무시 대상 아님. 커밋 189da8e (pip-audit 줄은 `pip_audit==2.10.1`로 적힘)
- [x] 2. 첫 검사 — `.venv\Scripts\pip-audit -r requirements.lock.txt`
  - 확인: 명령이 끝나고 "No known vulnerabilities found" 또는 취약점 표가 나옴. 취약점이 있으면 패키지·ID·고친 버전을 OPEN에 새 O번호로 넣음
  - 결과: No known vulnerabilities found
- [x] 3. 문서 — CLAUDE.md 빌드 줄, SECURITY_POLICY §8에 첫 검사 결과(날짜, 결과), PROGRESS "다음 할 일" 1번 정리
  - 확인: 문서에 실제 IP·기기 이름·경로·파일 이름 없음 (D041)
  - 결과: CLAUDE.md 빌드 줄·SECURITY_POLICY §8 첫 검사 줄·PROGRESS 갱신
- [x] 4. 인수 확인
  - 확인: 전체 테스트 `.venv\Scripts\python -m tools.cast_test --selftest --log` 통과 (설치로 기존 라이브러리 버전이 바뀌지 않았는지: 1번 전후 `pip freeze`에서 pip-audit 관련 줄 말고 차이 없음)
  - 결과(2026-11-02): 74개 통과, 약 11초. 전후 freeze는 추가만 있음

## 자가 검토
- PRD 기능 누락: 없음 (보안 정책 §8만 해당)
- 테스트로 옮기지 않은 인수 기준: 없음 (실기기 시험 불필요, TV와 무관)
- 순서 의존: 2는 1 뒤, 3은 2 뒤. 커밋은 1(`chore:`)·3(`docs:`) 두 개, 2는 결과를 3에 적음
- 남은 위험: pip-audit이 setuptools 같은 도구를 올리면 기존 버전이 바뀜 → 4번의 전후 비교로 잡는다
