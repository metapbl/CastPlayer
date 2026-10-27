<!-- metarche -->
# CastPlayer

Windows PC의 로컬 동영상을 Chromecast with Google TV로 보내는 PySide6 GUI. PC는 제어만, 재생은 TV. 상세는 docs/PRD.md

## 구조
- `main.py` — GUI 진입점 (로그 설정, ffmpeg 확인, 객체 조립)
- `core/` — 송출 로직. Qt에 의존하지 않는다 (cast_manager, player, hls, planner, subtitles 등)
- `ui/` — PySide6 화면. `bridge.py`가 core 콜백을 Qt Signal로 바꾼다
- `tools/cast_test.py` — 콘솔 시험·자가검사·끊김 시험 (테스트 코드는 이 파일 하나)
- `bin/`(ffmpeg), `cache/`, `logs/`, `config.json` — git 제외

## 명령
- 실행: `.venv\Scripts\python main.py -v` (TV 송출 → 실행 전 확인)
- 전체 테스트 (작업마다, TV 불필요, 약 6초): `.venv\Scripts\python -m tools.cast_test --selftest --log` (D064)
- 편집 때 자동 검사: `.claude/hooks/check.ps1`이 실행 (`.venv\Scripts\ruff.exe check`, 설정 `ruff.toml`, D063)
- 콘솔 시험: `.venv\Scripts\python -m tools.cast_test "<파일>" -v --log` (TV 송출 → 실행 전 확인)
- 빌드 (실행 전 확인): `.venv\Scripts\pyinstaller.exe --noconfirm CastPlayer.spec` → `Compress-Archive dist\CastPlayer dist\CastPlayer-<버전>-win64.zip`. zip 전에 `dist\CastPlayer`의 시험 흔적(`bin`·`logs`·`cache`·`config.json`)이 없어야 한다 (D014·D043·D067)

## 이 프로젝트의 규칙
- core에서 Qt를 import하지 않는다 (ruff TID251이 막음). 상태는 `CastCallbacks`로 알린다 (D003, D063)
- pychromecast 블로킹 명령은 `cast-worker` 큐로만 보낸다 (D004)
- 연결이 끊겨도 HLS 세션·ffmpeg·자막 경로를 정리하지 않는다. 정리는 정지·새 파일·사용자 연결 해제·재연결 포기 때만 (D029, R§4 T9)
- 다시 연결된 뒤 첫 요청은 RECEIVER_STATUS를 받은 뒤에 보낸다 (D029, R§4 T6)
- ffmpeg는 세션당 1개. 먼저 죽이지 말고 교체한다 (D018)
- 정지할 때는 기본 수신 앱(CC1AD845)만 종료한다 (D005)
- 테스트 코드는 `tools/cast_test.py`에만 추가한다. 로그 파일 확장자는 `.txt` (D030, D031)
- 실기기 시험은 사용자가 한다. 기대 결과를 번호 항목으로 주고 항목마다 "예/아니요와 본 것"을 받는다. 로그는 `logs/`의 최신 `.txt`를 읽어 함께 판정한다 (D062)
- TV 송출 시험, `pip install`, `git push`, `cache/`·`logs/` 삭제는 실행 전에 묻는다 (D048)
- 커밋: 작업 하나당 1개, `feat:`/`fix:`/`docs:`/`chore:`, main 직접 (D049)
- 문서·커밋·코드 주석에 실제 IP·기기 이름·사용자 경로·영상 파일 이름을 쓰지 않는다. 예시값을 쓴다 (D041)

## 문서 지도
- `docs/PRD.md` — 무엇을 왜 (승인본. 바꾸려면 /metarche discover)
- `docs/PROGRESS.md` — 상태·다음 할 일 (머리는 세션 시작 때 자동 주입)
- `docs/REFERENCE.md` — 구조·수신기 제약·함정 대장. 필요한 절만 검색해 읽는다
- `docs/plans/` — 작업 계획 (체크박스)
- `docs/discovery/` — DECISIONS는 결정 확인용, QA_LOG는 검색만

## 작업 기록
- 작업을 끝내면 계획 파일의 체크박스를 갱신한다. 세션을 마칠 때 docs/PROGRESS.md 머리 부분을 갱신하고 /metarche wrap을 제안한다.
- 관련 없는 작업으로 넘어갈 때는 /clear를 제안한다.
- 새 결정은 `docs/discovery/DECISIONS.md`에, 반복된 실수의 원인은 REFERENCE 함정 대장에 적는다.
- PRD 변경 중(`상태: changing`)에는 docs/ 밖을 수정하지 않는다 (훅이 막는다).

## 압축 시 보존
- 압축할 때는 진행 중인 계획 파일 경로, 수정한 파일 목록, 확인 명령, 마지막 실기기 시험 로그 파일 이름을 보존한다.
