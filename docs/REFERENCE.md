# REFERENCE — CastPlayer
<!-- 필요할 때 검색해 읽는다. 참조는 R§n, 코드 위치는 파일 > 함수. -->
<!-- 출처: docs/legacy/claude.md §5~8 (2026-10-23 adopt). 코드와 다르면 코드가 사실이다. -->

## R§1 아키텍처
- 흐름: 파일 열기 → `probe` → `planner.make_plan`(DIRECT/REMUX/TRANSCODE) → `keyframes`(REMUX, 캐시) → `subtitles.load_subtitles` → `PlaybackController.play` → `MediaServer`에 리소스 등록 → `CastManager.play_media` → 수신기가 HTTP로 가져감
- DIRECT는 원본 mp4를 `/media/<token>`로, REMUX·TRANSCODE는 `HlsSession`이 ffmpeg 1개의 fMP4 출력을 조각으로 나눠 `/hls/<token>/`로, 자막은 `/sub/<token>/<trackId>.vtt`
- 스레드: pychromecast 소켓 스레드(콜백) · `cast-worker`(블로킹 명령 큐) · `TaskRunner`(불러오기·음성 변경, 1개) · Qt 메인. 콜백은 `ui/bridge.py`가 Signal로 넘긴다
- 시작 순서 (`main.py > main`): AppConfig.load → 로그 → QApplication → ffmpeg 확인 → EncoderDetector.start → MediaServer.start → CastBridge → CastManager → PlaybackController → MainWindow. 종료: `cm.shutdown → ctrl.shutdown → server.stop`

### 모듈
- `core/paths.py` — `app_dir()`(frozen이면 exe 폴더), `bin_dir`, `ffmpeg_path`, `ffprobe_path`, `config_path`, `cache_dir`. 로그 폴더 함수는 없고 `main.py`·`main_window._open_logs`가 `app_dir()/"logs"`를 직접 씀
- `core/config.py` — `AppConfig`(server_port 8765, last_device_uuid/name/host, known_hosts, volume, subtitle_scale, auto_connect, debug_log). `known_hosts`는 사용자가 추가한 IP만, `last_device_host`는 mDNS 실패 시 힌트
- `core/proc.py` — `NO_WINDOW`, `bind_to_job`(Job Object KILL_ON_CLOSE)
- `core/media_server.py` — `FileResource`(Range 지원), `HlsResource`(get(name)→(data, mime)|None), `BytesResource`·`StreamResource`(사용처 없음, 유지). `register(res, prefix) -> "/prefix/<token>"`. CORS, `SLOW_SEND`=5초 넘는 조각 전송은 "← 느림"
- `core/cast_manager.py` — pychromecast 래퍼
  - 상수: `CONNECT_TIMEOUT`=15, `CMD_TIMEOUT`=5, `READY_WAIT`=5, `LOAD_WAIT`=15, `CLOSE_LOAD_WAIT`=3
  - 공개 명령(큐, 비동기): connect, disconnect, play_media, pause, resume, seek, set_subtitle, set_text_style, check_session, stop, set_volume, set_muted
  - `_do_connect`: `get_chromecast_from_cast_info(tries=3, retry_wait=2, timeout=10)` — 끊긴 뒤 재접속에도 쓰임. 맨 앞에서 `_lost = None`
  - `_do_play` → `_wait_loaded`: LOAD 응답 또는 새 세션 번호를 기다림 (`block_until_active` 쓰지 않음)
  - 끊김 기록 `_on_conn_status`: `_last_point`(활성 상태일 때만 갱신) → LOST 때 `_lost_point=(위치, 일시정지)`, 연달아 끊기면 처음 값 유지. DISCONNECTED("다시 연결 포기")면 `drop()`
  - `check_session`: `_wait_rx_ready` → `_judge`(수신 앱·세션·contentId 확인) → 살아 있으면 요청 상태 복원
  - `rescan`: 연결이 없으면 브라우저·zeroconf를 새로 띄움 → 목록이 비었다가 mDNS 응답으로 채워짐
