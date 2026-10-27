# 버퍼링 판정 · 공개 준비
상태: done (2026-10-27) | 시작: 2026-10-23 | 근거: PRD §1 성공 기준, §2.1 버퍼링·GitHub 공개, §2.6 제약 (D034, D039~D044, D050, D054, D060)

목표: 영화 한 편을 GUI로 보고 버퍼링 횟수를 로그로 세어 성공 기준(2회 이하)을 판정한다. 그동안 README·LICENSE·의존성 고지·exe 빌드를 마쳐, 공개 직전 단계(히스토리 재시작·업로드만 남음)까지 간다.
구조:
- `core/player.py` — 탐색 INFO 로그 (판정에서 조작 뒤 10초를 빼기 위해)
- `tools/cast_test.py` — `--count-buffering` 판정 명령, 자가검사 항목 (테스트 코드는 이 파일에만, D030, D031)
- 루트 `README.md`(한국어), `README.en.md`(영어), `LICENSE`, `THIRD_PARTY_NOTICES.md`, `CastPlayer.spec`
전역 제약:
- 작업마다 전체 테스트 `.venv\Scripts\python -m tools.cast_test --selftest --log` 전부 통과 뒤 커밋 (현재 34/34). 앞 작업 테스트가 깨지면 다음 작업으로 가지 않는다 (D064)
- 테스트는 두 겹: 바깥은 PRD 인수 기준(이 계획은 F7·F8·F3-6, §1 성공 기준), 안쪽은 작업별 자가검사 항목 (D061)
- 실기기 확인은 기대 결과를 번호 항목으로 주고 "예/아니요와 본 것"으로 받는다 (D062)
- 문서·커밋에 실제 IP·기기 이름·사용자 경로·영상 파일 이름을 쓰지 않는다. 예시값을 쓴다 (D041)
- `pip install`, TV 송출 시험, `git push`는 실행 전에 묻는다 (D048). 공개 직전 git 히스토리 재시작(D041)과 GitHub 업로드는 이 계획에 넣지 않는다
- ffmpeg·ffprobe는 배포물에 넣지 않는다 (D042)

## 작업
### B. 버퍼링 판정
- [x] 1. 탐색할 때 INFO 한 줄 `탐색: N초` — `core/player.py > seek` (D050의 "탐색 뒤 10초 제외"용. 불러오기·음성·싱크 변경은 이미 INFO로 남음)
  - 확인: 자가검사에 "탐색 로그" 항목을 먼저 추가해 실패 확인 → 통과
- [x] 2. 판정 명령 `python -m tools.cast_test --count-buffering [로그 파일…]`: 인자가 없으면 `logs/castplayer.3~1.txt`, `castplayer.txt`를 시간 순서로 읽는다. `재생 상태: PLAYING → BUFFERING`을 세되 `재생:`·`탐색:`·`음성 변경:`·`자막 싱크 반영:` 줄 뒤 10초 안의 것은 뺀다. 출력: 센 횟수, 뺀 횟수, 각 시각과 이유, 시청 구간 길이 — `tools/cast_test.py` (D050)
  - 확인: 자가검사에 예시 로그 줄로 "조작 뒤 10초 안 제외 / 밖은 셈" 항목을 먼저 추가해 실패 확인 → 통과. 오늘 GUI 시험 로그에 실행해 결과가 손으로 센 것과 같은지 확인
- [x] 3. 장시간 시청 (사용자): `.venv\Scripts\python main.py` (`-v` 없이. DEBUG는 1MB×3 로그가 금방 넘침)로 영화 한 편(약 2시간)을 처음부터 끝까지. 시청 중 끊김 시험은 하지 않는다
  - 실기기: 시청 뒤 "끝" → 작업 2 명령으로 판정
  - 결과: 2026-10-24 통과 — 로그 00:49~02:55, `--count-buffering` 125.5분 버퍼링 0회(뺀 것 0회), PLAYING 7,486.7초 연속, "← 느림"·재요청·끊김 0줄. 사용자: ① 2시간 5분을 끝 장면까지 봄 ② 로딩 없었음 ③ 소리·자막 정상 ④ 마지막 장면에서 프로그램 정지 버튼
