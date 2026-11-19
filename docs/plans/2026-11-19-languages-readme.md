# 화면 언어 6개·UI 정리·README 개편 (F10, F9, D079~D096)
Status: active | 시작: 2026-11-19 | 근거: PRD F10, F9, §2.1 README (D079~D089, UI 정리 D090~D096 2026-11-19 추가)

목표: 화면·알림·대화상자가 English·한국어·简体中文·日本語·Español·Русский로 보이고, 처음에는 Windows 표시 언어를 따르며, 옵션 → 언어로 바꾸면 다시 켜지 않아도 바로 바뀐다. GitHub README가 영어 기본 + 5개 번역이고, 맨 위에 자동 생성한 작동 장면 GIF가 있다. 창을 세로로 늘리면 미디어 카드 윗칸만 커지고 상태가 바뀌어도 카드 높이가 같으며, 음성·자막 목록이 사람이 읽는 말로 나온다(UI 정리, D090). 1.2.0 zip에 README 6개가 들어간다.
구조:
- `core/i18n.py` (새 파일) — `tr(key, **kw)`, `set_language(code)`, `language()`, `pick_language(ui_langs) -> code`, `LANGUAGES`(코드 → 자기 이름). Qt 비의존
- `core/lang/en.py`·`zh_CN.py`·`ja.py`·`es.py`·`ru.py` (새 파일) — 각각 `STRINGS: dict[str, str]` (키 = 코드의 한국어 문장)
- `core/config.py > AppConfig` — `language: str = "system"`
- `main.py > main` — QApplication 직후·ffmpeg 확인 대화상자 전에 언어를 정함 (`QLocale.system().uiLanguages()` → `pick_language`)
- `ui/main_window.py` — 고정 글자를 `_retranslate()` 하나로 모음, `_set_language()`, 메뉴 연결
- `ui/menus.py > build_menus` — 메뉴 글자는 `retranslate_menus()`가 넣음, 옵션 → 언어 하위 메뉴
- `ui/dialogs.py` — 단축키·지원 형식·정보 글을 표시할 때 `tr()`
- `core/*.py` — 화면에 가는 문장(콜백 메시지·`raise`된 예외 문장·`label`·`display`·`summary`)만 `tr()`
- `tools/cast_test.py` — F10 자가검사, `--shots` (스크린샷·GIF 생성)
- `README.md`(영어)·`README.ko.md`·`README.zh-CN.md`·`README.ja.md`·`README.es.md`·`README.ru.md`, `docs/images/` — `README.en.md`는 지움
- `CastPlayer.spec` — zip에 `README*.md` 6개 (D087), `ui/dialogs.py > APP_VERSION` 1.2.0
- `ui/main_window.py > _build_ui` — 미디어 카드 윗칸을 `QStackedWidget`(끌어다 놓기 / 파일 정보·불러오기 줄)로, 윗칸만 세로로 늘어남, 고정 너비 버튼을 최소 너비로 (UI 정리)
- `ui/tracks.py` (새 파일) — 음성·자막 목록 글자와 풍선 도움말 (언어 이름 15개·코덱 이름 표, D096)
전역 제약:
- 로그 문구(`log.*`)와 콘솔 시험 도구 출력은 `tr()`로 감싸지 않는다 (D081, D086)
- `tr()`는 표시하는 순간에 부른다. 모듈 수준 상수·기본 인수 안에서 부르지 않는다 (즉시 적용이 깨짐, D085)
- 기본 언어는 한국어(`core.i18n`의 시작값 `ko`)이고 자가검사는 한국어로 고정해 돌린다. 기존 GUI 시험의 한국어 문장 확인이 그대로 지금 동작을 고정하는 시험 역할을 한다
- 문장을 바꾸면 6개 사전을 같은 커밋에서 바꾼다. 자리표시는 `{이름}`만 쓴다 (`str.format`)
- core에서 Qt를 import하지 않는다 (D003). 문서·README·이미지에 실제 IP·기기 이름·사용자 경로·영상 파일 이름을 쓰지 않는다 (D041)
시험 접점: `tools/cast_test.py --selftest`의 GUI 시험(`_gui()` = 가짜 TV를 붙인 실제 `MainWindow`)과 `core.i18n`의 공개 함수