- `core/planner.py` — `COPY_AUDIO={aac, mp3}`, `pick_audio`(None이면 default 플래그 → 첫 트랙), `make_plan`(규칙은 PRD §3 F2)
- `core/probe.py` — `probe() -> MediaInfo`, `check_pts_order`(B프레임 h264/hevc 앞 5초 pts가 저장 순서대로만 증가하면 `pts_broken`)
- `core/encoders.py` — nvenc → qsv → amf → libx264 감지(720p 0.5초 시험, 20초 제한)
- `core/keyframes.py` — ffprobe compact 출력을 이름으로 파싱, 캐시 `cache/keyframes/<sha1>.json`(키: 버전|경로|크기|mtime), 98% 이상 읽으면 사용
- `core/transcoder.py` — `build_args`(`-copyts -start_at_zero`, 영상 복사 탐색 +0.25초, `MOVFLAGS`=frag_keyframe+empty_moov+default_base_moof+frag_discont+delay_moov, `-use_editlist 0`), `FFmpegProcess`(1회 실행, stderr 마지막 20줄)
- `core/hls.py` — `SEG_LEN`=6, `WAIT_AHEAD`=3, `MAX_AHEAD`=10, `MEMORY_LIMIT`=512MB, `WAIT_TIMEOUT`=30. `fixed_timeline`(TRANSCODE), `keyframe_timeline`(REMUX). `HlsSession.get(name)`: init은 조각 0부터, 처음 받은 init만 사용, tfdt 보정 없음
- `core/subtitles.py` — 인코딩 판별 UTF-16 BOM → UTF-8 BOM → UTF-8 → CP949 → charset-normalizer, SRT/SMI/ASS 파서, `SubtitleSet.auto_select`, `text_style(scale)`
- `core/player.py` — `PlaybackController`: load, play, seek, set_audio, select_subtitle, set_subtitle_scale, adjust_subtitle_delay(wait), `mark_lost`/`recover`/`forget_lost`(세대 번호 `_lost_gen`), stop, shutdown
- `ui/main_window.py` — 상수 `AUTO_HOST_FALLBACK_MS`=8000, `RECONNECT_WINDOW`=30, `SEEK_STEP`=5, `SEEK_COALESCE_MS`=300, `VOL_STEP`=5. 연결 흐름: `_connect`, `_connect_selected`(`_reconnect_uuid=None`), `_on_connected`(resume이면 `ctrl.recover()`), `_on_lost`, `_on_disconnected`(곧바로 `ctrl.shutdown()` → `cm.rescan()`), `_reconnect_timeout`
- `ui/widgets.py` — `SeekSlider`(드래그 중 미리보기, 키보드 포커스 없음), `fmt_time`. `ui/dialogs.py` — `APP_VERSION`
- `tools/cast_test.py` — 명령 p, r, s, o, g 초, a 번호, t, c 번호, y 초, z 배율, v 볼륨, m on|off, i, x(연결 끊기), q. `--selftest`(player 11건 + manager 10건), `--droptest`(장면 3개), `--log`, `-v` 압축(`_CompactFilter`), `-vv` 원본