- [x] 4. 판정 기록: 2회 이하면 PROGRESS·DECISIONS에 통과 기록, 비트레이트 상한(O101)은 하지 않는 쪽으로 PRD §2.2 변경 제안(`/metarche discover`). 넘으면 "← 느림"·재요청 로그로 원인을 보이고 O101 설계안·질문 → 별도 계획, 작업 7은 그 뒤로 미룸 (D034)
  - 확인: 작업 2 명령 출력, PROGRESS 기록
  - 결과: 2026-10-24 버퍼링 0회로 통과 → 비트레이트 상한 안 함, PRD §2.2 → §2.3 변경 승인 (D065, Q049)

### C. 공개 준비 (작업 3 시청 중 진행 가능, 작업 7은 작업 4 뒤)
- [x] 5. `LICENSE` — MIT, `Copyright (c) 2026 META PUBLIC` (D039, D040)
  - 확인: MIT 원문과 대조, 저작권 줄
- [x] 6. `README.md`(한국어)·`README.en.md`(영어): 소개, 요구 사항(Windows 11 공식·Windows 10 미시험, 같은 서브넷의 Chromecast with Google TV), 설치(Releases zip / 소스: venv + `pip install -r requirements.txt`), ffmpeg 설치 `winget install Gyan.FFmpeg`와 `bin/` → PATH 순서, 사용법·단축키, 한계(이미지 자막 미지원, 기본 미디어 수신기만), 이슈·PR 응답 보장 없음, 라이선스 (D040, D042, D044)
  - 확인: 두 파일의 절 구성이 같음, 명령·단축키가 코드(`ui/dialogs.py` 단축키 목록)와 같음, 예시값만 사용(`git grep` 사설 IP·경로 0건)
- [x] 7. PyInstaller onedir·`--windowed` 빌드: `CastPlayer.spec` 작성, `pip install pyinstaller`(실행 전 확인), `dist/CastPlayer/` 생성 뒤 zip. 버전은 `ui/dialogs.py > APP_VERSION`을 `1.0.0`으로 (D060) (D014, D043)
  - 확인: 빌드 출력 오류 없음, 콘솔 창 없이 실행, `bin/` 없음+PATH에 ffmpeg 있음/없음 두 경우 동작 | 실기기: exe로 연결 → 파일 하나 재생 → 정지 → 창 닫기 → `Get-Process ffmpeg, ffprobe` 없음. Python 3.15를 PyInstaller가 지원하지 않으면 멈추고 OPEN에 질문
  - 결과: 2026-10-25 통과 — 자동: PyInstaller 6.22.3·Python 3.15.1 빌드 오류 없음, GUI subsystem, offscreen 실행에서 PATH에 ffmpeg 있음 → 서버·인코더 시작 / 없음 → 서버 없이 안내창 대기, zip 54.9MB에 ffmpeg 없음. 사용자: ① 콘솔 창 없음, 정보 1.0.0 ② ● 초록, TV 재생 잘 됨(REMUX) ③ 유튜브 시청 중 영화를 틀었다가 창을 닫으니 Google TV 홈 화면(로그: 재생 중 종료 처리 → 수신 앱 종료) ④ `Get-Process ffmpeg, ffprobe` 결과 없음
  - 추가 (2026-10-25, Q050·D066): 아이콘 `assets/cast.ico`를 exe·창·작업표시줄에 적용하고 다시 빌드. 자동: 자가검사 "아이콘 경로" 통과, exe에 아이콘 리소스, `_internal/assets/cast.ico`, offscreen 실행 정상, zip 55.1MB(ffmpeg 없음). 실기기 2026-10-25 통과 — ① 탐색기 exe 아이콘 예 ② 창 제목 표시줄 예 ③ 작업표시줄 예
- [x] 8. `THIRD_PARTY_NOTICES.md`: 작업 7 산출물에 실제로 들어간 패키지 기준 이름·버전·라이선스·출처. LGPL(PySide6·shiboken6·zeroconf)은 라이브러리 교체 가능(onedir) 안내와 소스 위치 포함. ffmpeg는 동봉하지 않음을 명시 (D043, PRD §2.6)
  - 확인: `dist/CastPlayer/_internal`의 패키지 목록과 고지 목록 대조, 누락 0
  - 결과: 2026-10-27 통과 — PYZ의 서드파티 패키지 13개(PySide6·shiboken6·zeroconf·pychromecast·protobuf·ifaddr·requests·urllib3·idna·certifi·charset-normalizer·packaging·setuptools)와 `_internal` DLL 9개(Python·OpenSSL 3.5.9·libffi·VC 런타임)를 고지 목록과 대조, 누락 0. PyInstaller 부트로더 예외도 기재