## 작업
- [x] 1. 번역 틀 — `core/i18n.py` (`tr`·`set_language`·`language`·`pick_language`·`LANGUAGES`), `core/config.py > AppConfig.language`, 빈 `core/lang/*.py` 5개
  - 먼저 실패하는 시험: `pick_language(["ja-JP"]) == "ja"`, `["de-DE"]` → `"en"`, `["zh-TW"]`·`["zh-Hant-HK"]` → `"en"`, `["zh-Hans-CN"]`·`["zh-CN"]` → `"zh_CN"`, `["ko-KR"]` → `"ko"`, 빈 목록 → `"en"`. `tr`은 사전에 없으면 키 그대로, `{n}` 채움. config에 `language`가 없던 파일을 읽으면 `"system"`
  - 확인: `.venv\Scripts\python -m tools.cast_test --selftest --log` 전부 통과
  - 결과: 2026-11-19 통과 — 새 시험 4개 먼저 실패(ImportError) 확인 뒤 구현, 자가검사 88/88, 13.6초. ruff·pyright 0건
- [x] 2. 키 검사기 (F10-4 틀) — `tools/cast_test.py`: `core/`·`ui/`·`main.py`를 ast로 읽어 (가) `tr("문자열")`의 키 목록, (나) `tr()`·`log.*` 밖에 있는 한글 문자열 상수 목록을 만든다. (가)의 키가 각 사전에 있는지, 자리표시가 같은지 확인하고, 사전에만 있는 키(안 쓰는 키)를 실패로 본다. (나)는 이 단계에서 개수만 출력 (after: 1)
  - 확인: selftest 통과, (나)의 개수가 출력됨 (감싸기 전 기준값)
  - 결과: 2026-11-19 통과 — 자가검사 96/96, 14.1초. 기준값: core 91개, ui·main.py 121개. 검사기 자체 시험(임시 폴더의 표본 코드) 포함
- [x] 3. 화면 글자 감싸기 (구조 변경, 동작 같음) — `ui/*.py`·`main.py`의 화면 문장을 `tr()`로. 고정 글자(버튼·툴팁·라벨·창 제목)는 `MainWindow._retranslate()`로 옮기고 `__init__`에서 한 번 부름. 메뉴 글자는 `menus.retranslate_menus(acts)`로. `dialogs.py`의 단축키 표는 키만 상수로 두고 설명은 표시할 때 `tr()` (after: 2)
  - 확인: selftest 통과 (기존 한국어 문장 시험이 바뀌지 않고 통과), (나)에서 `ui/`·`main.py` 0개
  - 결과: 2026-11-19 통과 — 자가검사 97/97, 13.5초, 기존 GUI 시험 기대값 변경 없음. 키 103개. ui·main.py 감싸지 않은 한글 0개를 실패 조건으로 고정
  - 계획과 다른 점: 상수 키는 `core.i18n.N_()`로 표시하고 보일 때 `tr(변수)` (연결 상태·단축키 표·메뉴). 검사기는 변수 키를 허용하고 f-문자열·이어 붙인 키만 막음. 아직 빈 사전은 빠진 키를 세지 않음(작업 5·7에서 엄격). `ui/theme.py`(QSS 주석)·assert 문구·명령줄 help는 검사 대상에서 뺌
- [x] 4. core 화면 문장 감싸기 (구조 변경, 동작 같음) — `core/`에서 콜백(`on_error`·`on_connection_failed` 등)으로 가는 문장, 화면에 보이는 예외 문장, `AudioStream.label`·`SubtitleStream.label`·`SubtitleTrack.display`·`Plan.summary`와 `ui/main_window.py > _plan_text`가 쓰는 문장만 `tr()`. 로그만 가는 문장은 그대로 (after: 2)
  - 확인: selftest 통과, (나)에서 `core/`에 남은 한글 상수는 모두 로그 전용임을 목록으로 보임
  - (나)가 0개(로그 제외)가 되면 검사기를 "개수 출력"에서 "0개가 아니면 실패"로 바꾼다
  - 결과: 2026-11-19 통과 — 자가검사 96/96, 14.0·14.3초, 기존 시험 기대값 변경 없음. 키 161개, 감싸지 않은 한글 0개를 실패 조건으로 고정
  - 계획과 다른 점: 로그로만 가는 문장(재연결 판정 이유, 내부 자막 오류 등 17줄)은 줄 끝 `# 로그 전용` 표시로 검사에서 뺌. 즉시 적용을 위해 `Plan.reasons`를 (키, 값) 튜플로, 내장 자막 `label`은 "#번호 …"로 두고 `SubtitleTrack.title`이 보여 줄 때 "내장"을 붙임(TV 자막 이름도 같음), 불러오기 단계 이름은 N_ 키로 보내 화면이 번역
