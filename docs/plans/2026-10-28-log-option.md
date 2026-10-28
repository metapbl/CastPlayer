# 로그 기록 옵션과 새 인수 기준 (D069, D070)
상태: done (2026-10-29) | 시작: 2026-10-28 | 근거: PRD F2, F5, F7, F8, §5, §6 (D069, D070)

목표: GUI 로그가 기본 꺼짐이 되고, 옵션 메뉴 "로그 기록"으로 켜며, 실행마다 새로 쓰고, DEBUG는 터미널 `-v`로만 켠다. 로그 확장자는 GUI·tools 모두 `.log`. PRD에 새로 넣은 [자동] 인수 기준을 자가검사로 옮긴다.
구조:
- `main.py` — `setup_logging`을 로그 파일 열기·닫기 함수로 바꿈 (켜기/끄기, 실행 첫 열기 때 지난 `castplayer*.log` 삭제, 1MB×4 순환, 실패 시 오류 문구 반환). `-v`는 옵션과 무관하게 파일 기록 + DEBUG
- `core/config.py` — `debug_log` → `log_file: bool = False` (옛 `debug_log` 키는 읽을 때 무시됨)
- `ui/menus.py` — "디버그 로그" → "로그 기록"
- `ui/main_window.py` — `set_debug`/`debug_on` → 로그 켜기·끄기 콜백과 시작 때 오류 문구. 실패하면 상태줄 오류 알림
- `tools/cast_test.py` — `LOG_EXT = ".log"`, `--count-buffering` 기본 입력 `castplayer*.log`, 도움말·주석. 자가검사 추가
- `.gitignore`, `README.md`·`README.en.md`, `CLAUDE.md`, `docs/REFERENCE.md` — `.txt` → `.log`, 로그 안내
전역 제약:
- 작업마다 `--selftest` 전부 통과해야 커밋 (D064). 편집 때 ruff·pyright 통과 (D063, D068)
- core에서 Qt import 금지 (D003). 로그 파일 처리는 `main.py`에 둔다 (GUI 진입점 전용)
- 테스트 코드는 `tools/cast_test.py`에만 (D031)
- 지금 `logs/`에 있는 옛 `castplayer*.txt`·`cast_test_*.txt`는 지우지 않는다 (삭제는 사용자 확인 대상, D048). 새 코드는 `.log`만 지운다
- 한 실행 안에서 끄고 다시 켜면 같은 파일에 이어 씀 (지우는 것은 그 실행의 첫 열기 때만) [AI]

## 작업
- [x] 1. 자가검사: D069 [자동] 인수 기준 — F2-6(3840×2160 60fps XviD → TRANSCODE, fps 30), F5-6(`text_style` 투명 배경·흰 글자·검은 테두리, 배율 0.5~2.0으로 맞춤). 지금 코드 동작을 고정하는 시험이라 처음부터 통과해야 함 — `tools/cast_test.py > _plan_style_cases`(새)
  - 확인: `.venv\Scripts\python -m tools.cast_test --selftest --log` → 새 항목 포함 전부 통과
- [x] 2. tools 로그 확장자 `.log` — `LOG_EXT`, `open_log`·`count_buffering` 기본 경로(`castplayer.{n}.log`, `castplayer.log`), 도움말·docstring, `.gitignore`의 `cast_test_*.txt`·`drop_*.txt` → `.log`. 버퍼링 판정 기본 경로 자가검사 1개 추가 (임시 폴더의 `castplayer.1.log`·`castplayer.log`를 오래된 순으로 읽음)
  - 확인: `--selftest --log` 통과, 출력의 "로그 파일:"이 `logs\cast_test_날짜_시각.log`
- [x] 3. GUI 로그 옵션 — 먼저 실패하는 자가검사 F7-5~F7-8(임시 폴더 대상: 꺼짐이면 파일 없음 / 켜면 지난 내용 없이 새로 / `-v`면 꺼짐이어도 DEBUG 줄 / 쓸 수 없는 경로면 "로그 파일을 만들 수 없습니다" 문구 반환)를 쓰고, `main.py`·`core/config.py`·`ui/menus.py`·`ui/main_window.py`를 고침. 실행 중 켜기·끄기는 핸들러 추가·제거
  - 확인: 고치기 전 새 항목 실패 → 고친 뒤 `--selftest --log` 전부 통과, `pyright` 0개
- [x] 4. 문서 — README 한/영 로그 줄("옵션 → 로그 기록을 켜면 `logs\castplayer.log`, 실행할 때마다 새로 씀, 터미널 `-v`는 DEBUG"), `CLAUDE.md` 규칙(`.txt` → `.log`, 실기기 시험은 로그 기록을 켜고 끝나면 다시 켜기 전에 알림), `docs/REFERENCE.md` 로그 줄, `main.py` 머리 주석
  - 확인: `git grep -n "castplayer\.txt\|cast_test_.*\.txt\|확장자는 \`.txt\`"` → docs/discovery·docs/plans 옛 기록 말고 0건
- [x] 5. 인수 확인 (실기기 F3-7은 `2026-10-29-gui-autotest.md` 작업 5로 옮김) — 전체 테스트와 이번 계획의 실기기 기준
  - 확인: 전체 테스트 `.venv\Scripts\python -m tools.cast_test --selftest --log` 통과
  - 실기기 (사용자, `main.py` 실행 전 확인):
    1. F3-7: REMUX 파일 재생 직후 TV 리모컨으로 끝부분 근처까지 탐색 → 그 위치에서 재생
  - 옛 실기기 1·2·3·5번(로그 꺼짐·메뉴, F7-9, F7-8 상태줄, 단축키·탐색 바·상태 갱신·회색 자막)은 D071로 자동 시험 계획에 옮김

## 자가 검토
- PRD 기능 누락: 없음 — D069의 나머지 예외 동작은 기존 코드 그대로라 코드 작업 없음
- 테스트로 옮기지 않은 인수 기준: F7-8의 "상태줄에 표시" 부분 → 자가검사는 오류 문구 반환까지, 표시는 실기기 3번 (MainWindow를 화면 없이 띄우는 시험 틀이 없음. 연결은 `_msg` 한 줄) / F7-9·F3-7 → PRD가 [실기기]로 정함
- 순서 의존: 3은 2 뒤 (같은 `.log` 이름 규칙), 4는 3 뒤, 5는 마지막