## R§2 외부 사양·제약
- Cast 기본 미디어 수신기 (`CC1AD845`) 지원 형식 (출처: https://developers.google.com/cast/docs/media)
  - 영상: H.264 High Level 5.1 이하(4K30), HEVC Main/Main10 Level 5.1 이하(4K60), VP9 Profile 2
  - 컨테이너: MP4, WebM, MP2T 등. MKV·AVI는 재생 불가
  - 자막: WebVTT, TTML. CORS 헤더 필요
  - AC-3/E-AC-3는 패스스루라 소리가 안 날 수 있음 → AAC로 변환
- pychromecast 14.0.10 (https://github.com/home-assistant-libs/pychromecast)
  - `play_media()`는 `stream_type`을 안 주면 LIVE → BUFFERED 명시 (D002)
  - `play_media(subtitles=...)`는 자막 1개만, `media_info`의 tracks를 덮어씀 → 쓰지 않음 (D019)
  - 채널 연결 시 GET_STATUS 자동 전송. `MediaStatus.update`는 빈 status 목록을 무시
  - 연결이 끊기면 `channel_disconnected()`가 미디어 상태를 비운 **뒤** LOST를 알림 (T5)
  - `block_until_active`는 이벤트가 켜져 있으면 바로 돌아오고, 세션 번호 없는 메시지에서 이전 번호 유지 (T7)
  - 연결 직후 볼륨을 보내면 TV 볼륨을 덮어씀 (T11)
- 수신기 실측
  - 처음 켤 자막의 tracks 정보는 BUFFERING 이후 도착 → PLAYING/PAUSED 뒤 EDIT_TRACKS_INFO
  - `textTrackStyle`(글자 크기)은 EDIT_TRACKS_INFO로 바로 바뀜
  - LOAD 응답(새 세션)까지 2.07~2.80초 (REMUX HLS)
  - 버퍼링 직전마다 같은 조각을 약 8초 간격으로 재요청. REMUX 조각 평균 약 10.6초, 4~39MB
  - TV가 꺼져 있으면 mDNS 미검색, 저장 IP 확인도 timeout

## R§3 설계 근거
<!-- 내용은 docs/discovery/DECISIONS.md에 있다. 여기는 색인만. -->
- D001 — 표준 HTTP 서버, 8765, 토큰 경로, CORS
- D003 — core는 Qt 비의존, 콜백 → Signal
- D004 — pychromecast 명령은 cast-worker 큐
- D005 — 정지 시 기본 수신 앱만 종료
- D008 — 음성 AAC 변환·복사 규칙
- D013 — 외부 프로세스 Job Object
- D015 — HLS VOD (A안 duration 전달 버림)
- D016 — HLS 조각·시간축 세부
- D018 — ffmpeg 세션당 1개, 교체
- D019 — 자막 WebVTT, tracks 직접
- D023 — 싱크 변경은 다시 불러오기
- D024 — 표시 시각 결함 → TRANSCODE
- D029 — 끊김 복구 (자원 유지, RECEIVER_STATUS 뒤 확인)
- D033 — 실제 끊김 보강 설계 (미구현)
- D042 — ffmpeg `bin/` → PATH, 동봉 안 함
- D046 — 첫 번째가 아닌 음성 트랙은 REMUX
- D050 — 재생 상태 전환 로그로 버퍼링 판정

## R§4 함정 대장
| ID | 증상 | 원인 | 대처 | 근거 |
|---|---|---|---|---|
| T1 | 탐색 바 길이가 받은 만큼 계속 늘어남 | 길이 정보 없는 fMP4 실시간 스트림에서 수신기가 `media_info.duration`을 무시 | HLS VOD + ENDLIST | D015, 2026-10-16 로그 |
| T2 | 싱크를 바꿔도 화면 자막이 그대로 | 수신기가 한 번 받은 VTT를 다시 요청하지 않음 (EDIT_TRACKS_INFO로 껐다 켜도 GET 없음) | 새 토큰 주소로 다시 불러오기 | D023 |
| T3 | x265 mp4가 DIRECT에서 끊김 | B프레임인데 ctts(표시 시각)가 빠짐 — MKVToolNix 45 이전으로 만든 mp4의 알려진 결함 | `pts_broken` → TRANSCODE | D024 |
| T4 | .ts가 LOAD_FAILED | `empty_moov`가 `aac_adtstoasc` 첫 패킷 전에 moov를 써서 AudioSpecificConfig가 빠짐 | `delay_moov` + `-use_editlist 0` | D016 |
| T5 | 끊긴 위치가 0으로 기록됨 | pychromecast가 상태를 비운 뒤 LOST를 알림 | `_last_point`를 계속 기록해 두고 사용 | D029 |
| T6 | 다시 연결 직후 또 끊김 (BAD_LENGTH) | 우리 요청과 pychromecast의 GET_STATUS·PING이 같은 SSL 소켓에 겹쳐 씀 | RECEIVER_STATUS를 받은 뒤 요청 | D029 |
| T7 | 다시 불러온 직후 STOP이 `INVALID_MEDIA_SESSION_ID` | `block_until_active`가 이전 세션 번호로 바로 돌아옴 | LOAD 응답·새 세션 번호 대기 | D029 |
| T8 | 랜선 분리 뒤 이어 재생 실패 | pychromecast가 약 4초 만에 재접속 포기 → 포기 처리에서 자원·기억 정리 → 다시 꽂은 뒤 약 48초 mDNS 목록 비어 [연결] 실패 | 보강 설계 (미구현) | D033, 2026-10-23 GUI 시험 |
| T9 | 짧은 끊김 뒤 오류 310 → IDLE | 끊길 때 HLS 세션을 정리해 TV가 다음 조각에서 404 | 끊겨도 자원 유지 | D029 |
| T10 | .ts 키프레임 0개 | ffprobe 줄 끝 `\|` 때문에 K 플래그 파싱 실패 | compact 형식 + 이름 파싱 | keyframes.py |
| T11 | 연결하면 TV 볼륨이 바뀜 | 연결 직후 `set_volume(cfg.volume)`이 TV 값을 덮어씀 | 그 줄 삭제 (미구현) | D032 |
| T12 | 남은 일시정지 세션 위 LOAD가 22초 걸리고 PLAYING 뒤 약 8초 정지 | 원인 미확정 (새로 띄운 앱에서는 0.8초) | 끊김 보강 뒤 재발 시 LOAD 전 STOP | OPEN O103 |
| T13 | 30초 끊김 뒤 다시 붙는 데 60초가 넘음 | pychromecast 14.0.10은 재연결 실패마다 다음 시도 간격을 2·4·8·16·32초로 두 배씩 늘림(`socket_client.mdns_backoff`). `tries`를 늘려도 간격은 그대로 늘어남 | 포기 신호(DISCONNECTED) 뒤 우리가 마지막 IP로 3초 간격 재시도 (`cast_manager._retry_connect`) | D056, 2026-10-23 원본 확인 |
| T14 | 61~90초 사이에 꽂아도 자동으로 다시 연결 안 됨 | 포기 뒤 30초 대기의 자동 연결은 기기 목록이 바뀔 때만 돈다. 목록을 유지(검색 재기동 안 함)하면 기기가 목록에 남아 있어 변화가 없음 | 마지막 IP 재시도 기한을 90초로 늘림 | D059, 2026-10-23 GUI 시험 3차 |
| T15 | 재생 요청이 "start app CC1AD845 timed out after 10.0 s" | TV에 다른 Android 앱이 떠 있으면 기본 수신 앱 실행이 약 18초 걸림. 앱이 뜬 뒤에도 다시 요청하지 않음 | 보류. 시험 전 TV를 홈 화면에 둔다 | O105, 2026-10-23 droptest |
| T16 | 리모컨으로 탐색한 직후 버퍼링이 판정에 셈됨 | TV 리모컨 탐색은 우리 프로그램을 거치지 않아 `탐색:` 로그가 없음 → `--count-buffering`이 10초 제외를 못 함 | 보류. 판정 로그를 볼 때 `HLS 생산 시작` 위치 점프로 구분 | O109, 2026-10-25 exe 시험 |
| T17 | 배포 zip의 exe에 지운 줄 알았던 영상 이름이 남음 | zip을 공개 전 정리 커밋보다 먼저 빌드함. 주석은 exe에 안 들어가지만 docstring은 기본 빌드(최적화 없음)에서 들어감 | 릴리스 직전 마지막 코드 커밋 뒤 다시 빌드하고, exe 안 `core`·`ui` 모듈 문자열을 검색(`PyInstaller.archive.readers.CArchiveReader` → `PYZ.pyz`) | D041, 2026-10-27 릴리스 점검 |

## R§5 환경·도구
- 개발 환경: Windows 11, PowerShell 7, Python 3.15.1 `.venv`(설계 기준 3.11+), PyChromecast 14.0.10, zeroconf 0.151.5, protobuf 7.36.2, PySide6 6.12.0, charset-normalizer 3.5.2 (2026-10-23 확인). PyInstaller 미설치
- 네트워크: PC 유선, Chromecast 5GHz 무선(유선 불가 위치), 같은 서브넷. 방화벽은 기기를 못 찾을 때만 Python 허용 규칙 추가
- 인코더 실측: `h264_amf` (nvenc·qsv 실패)
- 실기기 끊김 시험: PC 랜선을 뽑았다가 다시 꽂는다 (droptest와 달리 실제 끊김). 성공 기준은 D051
- droptest 원리: `sc._force_recon = True; sc.socketpair[1].send(b"x")` — 실제 원격 끊김과 같은 경로. pychromecast 내부 속성이 없으면 "이 버전에서는 끊김 시험 불가"
- 음성 2개 시험 파일 만들기: `ffmpeg -i <mp4> -t 600 -map 0:v -map 0:a -map 0:a -c:v copy -c:a:0 copy -c:a:1 aac -b:a:1 128k -filter:a:1 "volume=0.2" <음성 2개>.mp4`
- 로그 (D070): GUI `logs/castplayer.log`는 옵션 "로그 기록"을 켰을 때만, 실행마다 새로(1MB×3 순환, `castplayer.1.log` 형식), `-v`는 옵션과 무관하게 DEBUG 기록. tools `logs/cast_test_YYYYMMDD_HHMMSS.log`