- [x] 5. 영어 사전 — `core/lang/en.py`에 3·4에서 나온 모든 키 (after: 3, 4)
  - 확인: selftest의 키 검사기가 en에 대해 통과
  - 결과: 2026-11-19 통과 — 사전 en 161/161, 빠짐·남음·자리표시 불일치 0, 자가검사 96/96, 13.6초
- [x] 6. 언어 메뉴·감지·즉시 적용 (F10-1·F10-2·F10-3) — `main.py`에서 `cfg.language`가 `system`이면 `QLocale.system().uiLanguages()` → `pick_language`, 아니면 그 값으로 `set_language` (ffmpeg 확인 대화상자보다 먼저). `ui/menus.py`: 옵션 → 언어(맨 위 "시스템 설정 따르기", 6개는 `LANGUAGES`의 자기 이름, 테마처럼 하나만 체크). `MainWindow._set_language(code)`: 저장 → `set_language` → `_retranslate()`·`retranslate_menus()`·`_update_ui`·`_fill_tracks`·`_show_plan`·`_show_sync`·연결 상태 글 다시 그리기 (after: 5)
  - 먼저 실패하는 시험: F10-3 — `_gui(loaded=True)` 한국어 → 메뉴의 English 실행 → 모든 위젯의 `text()`·`toolTip()`·`windowTitle()`·메뉴 글자·콤보 항목에 한글 없음(기기 이름·파일 이름 같은 데이터 제외), `cfg.language == "en"`, 새로 만든 창(같은 cfg)도 English. F10-1·F10-2 — `main`의 언어 결정 함수에 `["ja-JP"]`·`["de-DE"]`·`["zh-TW"]`를 넣어 `ja`·`en`·`en`, 그 상태로 만든 창의 메뉴 글자가 사전 값과 같음
  - 확인: selftest 통과
  - 결과: 2026-11-19 통과 — 새 시험(F10-1·2, F10-3) 먼저 실패 확인 뒤 구현. 자가검사 98/98, 14.2초 두 번. F10-3: 영어로 바꾸기 전 한글 글자 48개 → 뒤 0개, 송출 방식 풍선 도움말도 영어, 다시 만든 창도 English
  - 계획과 다른 점: 언어 결정 함수는 main.py가 아니라 `core.i18n.startup_language`(main·창이 같이 씀). 시험의 기대값 1개(연결 버튼)는 시험 환경에서 기기 목록이 비어 "연결"이 맞아 고침. 언어 메뉴의 각 언어 이름("한국어" 등)은 한글 검사에서 뺌. 새 키 "언어" 1개 → 162개
- [x] 7. 4개 언어 사전 (F10-4) — `core/lang/zh_CN.py`·`ja.py`·`es.py`·`ru.py`를 en과 같은 키로 채움 (AI 번역) (after: 5)
  - 확인: selftest의 키 검사기가 5개 사전 모두 통과(누락·남는 키·자리표시 불일치 0). F10-3 시험을 5개 언어 각각으로 돌려 한글 0
  - 결과: 2026-11-19 통과 — 5개 사전 모두 162/162, 누락·남음·자리표시 불일치 0. F10-3 영어 + 4개 언어 화면 한글 0. 자가검사 99/99, 14.0초. 4개 사전은 영어판과 같은 순서의 표 하나에서 만들고 줄마다 영어 앞부분이 맞는지 확인함
