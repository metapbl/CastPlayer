"""en 사전. 키는 코드의 한국어 문장 (core/i18n.py)."""

STRINGS: dict[str, str] = {
    # ---- core/cast_manager.py ----
    "{what} 실패: {err}": "{what} failed: {err}",
    "연결된 기기가 없습니다.": "No device is connected.",
    "기기 정보를 찾을 수 없습니다.": "Device information could not be found.",
    "자막 설정 응답 없음": "No response to the subtitle setting",
    "TV가 이 영상을 재생하지 못했습니다.": "The TV could not play this video.",
    "연결 복구 중이라 {what} 명령을 보내지 못했습니다. 잠시 후 다시 시도하세요.":
        "The connection is being restored, so the {what} command was not sent. "
        "Try again in a moment.",
    "연결 실패: {err}": "Connection failed: {err}",
    "재생 요청": "Play request",
    "자막 설정": "Subtitle setting",
    "수신 앱 종료": "Closing the receiver app",
    "내부 오류: {err}": "Internal error: {err}",
    "볼륨 설정": "Volume setting",
    "음소거": "Mute",
    "일시정지": "Pause",
    "재생": "Play",
    "이동": "Seek",
    # ---- core/hls.py, keyframes.py, media_server.py, transcoder.py ----
    "ffmpeg 실행 실패: {err}": "Could not run ffmpeg: {err}",
    "종료 코드 {rc}": "exit code {rc}",
    "키프레임 분석 실패: {err}": "Keyframe analysis failed: {err}",
    "ffprobe 실행 실패: {err}": "Could not run ffprobe: {err}",
    "키프레임 분석 실패 ({reached}/{duration}초에서 중단): {err}":
        "Keyframe analysis failed (stopped at {reached}/{duration} s): {err}",
    "포트 {port}를 열 수 없습니다: {err}": "Could not open port {port}: {err}",
    "재인코딩용 인코더가 없습니다.": "No encoder is available for re-encoding.",
    "ffmpeg 오류: {msg}": "ffmpeg error: {msg}",
    # ---- core/planner.py ----
    "영상 복사": "video copied",
    "영상 재인코딩": "video re-encoded",
    "음성 없음": "no audio",
    "{codec} 코덱 미지원": "{codec} codec not supported",
    "음성 트랙 #{n}이 없습니다.": "There is no audio track #{n}.",
    "영상 트랙이 없습니다.": "There is no video track.",
    "음성 {label} 복사": "audio {label} copied",
    "음성 {label} → AAC 2ch": "audio {label} → AAC 2ch",
    "표시 시각 정보 없음(ctts 누락)": "no presentation timestamps (ctts missing)",
    "컨테이너 변환": "container conversion",
    "HEVC 태그 {tag}→hvc1": "HEVC tag {tag}→hvc1",
    "기본 외 음성 트랙 선택": "non-default audio track selected",
    "H.264 {profile} 미지원": "H.264 {profile} not supported",
    "H.264 레벨 {level} 초과": "H.264 level above {level}",
    "HEVC {profile} 미지원": "HEVC {profile} not supported",
    "HEVC 레벨 {level} 초과": "HEVC level above {level}",
    "4K H.264 한계로 {fps}fps": "{fps} fps due to the 4K H.264 limit",
    # ---- core/player.py ----
    "자막 추출": "Extracting subtitles",
    "전체 길이를 알 수 없어 HLS로 보낼 수 없습니다.":
        "The total length is unknown, so the video cannot be sent as HLS.",
    "사용 가능한 H.264 인코더가 없습니다.": "No H.264 encoder is available.",
    "불러온 파일이 없습니다.": "No file is loaded.",
    "HLS 준비가 되지 않았습니다.": "HLS is not ready.",
    "켜진 자막이 없습니다.": "No subtitle is turned on.",
    "키프레임 분석": "Analyzing keyframes",
    "자막 #{n}이 없습니다.": "There is no subtitle #{n}.",
    "자막 #{n}은 고를 수 없습니다 ({why}).": "Subtitle #{n} cannot be selected ({why}).",
    # ---- core/probe.py, subtitles.py ----
    "내장#{n}": "Embedded #{n}",
    "(기본)": "(default)",
    "(지원 안 함)": "(not supported)",
    "ffprobe 오류": "ffprobe error",
    "ffprobe 출력 해석 실패": "Could not read the ffprobe output",
    "내장": "Embedded ",
    "{n}개": "{n} lines",
    "지원 안 함": "not supported",
    "읽기 실패": "read failed",
    "추출 실패": "extraction failed",
    "비어 있음": "empty",
    # ---- main.py ----
    "{names}을(를) 찾지 못했습니다.\n\n찾아본 곳:\n- {folder}\n- PATH 환경 변수\n\n"
    "PowerShell이나 명령 프롬프트에서 설치할 수 있습니다:\nwinget install Gyan.FFmpeg\n\n"
    "설치한 뒤 CastPlayer를 다시 실행해 주세요.":
        "{names} not found.\n\nLooked in:\n- {folder}\n- the PATH environment variable\n\n"
        "You can install it from PowerShell or Command Prompt:\nwinget install Gyan.FFmpeg\n\n"
        "Run CastPlayer again after installing.",
    "로그 파일을 만들 수 없습니다: {path} ({err})": "Could not create the log file: {path} ({err})",
    "{err}\n\nCastPlayer가 이미 실행 중이거나 다른 프로그램이 포트 {port}를 쓰고 있습니다.\n"
    "config.json의 server_port로 포트를 바꿀 수 있습니다.":
        "{err}\n\nCastPlayer is already running, or another program is using port {port}.\n"
        "You can change the port with server_port in config.json.",
    # ---- ui/dialogs.py ----
    "재생 / 일시정지": "Play / Pause",
    "5초 뒤로 / 앞으로 (연타하면 모아서 한 번에 이동)":
        "Back / forward 5 s (repeated presses are combined into one seek)",
    "볼륨 ±5%": "Volume ±5%",
    "음소거 전환": "Toggle mute",
    "정지 (TV 플레이어 종료)": "Stop (closes the TV player)",
    "파일 열기": "Open file",
    "기기 다시 찾기": "Search for devices again",
    "프로그램 종료": "Quit",
    "Shift+클릭": "Shift+click",
    "자막 싱크 버튼을 0.1초 단위로": "Subtitle sync buttons in 0.1 s steps",
    "단축키 목록": "Keyboard shortcuts",
    "지원 형식": "Supported formats",
    "<b>DIRECT</b>: mp4 + H.264/HEVC(hvc1) + AAC/MP3, 기본 음성 트랙 → 파일 그대로<br>"
    "<b>REMUX</b>: 영상은 지원되지만 컨테이너(mkv, ts, mov 등)·HEVC 태그·음성 코덱이 "
    "맞지 않거나 기본 외 음성 선택 → HLS, 영상 복사<br>"
    "<b>TRANSCODE</b>: 영상 미지원(XviD, H.264 10bit 등)이나 표시 시각 결함 → "
    "HLS, H.264 재인코딩<br><br>"
    "음성: AAC는 복사(HE-AAC·48kHz 초과·6채널 초과는 변환), 나머지는 AAC 2ch로 변환<br>"
    "자막: srt, smi(클래스별), ass/ssa, vtt, 내장 텍스트 자막 → WebVTT<br>"
    "이미지 자막(PGS, VobSub)은 지원 안 함":
        "<b>DIRECT</b>: mp4 + H.264/HEVC(hvc1) + AAC/MP3, default audio track → file as is<br>"
        "<b>REMUX</b>: video is supported but the container (mkv, ts, mov, etc.), HEVC tag or "
        "audio codec does not fit, or a non-default audio track is chosen → HLS, video copied<br>"
        "<b>TRANSCODE</b>: unsupported video (XviD, H.264 10-bit, etc.) or broken timestamps → "
        "HLS, re-encoded to H.264<br><br>"
        "Audio: AAC is copied (HE-AAC, above 48 kHz or above 6 channels is converted), "
        "everything else is converted to AAC 2ch<br>"
        "Subtitles: srt, smi (per class), ass/ssa, vtt, embedded text subtitles → WebVTT<br>"
        "Image subtitles (PGS, VobSub) are not supported",
    "{app} 정보": "About {app}",
    "IP로 기기 추가": "Add device by IP",
    "크롬캐스트 IP 주소:": "Chromecast IP address:",
    "확인 실패": "could not check",
    "인코더: {name}": "Encoder: {name}",
    "올바른 IP 주소가 아닙니다: {ip}": "Not a valid IP address: {ip}",
    "로컬 동영상 → Chromecast 송출": "Local videos → Chromecast",
    "감지 중 또는 없음": "detecting, or none",
    # ---- ui/main_window.py ----
    "미연결": "Not connected",
    "연결 중": "Connecting",
    "연결됨": "Connected",
    "끊김": "Disconnected",
    "파일": "File",
    "영상 그대로": "video as is",
    "자막 싱크 {sign} 0.5초 (Shift+클릭: 0.1초)": "Subtitle sync {sign}0.5 s (Shift+click: 0.1 s)",
    "{ext} 그대로 보냄": "{ext} sent as is",
    "{ext} → HLS 변환": "{ext} → HLS",
    "{ext} → HLS 재인코딩": "{ext} → HLS re-encoded",
    "음성 그대로": "audio as is",
    "음성 AAC 2ch로 변환": "audio converted to AAC 2ch",
    "기기 다시 찾기 (F5)": "Search for devices again (F5)",
    "Ctrl+O · 끌어다 놓아도 됩니다": "Ctrl+O · or drag and drop",
    "{n}초 뒤로": "Back {n} s",
    "재생 / 일시정지 (Space)": "Play / Pause (Space)",
    "{n}초 앞으로": "Forward {n} s",
    "정지 (S) · TV 플레이어 종료": "Stop (S) · closes the TV player",
    "음소거 (M)": "Mute (M)",
    "자막 작게": "Smaller subtitles",
    "자막 크게": "Larger subtitles",
    "끄기": "Off",
    "{n}초": "{n} s",
    "{name}을(를) mDNS로 찾지 못해 {host}로 확인합니다…":
        "{name} was not found with mDNS. Checking {host}…",
    "기기를 찾는 중…": "Searching for devices…",
    "{ip} 확인 중… 목록에 나타나면 [연결]을 누르세요.":
        "Checking {ip}… Press [Connect] when it appears in the list.",
    " — 다시 연결 중…": " — reconnecting…",
    " — {n}초 동안 다시 찾는 중…": " — searching again for {n} s…",
    "동영상 열기": "Open video",
    "재생 완료": "Playback finished",
    "캐시를 비웠습니다.": "The cache was cleared.",
    "종료 중… (정지 → TV 플레이어 종료 → 연결 해제)":
        "Quitting… (stop → close the TV player → disconnect)",
    "음성": "Audio",
    "자막": "Subtitles",
    "크기": "Size",
    "싱크": "Sync",
    "동영상 파일을 여기에 끌어다 놓으세요": "Drag a video file here",
    "먼저 기기를 연결하세요": "Connect a device first",
    "연결 해제": "Disconnect",
    "연결": "Connect",
    "{name}을(를) 찾지 못했습니다.": "{name} was not found.",
    "기기를 먼저 찾으세요 (F5).": "Search for devices first (F5).",
    "다시 연결됨. 끊긴 위치부터 이어 갑니다.": "Reconnected. Resuming from where it stopped.",
    "기기에 다시 연결하지 못했습니다. [연결]을 눌러 주세요.":
        "Could not reconnect to the device. Press [Connect].",
    "파일이 없습니다: {path}": "File not found: {path}",
    "재생 요청을 보냈습니다.": "Play request sent.",
    "불러오기 실패: {msg}": "Loading failed: {msg}",
    "음성 변경 실패: {msg}": "Changing the audio track failed: {msg}",
    "TV에서 플레이어가 종료됨": "The player was closed on the TV",
    "불러오기 실패: {name} ({code})": "Loading failed: {name} ({code})",
    "연결됨. 재생 버튼을 누르면 이어서 재생합니다.": "Connected. Press Play to continue.",
    "동영상": "Videos",
    "모든 파일": "All files",
    "먼저 기기를 연결하세요.": "Connect a device first.",
    "지금 재생 중인 파일을 멈추고 새 파일로 바꾸겠습니까?\n\n{name}":
        "Stop the file that is playing and switch to the new file?\n\n{name}",
    "음성 트랙을 바꿨습니다.": "Audio track changed.",
    "로그 기록 켬": "Logging on",
    "로그 기록 끔": "Logging off",
    "키프레임 분석·자막 추출 캐시를 지우겠습니까?\n(다음에 열 때 다시 만듭니다)":
        "Clear the keyframe and subtitle cache?\n(It is rebuilt the next time a file is opened)",
    "파일을 불러오는 중입니다. 종료하겠습니까?": "A file is loading. Quit anyway?",
    "마지막 기기": "The last device",
    # ---- ui/menus.py ----
    "메뉴": "Menu",
    "파일 열기…": "Open file…",
    "IP로 기기 추가…": "Add device by IP…",
    "기기 연결 해제": "Disconnect device",
    "옵션": "Options",
    "시작 시 마지막 기기 자동 연결": "Connect to the last device at startup",
    "테마": "Theme",
    "로그 기록": "Logging",
    "로그 폴더 열기": "Open log folder",
    "캐시 비우기…": "Clear cache…",
    "정보": "Help",
    "CastPlayer 정보": "About CastPlayer",
    "시스템 설정 따르기": "Use system setting",
    "어둡게": "Dark",
    "밝게": "Light",
}