- [x] 8-1. 배포 zip에 `LICENSE`·`THIRD_PARTY_NOTICES.md`·`README.md`·`README.en.md`를 exe 옆에 넣는다 (계획 추가 2026-10-27, Q051, D067) — `CastPlayer.spec` 끝에서 복사, CLAUDE.md 빌드 명령
  - 확인: 다시 빌드 → `dist\CastPlayer`에 4개 파일, zip 안에도 4개 파일·ffmpeg 없음, 시험 흔적 없음
  - 결과: 2026-10-27 통과 — 다시 빌드한 `dist\CastPlayer`와 zip(55.1MB, 항목 219개)에 4개 파일이 원본과 같은 내용으로 있음, ffmpeg·시험 흔적 없음
- [x] 9. 공개 전 점검: `git grep`으로 사설 IP 패턴(`192.168.`·`10.`·`172.16~31.`), 사용자 경로(`C:\Users\`), 시험 영상 파일 이름 검색 0건. `.gitignore`가 영상·`bin/*.exe`·`logs/`·`cache/`·`config.json`·`build/`·`dist/`를 막는지 (D054)
  - 확인: 검색 명령 출력 0건 (예시값 `10.0.0.x`처럼 의도한 것은 목록으로 보이고 승인)
  - 결과: 2026-10-27 통과 — 1차 검색에서 6곳(사용 예시의 실제 TV IP, docstring의 영상 제목 2개, 주석의 배포 그룹 이름, PRD §5 서브넷, REFERENCE 시험 파일 이름, QA_LOG Q의 사설 IP·기기 이름)을 예시값으로 바꾸거나 가림(QA_LOG는 "공개 전 가림, D054" 표시, Q052). 재검색: 남은 것은 점검 규칙 설명 2줄(PRD §6, 이 작업)과 시험용 `10.0.0.x`뿐. `.gitignore` 16개 경로 차단 확인. git 히스토리는 D041로 공개 직전에 새로 시작
- [x] 10. 인수 확인 — PRD §1 성공 기준(버퍼링 절반)과 이 계획에 넣은 인수 기준 F7-1~F7-4, F8-1, F3-6을 모두 실행
  - 확인: 전체 테스트 `--selftest --log` 통과(F7-1·F7-2·F8-1) | 실기기: ① 작업 3 시청 로그로 `--count-buffering` 2회 이하(F7-3, 성공 기준) ② 5초 넘는 조각마다 "← 느림" 줄, 없으면 해당 없음(F7-4) ③ exe로 REMUX 재생 중 창 닫기 → TV 플레이어 꺼짐, `Get-Process ffmpeg, ffprobe` 없음(F3-6)
  - 결과(부분): 2026-10-25 ③ F3-6 통과 (작업 7 실기기 ③④), 2026-10-24 ① F7-3 통과·② F7-4 해당 없음 (작업 3). 남음: 전체 테스트 최종 실행
  - 결과: 2026-10-27 통과 — 전체 테스트 `--selftest --log` 35/35, 종료 코드 0, `logs/cast_test_20261027_194856.txt` 기록(F7-1·F7-2·F8-1), ruff 통과. 실기기 ① F7-3 버퍼링 0회(성공 기준) ② F7-4 해당 없음 ③ F3-6 통과 — 모두 통과

## 자가 검토
- 테스트로 옮기지 않은 인수 기준: F7-3·F7-4 → 장시간 실기기 시청 로그로 판정(TV와 2시간 재생 필요), F3-6 → exe 실기기(Qt 창·TV 필요)
- 계획 수정 (2026-10-23, Q043): 스킬 변경에 따라 작업 10 인수 확인과 두 겹 테스트·확인 결과 형식을 넣음
- PRD 기능 누락: 이번 계획 밖 — 비트레이트 상한(O101, 작업 4 결과에 따라), 공개 직전 히스토리 재시작·GitHub 업로드(D041, 별도 확인), O103·O105·O106 보류
- 순서 의존: 2는 1 뒤(탐색 줄을 씀), 3은 2 뒤가 아니어도 되지만 판정은 2 뒤. 7은 4 뒤(코드가 바뀔 수 있음), 8은 7 뒤(산출물 기준), 9는 맨 끝. 5·6은 언제든