- [ ] 8. 미디어 카드 배치 (F9-9·F9-10) — `ui/main_window.py > _build_ui`: 윗칸을 `QStackedWidget`(0: 끌어다 놓기 영역, 1: 파일 이름·송출 방식 + 불러오기 진행 줄)로 묶어 세 상태 높이를 같게 하고, 미디어 카드에서 윗칸만 세로로 늘어나게(`root.addStretch` 제거). 최소 높이는 지금 창, 너비는 레이아웃 최소 너비(고정 너비 버튼 `setFixedSize` → 높이만 고정·너비는 최소값, 글자가 길면 넓어짐). 창이 클 때 파일 정보는 윗칸 가운데, 파일 이름 조금 크게 (after: 7)
  - 먼저 실패하는 시험: F9-9 — `_gui()` 연결·파일 없음 → 불러오는 중(`_on_progress`) → 재생 중에서 미디어 카드 `height()`가 같음. F9-10 — 최소 크기에서 창을 세로로 200px 늘리면 윗칸 높이 +200, 기기·트랙 카드·조작줄 높이 그대로
  - 확인: selftest 통과 (F9-3·F9-4 등 기존 시험 그대로)
- [ ] 9. 트랙 목록 표기 (F9-11) — 새 `ui/tracks.py`의 `audio_text`·`subtitle_text`·`track_tip`, `ui/main_window.py > _fill_tracks`가 씀(항목 풍선 도움말 = 트랙 제목). 언어 이름 15개·"언어 정보 없음"·형식 문장은 N_ 키로 6개 사전에 추가. 코덱 이름·채널 표는 번역하지 않는 상수 (after: 7)
  - 먼저 실패하는 시험: F9-11 — D096 예시(음성 eac3 6ch kor 기본 제목 있음 / aac 2ch eng, 자막 내장 subrip ko 2352줄 / 외부 srt en / 내장 PGS)를 넣으면 목록이 "한국어 · Dolby Digital Plus 5.1 · 기본", "English · AAC stereo", "한국어 · 내장 SRT · 2352줄", "English · {파일 이름} · 1342줄", "한국어 · 내장 PGS · 지원 안 함"(회색)이고 첫 음성의 풍선 도움말이 트랙 제목
  - 확인: selftest 통과, 키 검사기 6개 사전 모두 통과
- [ ] 10. 앞뒤 10초·자막 줄 이름 — `ui/main_window.py`의 `SEEK_FWD` 30 → 10, 줄 이름 "크기"·"싱크" → "자막 크기"·"자막 싱크"(6개 사전 키 바꿈) (after: 8)
  - 먼저 고치는 시험: F9-5 기대값을 +10초로 (PRD 변경 D093에 따른 기대값 변경)
  - 확인: selftest 통과
- [ ] 11. 스크린샷·작동 장면 GIF — `tools/cast_test.py --shots` (예시 기기 이름·파일 이름, English). 먼저 화면 없는 Qt(offscreen)가 아이콘 글꼴(Segoe Fluent Icons)과 본문 글꼴을 실제 창과 같게 그리는지 캡처를 보고 판단. 다르면 Windows 기본 플랫폼으로 창을 화면 밖 좌표에 두고 `grab()`. 장면: 미연결 → 연결됨·파일 없음 → 불러오기 진행 막대 → 재생 중 → 탐색 → 음성·자막 바꾸기. ffmpeg로 `docs/images/demo.gif`(팔레트 생성, 약 2MB 이하), 정지 화면 `docs/images/main-dark.png`·`main-light.png` (after: 10)
  - 확인: 명령이 끝나고 세 파일이 생김, GIF 크기 2MB 이하 출력. 사람: 세 이미지를 보고 글꼴·아이콘이 실제 창과 같고 개인정보가 없음
  - 진행: 2026-11-19 `--shots` 도구 커밋(1e39f18). offscreen은 글꼴이 없어 Windows 플랫폼에서 창을 띄우지 않고 찍음. 영어 "Subtitles" 라벨 잘림(40px 고정) 수정, 송출 방식 줄 문구(video unchanged 등)·구분자 `|`로 바꿈(사용자 선택)
  - 보류: 사용자가 이미지 확인 중 UI 문제(상태에 따라 카드 높이 변함, 창 크기를 따라가지 않음 등)를 지적 → UI 정리를 PRD F9 변경으로 먼저 하고 이미지는 그 뒤 다시 만듦 (D090). 2026-11-19 계획 고침: UI 정리를 작업 8~10으로 넣고 이 작업은 11로 옮김
