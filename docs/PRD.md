# PRD — CastPlayer

상태: approved (2026-10-28) | 단계: 5 확정 | 갱신: 2026-10-28
<!-- 상태가 approved (YYYY-MM-DD)가 되기 전에는 코드·뼈대·의존성 설치를 하지 않는다. -->
<!-- 모든 항목 끝에 출처를 단다: [U] 사용자 · [X] 기존 코드·문서 · [AI] AI 기본값. 근거 결정은 (D###). -->
<!-- [X] 출처 약칭: C = docs/legacy/claude.md, P = docs/legacy/progress.md -->

## 1. 목적
- 해결할 문제: Windows PC에 있는 로컬 동영상 파일을 Chromecast with Google TV(4세대)로 보내는 가벼운 GUI 프로그램. PC에서는 동영상을 재생하지 않고 제어 화면만 띄운다 [X] C §1
- 사용자 (누가, 몇 명, 어떤 기기): 본인(개발·주 사용자, Windows 11 PC → Chromecast with Google TV) [X] C §3 + GitHub에서 받아 쓰는 일반 사용자 [U] (D039). Windows 11 공식 지원, Windows 10은 미시험 표기. 화면 한국어, README 한국어+영어 [U] (D040)
- 성공 기준 (관찰 가능한 장면 하나): GUI로 영화 한 편을 처음부터 끝까지 본다. 중간에 연결이 끊겨도(랜선 수십 초 분리 포함) 손대지 않고 이어지고, 잦던 버퍼링(옛 기록: 약 2시간에 약 20회)이 해결됐음을 확인한다. 끊김 기준: 재생 중·일시정지 중 각 1회 랜선 30초 분리 후 꽂으면 60초 안에 조작 없이 같은 위치(±10초)·같은 상태로 이어짐. 버퍼링 기준: 영화 한 편(약 2시간)에 2회 이하, 로그의 재생 상태 전환 PLAYING→BUFFERING 횟수로 판정(조작 뒤 10초 안은 제외) [U] (D036, D050, D051)
- 기한과 수명 (언제까지, 다 쓰면 폐기/유지): 기한 없음, 계속 쓰며 유지 [U] (D038)

## 2. 범위
### 2.1 필수
- 기기 검색·자동 연결 (마지막 기기 → 저장 IP) [X] C §9 4단계 (D026)
- 재생, 일시정지, 정지, 볼륨, 탐색 바. 일시정지하면 수신기도 일시정지 [X] C §4
- 정지하면 수신기의 기본 미디어 수신 앱을 종료. 프로그램을 끌 때도 정지 후 앱 종료 [X] C §4 (D005)
- 대상 형식 mp4, mkv, avi, ts, mov 등 (H.264, HEVC, XviD 등) [X] C §4
- 4K 해상도 유지: 축소(다운스케일)하지 않는다. 재인코딩 때만 4K·31fps 초과면 fps 절반 [X] C §4 (D009)
- 음성: AAC·MP3는 그대로 보내고(HLS 경로에서는 AAC만), 그 밖의 코덱은 AAC 2ch로 변환. 음성 트랙 선택 [X] C §4·코드 `planner.COPY_AUDIO` (D008)
- 자막: srt, smi, 내장 텍스트 → WebVTT. 투명 배경 + 검은 테두리, 크기·싱크 조절 [X] C §4 (D019~D023)
- TV와 PC 양쪽 탐색 바가 처음부터 전체 길이를 보이고, TV 리모컨으로 전체 구간 탐색 [X] C §4 (D015)
- 연결이 끊겼다 다시 연결되면 사용자 조작 없이 그 자리에서 이어 재생 (일시정지 상태 유지) [X] C §4 (D029, D033)
- 버퍼링을 줄인다: 끊겨도 세션 유지(완료), 조각 전송 계측(완료). 영화 한 편(125.5분) 버퍼링 0회로 성공 기준 통과(2026-10-24), 비트레이트 상한은 하지 않음 [X] C §4 (D034) · [U] (D065)
- GitHub 공개: README(한국어+영어), LICENSE(MIT, META PUBLIC), 의존성 라이선스 고지, Releases에 exe(onedir zip). zip의 exe 옆에 LICENSE·THIRD_PARTY_NOTICES.md·README.md·README.en.md 동봉. 1.0.0 공개 (2026-10-27, Releases v1.0.0) [U] (D039~D044, D067)
- 프로그램 아이콘 `assets/cast.ico`를 exe 파일과 창·작업표시줄에 쓴다 [U] (D066)
- ffmpeg·ffprobe를 프로그램 옆 `bin/` → PATH 순서로 자동으로 찾는다 [U] (D042)
### 2.2 있으면 좋음
- (없음. 비트레이트 상한 옵션은 §2.3으로 옮김, D065)
### 2.3 이번에는 안 함
- PC 화면에서 동영상 재생 [X] C §1
- ffmpeg 동봉·설치 대행 (README 안내만) [U] (D042)
- 화면 다국어화 [U] (D040)
- 비트레이트 상한 옵션 — 장시간 시청에서 버퍼링 0회라 하지 않음. 버퍼링이 다시 잦아지면 O101 설계부터 [U] (D065)
- 이미지 자막(PGS, VobSub 등) 표시 — "지원 안 함"으로 회색 처리, 자리만 남김 [X] C §4 (D007)
### 2.4 반목표 (절대 그렇게 되면 안 되는 동작)
- 정지·종료 때 기본 수신 앱이 아닌 다른 앱(유튜브 등)을 종료 [X] C §9 1단계 (D005)
- 연결할 때 PC에 저장된 볼륨으로 TV 볼륨을 덮어씀 [X] C §9 4단계 (D032)
- 끊김 복구 기억이 남아 새 파일을 옛 위치에서 재생 [X] C §9 끊김 복구 (D029)
- 프로그램을 닫은 뒤 ffmpeg·ffprobe 프로세스가 남음 [X] C §6 (D013)
### 2.5 나중을 위해 구조만 준비
- 연속재생 (`Playlist`, `on_finished` 훅) [X] C §4
### 2.6 제약 (법·라이선스·비용·개인정보)
- 커스텀 수신 앱은 쓸 수 없다 → 기본 미디어 수신기(CC1AD845)만 [X] C §4 (D035)
- Windows 11 공식 지원, Windows 10은 "동작할 수 있으나 미시험" [U] (D040)
- 오픈소스, MIT 라이선스(저작권자 META PUBLIC), GitHub 공개 [U] (D039, D040)
- 의존성 라이선스: pychromecast·casttube·ifaddr·charset-normalizer MIT, protobuf BSD-3, zeroconf LGPL-2.1+, PySide6 LGPL-3.0 → exe 배포 시 LGPL 고지 필요 [X] (Q018)
- ffmpeg·ffprobe: 일반적으로 쓰이는 빌드가 GPL(현재 개발 환경도 GPLv3) → 배포물에 넣지 않는다 [U] (D042)
- 이슈·PR은 받되 응답 보장 없음 [U] (D044)
- 공개 저장소에 개인 정보(사설 IP, 기기 이름, 사용자 경로)와 시험 영상 파일 이름을 남기지 않는다 [AI] (Q020 승인) → 공개 직전 히스토리 새로 시작, `docs/legacy/` 로컬 보관, 문서는 예시값 [U] (D041)

## 3. 기능
### F1 기기 검색·연결
- 정상 흐름: 시작 시 mDNS 검색 → 저장 UUID가 보이면 자동 연결. 8초 뒤에도 연결 전이면 저장 IP를 known host로 추가 → 8초 뒤에도 없으면 포기 안내. 메뉴에서 IP로 기기 추가 [X] C §8 main_window
- 예외: TV가 꺼져 있으면 자동 연결 실패가 정상 동작 [X] P 4단계 1차
- 상태별 동작: 연결 전에는 파일 열기·끌어다 놓기 잠김. 연결 표시 회색 미연결 / 노랑 연결 중 / 초록 연결됨 / 빨강 다시 연결 중. 포기 안내 뒤에는 기기 목록에서 [연결]을 직접 누름 [X] C §8 main_window
- 인터페이스: `CastManager.start_discovery/add_known_host/rescan/connect/disconnect`, `CastCallbacks`, `config.json`(`last_device_uuid`, `last_device_host`, `known_hosts`, `auto_connect`) [X] C §8
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F1-1 [실기기] Given 저장된 기기가 켜져 있고 같은 네트워크에 있음 / When 프로그램을 시작 / Then 조작 없이 연결되고 연결 표시가 ● 초록 [X]
  - F1-2 [실기기] Given 기기에 연결되지 않음 / When 파일을 끌어다 놓음 / Then 열리지 않고 "먼저 기기를 연결하세요." 안내 [X]
  - F1-3 [실기기] Given 저장된 기기의 TV가 꺼져 있음 / When 프로그램을 시작 / Then 20초 안에 "…을(를) 찾지 못했습니다." 안내, ● 회색 [X] (8초 + 8초, 20초는 [AI] 여유)
  - F1-4 [자동] Given 목록에 기기가 아직 없음 / When [연결]을 누름 / Then 10초 안에 나타나면 연결, 아니면 "기기 정보를 찾을 수 없습니다." [X] (D033)
  - F1-5 [실기기] Given 검색(mDNS)에 보이지 않는 기기 / When 메뉴 → IP로 기기 추가에 IP를 넣음 / Then 목록에 나타나 연결할 수 있음 [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D026
### F2 불러오기·송출 방식 결정
- 송출 방식 규칙: 영상이 수신기 미지원(H.264 High 5.1 초과·10bit, HEVC Main/Main10 5.1 초과, 그 밖 코덱, 표시 시각 결함)이면 TRANSCODE. 아니면 mp4가 아님·HEVC 태그가 hvc1 아님·음성 변환 필요·첫 번째가 아닌 음성 트랙 중 하나라도 있으면 REMUX, 없으면 DIRECT [X] 코드 `planner.make_plan` (D010, D015, D024, D046)
- 정상 흐름: probe → 계획(DIRECT / REMUX / TRANSCODE) → 키프레임 분석(REMUX, 캐시) → 자막 준비 → 송출. DIRECT는 mp4 파일 그대로, 나머지는 HLS VOD(fMP4) [X] C §8 player·planner·hls
- 예외: ffmpeg/ffprobe를 `bin/`·PATH 어디서도 못 찾음 → 경고창(찾아본 곳, 복사 가능한 `winget install Gyan.FFmpeg`, 설치 후 다시 실행) 뒤 종료 코드 2 [U] (D042, D045). 포트 충돌 → 안내창 후 종료 코드 2. probe 실패 → ProbeError. 키프레임 98% 이상 읽었으면 경고 후 사용 [X] C §8
- 상태별 동작: 새 파일로 바꾸기 전 확인·취소 창. 불러오기는 TaskRunner에서 한 번에 하나 [X] C §9 4단계
- 인터페이스: `PlaybackController.load/play`, `MediaServer.register` 경로 `/media/<token>`, `/hls/<token>/`, `/sub/<token>/` [X] C §8
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F2-1 [자동] Given mp4 + H.264 + AAC, 기본 음성 트랙 / When 파일을 엶 / Then DIRECT로 파일을 그대로 보냄 (로그 `재생: DIRECT`) [X]
  - F2-2 [자동] Given mkv + H.264 + DTS / When 파일을 엶 / Then REMUX, 음성은 AAC 2ch로 변환 [X]
  - F2-3 [자동] Given XviD 또는 H.264 10bit 영상 / When 파일을 엶 / Then TRANSCODE [X]
  - F2-4 [자동] Given ffmpeg가 `bin/`·PATH 어디에도 없음 / When 프로그램을 시작 / Then 안내창(찾아본 곳, `winget install Gyan.FFmpeg`) 뒤 종료 코드 2 [U] (D045)
  - F2-5 [실기기] Given 재생 중 / When 다른 파일을 엶 / Then 확인 창이 뜨고, 취소하면 기존 재생이 이어짐 [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D001, D042, D008~D018, D024
### F3 재생 제어
- 정상 흐름: 재생/일시정지(Space), 정지(S, 수신 앱 종료), 탐색 바·←/→ 5초(300ms 모음), 볼륨 ↑/↓ 5%, 음소거 M [X] C §9 4단계
- 예외: 끊겨 있는 동안의 탐색은 버림 [X] C §8 main_window
- 상태별 동작: 끝났거나 정지한 뒤 탐색·재생하면 그 위치부터 다시 불러옴 [X] C §9 B안 (D017)
- 인터페이스: `PlaybackController.seek/stop`, `CastManager.pause/resume/seek/set_volume/set_muted` [X]
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F3-1 [실기기] Given 재생 중 / When Space를 누름 / Then TV가 일시정지하고, 다시 누르면 재생 [X]
  - F3-2 [실기기] Given 재생 중 / When →를 0.3초 안에 3번 누름 / Then 15초 앞으로 한 번만 이동 (로그 `탐색:` 1줄) [AI]
  - F3-3 [자동] Given 재생이 끝났거나 정지됨 / When 탐색하거나 재생을 누름 / Then 탐색한 위치부터(재생 버튼이면 끝난 영상은 처음부터) 다시 불러옴 [X] (D017)
  - F3-4 [실기기] Given TV 볼륨을 임의 값으로 둠 / When 연결 / Then TV 볼륨이 그대로이고 슬라이더가 그 값을 따름 [X] (D032)
  - F3-5 [실기기] Given 유튜브 재생 중, 파일을 열지 않음 / When 연결한 뒤 정지를 시도 / Then 정지 버튼이 비활성이고 유튜브가 그대로 유지됨 [U] (D058)
  - F3-6 [실기기] Given REMUX·TRANSCODE로 재생 중 / When 창을 닫음 / Then TV 플레이어가 꺼지고, `Get-Process ffmpeg, ffprobe` 결과 없음 [X] (2.4 반목표, D013)
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D002, D005, D017, D026, D032
### F4 음성 트랙
- 정상 흐름: 트랙 선택 → 다시 계획 → 재생 중이면 현재 위치에서 다시 불러옴 [X] C §8 player
- 예외: 끊긴 동안·확인 중이면 보류했다가 복구 뒤 한 번 반영 [X]
- 상태별 동작: 일시정지 중 변경하면 일시정지 유지. mp4에서 첫 번째가 아닌 트랙은 REMUX, 첫 트랙이면 DIRECT [X] C §9 음성 변경. default 플래그가 2번 이후 트랙에 있는 mp4도 REMUX (의도된 동작) [U] (D046)
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F4-1 [실기기] Given 음성 트랙이 2개인 mp4를 1번으로 재생 중 / When 2번 트랙을 고름 / Then 현재 위치에서 REMUX로 다시 불러옴 [X]
  - F4-2 [자동] Given 같은 mp4를 2번 트랙으로 재생 중 / When 1번 트랙을 고름 / Then DIRECT로 돌아감 [X] (D046)
  - F4-3 [자동] Given 일시정지 중 / When 음성 트랙을 바꿈 / Then 다시 불러온 뒤에도 일시정지 [X]
  - F4-4 [자동] Given 연결이 끊긴 동안 / When 음성 트랙을 바꿈 / Then 바로 불러오지 않고, 다시 연결된 뒤 끊긴 위치에서 한 번 반영 [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D008, D025, D046
### F5 자막
- 정상 흐름: 외부(같은 폴더·같은 이름)·내장 텍스트 자막을 WebVTT로 변환. 자동 선택은 외부 한국어 → 내장 한국어 → 첫 외부 → 끄기. 크기 0.5~2.0배(±0.1), 싱크 ±0.5초(Shift ±0.1초), 기본 0초 [X] C §9 3단계 (D021~D023)
- 예외: 이미지 자막은 회색 "지원 안 함". 인코딩 판별 실패 시 CP949(replace) [X] C §8 subtitles
- 상태별 동작: 처음 켤 자막은 PLAYING/PAUSED 뒤에 켬. 싱크 변경은 다시 불러오기(GUI 1.5초 디바운스), 일시정지 유지 [X]
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F5-1 [자동] Given 영상과 같은 폴더·같은 이름의 한국어 srt가 있음 / When 파일을 엶 / Then 그 자막이 자동으로 켜짐 [X] (D021)
  - F5-2 [실기기] Given 이미지 자막(PGS)이 든 mkv / When 자막 목록을 봄 / Then PGS 항목이 회색 "지원 안 함" [X] (D007)
  - F5-3 [실기기] Given 재생 중 / When 싱크 +0.5를 3번 연타 / Then 마지막 입력 1.5초 뒤 한 번만(+1.5초) 다시 불러옴 (로그 `자막 싱크 반영` 1줄) [X]
  - F5-4 [자동] Given 일시정지 중 / When 싱크를 바꿈 / Then 다시 불러온 뒤에도 일시정지 [X]
  - F5-5 [자동] Given UTF-8도 CP949도 아닌 자막 / When 파일을 엶 / Then 오류 없이 열림 (판별 실패면 CP949로 읽고 깨진 글자는 대체) [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D019~D023
### F6 연결 끊김 복구
- 정상 흐름: 끊겨도 송출 자원 유지 → 다시 연결되면 세션 확인 → 살아 있으면 그대로, 없으면 끊긴 위치·일시정지 상태로 다시 불러옴 [X] C §9 끊김 복구
- 현재 상태: 보강 완료 — pychromecast가 포기하면 끊긴 순간부터 90초까지 3초 간격으로 마지막 IP에 직접 다시 연결, 그 뒤 30초 동안 송출 자원·끊긴 위치 유지(같은 기기면 이어 감), 기다리는 동안 기기 목록 유지, [연결]은 최대 10초 대기 [U] (D033, D056, D059)
- 예외: 다시 연결 대기 시간이 지나면 "기기에 다시 연결하지 못했습니다. [연결]을 눌러 주세요." 안내 후 송출 자원 정리 [X] C §8 main_window
- 상태별 동작: 메뉴에서 연결 해제했거나 정지한 뒤에는 이어 재생하지 않음 [X]
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F6-1 [실기기] Given 재생 중 / When 랜선을 30초 뽑았다 꽂음 / Then 60초 안에 조작 없이 같은 위치(±10초)·같은 상태(재생 중)로 이어짐 [U] (D051)
  - F6-2 [실기기] Given 일시정지 중 / When 랜선을 30초 뽑았다 꽂음 / Then 일시정지 상태 그대로 이어짐 [U] (D051)
  - F6-3 [실기기]+[자동] Given 재생 중 / When 랜선을 뽑고 61~90초 사이에 꽂음 / Then 꽂은 뒤 60초 안에 조작 없이 같은 위치(±10초)·같은 상태로 이어짐 [U] (D059)
  - F6-4 [실기기] Given 끊긴 지 120초가 넘음 / When 그대로 기다림 / Then "기기에 다시 연결하지 못했습니다" 안내 뒤 정리, ffmpeg 남지 않음 [X] (D059)
  - F6-5 [자동] Given 메뉴에서 연결 해제했거나 정지함 / When 다시 연결 / Then 이어 재생하지 않음 [X]
  - F6-6 [자동] Given 끊김 기억이 남아 있음 / When 다른 파일을 엶 / Then 새 파일을 처음부터 재생 (옛 위치 안 씀) [X] (2.4 반목표, D058)
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D029, D033
### F7 로그·진단
- 정상 흐름: GUI `logs/castplayer.txt`(1MB×3, INFO), `-v` 또는 메뉴 디버그 로그로 DEBUG. 전송 계측(조각별 준비·전송 시간, 느림 표시) [X] C §8 main·media_server
- 추가: 재생 상태가 바뀔 때마다 INFO 한 줄 `재생 상태: A → B, N초` (버퍼링 횟수 판정용), 탐색할 때 `탐색: N초`, 판정은 `tools.cast_test --count-buffering` [U] (D050)
- 인터페이스: 로그 확장자 `.txt`, 로그 폴더 열기 메뉴. 조각 전송이 5초(`SLOW_SEND`) 넘으면 "← 느림" [X]
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F7-1 [자동] Given GUI로 재생 중 / When 재생 상태가 바뀜 / Then INFO `재생 상태: A → B, N초` 한 줄, 같은 상태 반복은 줄 없음 [U] (D050)
  - F7-2 [자동] Given 재생 중 / When 탐색함 / Then INFO `탐색: N초` 한 줄 [AI]
  - F7-3 [자동]+[실기기] Given 영화 한 편을 본 GUI 로그 / When `--count-buffering`을 실행 / Then 조작 뒤 10초 안을 뺀 PLAYING→BUFFERING 횟수. 2회 이하면 통과 [U] (D050)
  - F7-4 [실기기] Given `-v` 없이 실행 중 / When 장시간 시청 중 5초를 넘는 조각 전송이 생김 / Then 그 조각마다 "← 느림" 줄이 남음 (없으면 이 기준은 해당 없음으로 기록) [X]
  - F7-5 [실기기] Given 재생 중 / When 메뉴에서 디버그 로그를 켬 / Then 다시 시작하지 않아도 DEBUG 줄이 기록됨 [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D030
### F8 테스트 도구
- 정상 흐름: `python -m tools.cast_test "<파일>" [옵션]` 콘솔 시험, `--selftest`(TV 불필요), `--droptest`, `--log` [X] C §8 tools. 버퍼링 판정 `--count-buffering [로그…]`: PLAYING→BUFFERING 횟수, 조작 뒤 10초 안은 뺌 [X] `tools/cast_test.py > count_buffering` (D050)
- 인터페이스: 테스트 도구 코드는 `tools/cast_test.py` 한 파일만 둔다 (시험용 영상 파일과는 별개) [X]
- 인수 기준 (D061, 확인: [자동] = `--selftest`, TV 없이 가짜 cast·기기 목록·로그 수집으로 모의 / [실기기] = 사용자 확인):
  - F8-1 [자동] Given TV 없음 / When `--selftest --log` / Then 마지막 줄 `[자가검사] N개 중 N개 통과`, 종료 코드 0, 결과가 `logs/cast_test_날짜_시각.txt`에도 남음 [X]
  - F8-2 [자동] Given 자가검사 항목 하나가 실패 / When `--selftest` / Then 그 줄이 `[실패]`로 나오고 종료 코드 1 [X]
  - F8-3 [실기기] Given 실기기 연결, 긴 영상 / When `--droptest` / Then 마지막에 `[끊김 시험] 결과: 통과, 통과, 통과`, 종료 코드 0 [X]
- 확인 방법: 인수 기준의 표시대로. 자동은 `--selftest`, 실기기는 §6의 확인 결과 형식 (D062)
- 근거: D031

## 4. 기술 결정
| 항목 | 선택 | 버린 안 (이유) | 근거 |
|---|---|---|---|
| 언어 | Python (설계 기준 3.11+, 현재 3.15.1 .venv) | - | [X] C §3 |
| 송출 제어 | pychromecast, 기본 미디어 수신기 | 커스텀 수신 앱 (불가) | D035 [X] |
| GUI | PySide6 | - | [X] C §4 |
| 미디어 서빙 | 표준 `ThreadingHTTPServer`, 8765, 토큰 경로, CORS | - | D001 [X] |
| 변환 | ffmpeg/ffprobe (`bin/` → PATH, 동봉 안 함) | 동봉 (GPL 의무) | D042 [U] |
| 전체 길이·탐색 | HLS VOD (fMP4) | A안 duration 전달 (수신기가 무시, 실측) | D015 [X] |
| 인코더 | nvenc → qsv → amf → libx264 (실측 amf) | - | D012 [X] |
| 스레딩 | core는 Qt 비의존·콜백, cast-worker 1개, TaskRunner 1개 | - | D003, D004, D027 [X] |
| 배포 | PyInstaller onedir, `--windowed` | - | D014 [X] |
| 공개 | GitHub, MIT, 화면 한국어·README 한/영 | 화면 다국어화 (작업량) | D039, D040 [U] |

## 5. 비기능 요구
- 실행 환경: Windows 11 (공식, D040), Python 3.11 이상(개발 환경 3.15.1 .venv). PC와 Chromecast가 같은 서브넷 (개발 환경: PC 유선, TV 5GHz 무선, 같은 사설 서브넷) [X] C §3 (D041 예시값)
- 성능: 가볍고 반응이 빨라야 함, 수치 기준 없음 [X] C §4 · [U] (D052)
- 배포 형태: PyInstaller onedir exe(콘솔 없음)를 zip으로 GitHub Releases에, 소스는 저장소에 [X] C §3 (D014) · [U] (D043). 개발 환경에 PyInstaller는 아직 설치 전이며, Python 3.15 대응 여부는 빌드 작업에서 설치하며 확인 [X] 2026-10-23 pip list
- 로그: `logs/castplayer.txt` 1MB×3, `-v` DEBUG, tools는 `--log` [X] (D030)

## 6. 검증과 운영
- 자동 테스트 대상: `tools/cast_test.py --selftest`의 항목 (인수 기준의 [자동]과 그 안쪽 단위 검사). Claude가 직접 실행 [X] · [U] (D031, D048)
- 실기기 확인 대상과 결과 전달 방식: 인수 기준의 [실기기] 항목(TV 송출 필요). Claude가 기대 결과를 번호 항목으로 주고, 사용자는 항목마다 "예/아니요와 본 것"으로 답한다. 로그로 알 수 있는 것은 Claude가 `logs/`의 `.txt`를 읽어 함께 판정. 모든 항목이 "예"일 때만 통과, 애매한 답은 그 항목만 다시 묻는다 [U] (D062, D047 대체)
- 전체 테스트 명령과 걸리는 시간: `.venv\Scripts\python -m tools.cast_test --selftest --log` (TV 불필요, 약 6초). 작업마다 실행, 하나라도 실패하면 다음 작업으로 가지 않음 [U] (D064)
- 편집 때 자동 검사: `.py` → `.venv\Scripts\ruff.exe check` (ruff 기본 규칙 + `core/`에서 PySide6 import 금지 `TID251`, D003) → `pyright` (전역 npm 설치본, 설정 `pyrightconfig.json`, 오류 0개 유지). `.claude/hooks/check.ps1`이 실행 [U] (D063, D068)
- 반목표 확인: 유튜브 재생 중 캐스팅 전 연결·정지 → 유튜브 유지 (캐스팅한 뒤 정지하면 우리 수신 앱이 끝나 TV는 홈으로 감. Chromecast는 앱을 하나만 띄우므로 정상) / 연결 직후 TV 볼륨 그대로 / 끊김 뒤 다른 파일 열기 → 처음부터 재생 / 종료 뒤 `Get-Process ffmpeg, ffprobe` 없음 [U] (D058)
- 공개 전 점검: 저장소 전체(`git grep`)에서 사설 IP 패턴(`192.168.`·`172.16~31.`·`10.`, 문서용 예시 `10.0.0.x`·`192.0.2.x` 제외)·사용자 경로(`C:\Users\`)·시험 영상 파일 이름(작업 폴더의 영상 파일 이름에서 확장자를 뺀 문자열) 검색 0건 [U] (D054) · 패턴 [AI]
- 위험한 명령 (실행 전 확인 대상): TV 송출 시험(`tools.cast_test <파일>`, `main.py`), `pip install`, `git push`, `cache/`·`logs/` 삭제, 공개 직전 git 히스토리 재시작(D041) [U] (D048)
- 버전 관리 (커밋 단위, 메시지 형식): 작업 하나당 커밋 1개, `feat:`/`fix:`/`docs:`/`chore:`, main 직접 [U] (D049)

## 7. 미결
→ `docs/discovery/OPEN.md`

## 8. 변경 이력
| 날짜 | 변경 | 근거 |
|---|---|---|
| 2026-10-23 | adopt: 옛 claude.md·progress.md에서 초안 역추출 | Q001~Q012 |
| 2026-10-23 | §1 목적 확정 (성공 기준, 수명, MIT 공개) | D036~D040 |
| 2026-10-23 | §2 범위 확정 (공개 전 정리, ffmpeg 찾기, 배포물, 이슈) | D041~D044 |
| 2026-10-23 | §3 기능 확정 (ffmpeg 누락 동작, mp4 음성 판정 유지) | D045, D046 |
| 2026-10-23 | §4~§6 확정, 검사 지적 반영, PRD 승인 | D047~D054, Q030, Q032 |
| 2026-10-23 | §6 반목표 확인: 유튜브 유지는 캐스팅 전 연결·정지에 한정, 캐스팅 뒤 정지 → 홈은 정상 | D058 |
| 2026-10-23 | §3 F1~F8 인수 기준 39개, F6 현재 상태·F7 로그 갱신. §6 확인 결과 형식, 전체 테스트, 편집 때 검사 | D061~D064 |
| 2026-10-24 | §2 버퍼링 기준 통과 기록, 비트레이트 상한 옵션을 §2.2 → §2.3 | D065 |
| 2026-10-27 | §2.1 아이콘·zip 동봉 문서·1.0.0 공개, F8 --count-buffering | D050, D066, D067 |
| 2026-10-28 | §6 편집 때 검사에 pyright 추가 (기존 오류 71개 정리) | D068 |