- [ ] 12. README 개편 — `README.md`(영어 기본)를 readme 표준 §2~§4로 다시 쓰고 `README.ko.md`(지금 한국어판 기반)·`zh-CN`·`ja`·`es`·`ru` 작성, `README.en.md` 지움. 맨 위 언어 줄 → 번역 안내 한 줄(번역판) → 제목 → 배지(버전·라이선스·Python·Windows 11) → 한 줄 소개 → `demo.gif`. 본문에 다크·라이트 정지 화면, 화면 언어 안내, 설치·사용법·한계·파일 위치·이슈·라이선스(MIT) (after: 11)
  - 확인 (readme 표준 §6): 6개 파일 존재, 각 번역의 `##` 제목 수·배지 수가 영어판과 같음, 상대 링크가 가리키는 파일이 모두 있음, 배지 이미지가 열림(`logo=` 아이콘 보임), 쪽 안 링크가 각 번역의 제목을 씀, 설치·사용 명령은 실제로 실행(위험 명령은 있는지만), 공개 전 점검 패턴(PRD §6) `git grep` 0건
- [ ] 13. 배포 준비 — `CastPlayer.spec`가 `README*.md` 6개를 복사(D087), `APP_VERSION = "1.2.0"`, `THIRD_PARTY_NOTICES.md` 버전 문구, CLAUDE.md 규칙에 "화면 문장은 `tr()`로 감싸고 6개 사전을 같은 커밋에서 바꾼다" 한 줄 (after: 12)
  - 확인: selftest 통과, 빌드(실행 전 확인) 뒤 `dist\CastPlayer`에 README 6개와 LICENSE·THIRD_PARTY_NOTICES.md가 있고 시험 흔적(`bin`·`logs`·`cache`·`config.json`) 없음, `pip-audit -r requirements.lock.txt` 결과
- [ ] 14. 인수 — 이 계획의 F10·F9 인수 기준 전부
  - 확인: 전체 테스트 `.venv\Scripts\python -m tools.cast_test --selftest --log` 통과 (F10-1~4, F9-1~7·F9-9~11 포함)
  - 실기기: F10-5 — exe에서 옵션 → 언어로 简体中文·日本語·Español·Русский를 차례로 고르고, 다시 켜지 않아도 바뀌며 글자 깨짐(□)과 버튼·메뉴 글자 잘림이 없음. "시스템 설정 따르기"로 돌아오면 Windows 언어. 창을 최소 너비로 줄여도 잘림 없음. 한국어로 TV 재생 한 번 (기존 동작 그대로). F9-8 — 새 배치의 어둡게·밝게 화면 정렬·대비
  - 명세 검토: 대화 맥락 없는 서브에이전트에 이 계획, PRD F10·F9·§2.1, `git diff {계획 시작 커밋}..`을 주고 빠진 것·요청 없이 더한 것·잘못 구현한 것을 받음

## 자기 검토
- 빠진 PRD 기능: 없음 (F10 전체, F9 UI 정리 D091~D096, §2.1 README·스크린샷·GIF·zip 구성)
- 시험으로 바꾸지 않은 인수 기준: F10-5·F9-8 → 글자 깨짐·잘림·정렬은 눈으로만 판단 가능, 화면 없는 Qt에는 글꼴이 없음 (§6)
- 순서: 2는 1 뒤, 3·4는 2 뒤(서로 독립), 5는 3·4 뒤, 6·7은 5 뒤, 8·9는 7 뒤(서로 독립), 10은 8 뒤(같은 파일), 11은 10 뒤(최종 화면을 찍음), 12는 11 뒤, 13은 12 뒤
- 구조 변경(3·4)과 동작 변경(6)을 나눔. 3·4 동안 화면은 한국어 그대로
