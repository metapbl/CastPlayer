# SSL 소켓 동시 쓰기 막기 (O111)
상태: active | 시작: 2026-11-02 | 근거: OPEN O111, R§4 T6, D004

목표: pychromecast 소켓에 두 스레드(`cast-worker`와 pychromecast 소켓 스레드)가 동시에 쓰지 않는다. 빠른 연속 탐색을 해도 프로그램이 traceback 없이 꺼지지 않는다.
조사 결과(2026-11-02, TV 없이 로컬 TLS, 저장소 밖 임시 스크립트):
- pychromecast 14.0.10 `SocketClient.send_message`가 잠금 없이 `self.socket.sendall()`을 부른다. 소켓에 쓰는 곳은 여기 한 곳뿐이다 (하트비트 ping·pong, GET_STATUS, 우리 명령 모두 이 함수를 거침)
- 쓰기 2 + 읽기 1을 잠금 없이 → 5번 중 3번 `Windows fatal exception: access violation`으로 꺼짐 (O111 증상). 잠금을 걸면 오류 0
- 쓰기 1 + 읽기 1 → 꺼지지는 않고 `bad record mac` 등 통신 깨짐 (O106·T6 쪽). 이번 범위 밖 (아래 자가 검토)
구조:
- `core/cast_manager.py` — 모듈을 불러올 때 `SocketClient.send_message`를 프로세스 공용 `threading.RLock`으로 감싼다 (`_ensure_channel_connected`가 안에서 다시 `send_message`를 불러 RLock). 기기는 한 번에 하나라 공용 잠금으로 충분
- `tools/cast_test.py` — 자가검사 1개: 감싼 `send_message`를 대역 소켓 클라이언트로 두 스레드에서 동시에 부르고, 대역 `sendall`이 겹친 횟수를 센다
- `docs/REFERENCE.md` — R§4 함정 대장에 T19(동시 쓰기 → 강제 종료), R§5에 pychromecast 내부 의존(`send_message` 감싸기) 추가
전역 제약:
- 작업마다 `--selftest` 전부 통과, 전체 15초 이내 (D064, D071). 편집 때 ruff·pyright 통과 (D063, D068)
- 테스트 코드는 `tools/cast_test.py`에만 (D031). core에서 Qt import 금지 (D003)
- faulthandler는 코드에 넣지 않고 실기기 시험 때 `python -X faulthandler`로 켠다 (같은 효과, 코드 변경 없음). exe(창 전용, 콘솔 없음)에서는 크래시 단서가 남지 않음 — 다시 꺼지는 일이 생기면 그때 넣는다

## 작업
- [x] 1. 실패하는 자가검사 먼저 — `O111 → send_message 동시 호출 → sendall 겹침 0`. 대역: `stop`(Event)·`connecting=False`·`_force_recon=False`·`_ensure_channel_connected`(아무것도 안 함)·`_gen_request_id`·`logger`·`heartbeat_controller.logger`·`socket.sendall`(들어오면 카운터 +1, 0.01초 쉬고 −1, 최대값 기록). 두 스레드가 20번씩 호출 — `tools/cast_test.py > _manager_cases` 근처
  - 확인: `--selftest --log` → 이 항목만 실패(겹침 > 0), 나머지 통과
  - 결과: 72개 중 71개 통과, 이 항목만 "동시에 2개"로 실패
- [x] 2. 잠금 — `core/cast_manager.py`에 감싸기 몇 줄 (원래 함수는 `functools.wraps`로 보존, 반환값·예외 그대로)
  - 확인: `--selftest --log` 전부 통과, `pyright` 0개. 1번 항목을 3번 연속 실행해도 통과
  - 결과: 3번 연속 72개 전부 통과("동시에 1개"), ruff·pyright 0개
- [x] 3. 문서 — REFERENCE T19·R§5, OPEN O111 → 해결됨(실기기 결과 뒤), DECISIONS에 새 결정(라이브러리 함수 감싸기, faulthandler는 `-X`로)
  - 확인: 문서에 실제 IP·기기 이름·경로·파일 이름 없음 (D041)
  - 결과: T19·R§5 2줄·D073 추가, O111은 조사 결과만 적고 열어 둠(실기기 뒤 해결됨)
- [ ] 4. 인수 확인
  - 확인: 전체 테스트 통과, 15초 이내
  - 자동 결과(2026-11-02): 72개 통과, 약 14초(프로세스 시작 포함)
  - 실기기 (사용자, 실행 전 확인, 로그 기록 켬): `.venv\Scripts\python -X faulthandler main.py -v`
    1. REMUX 파일 재생 중 → 키를 빠르게 연타하고, 탐색 바를 다시 불러오는 중에 여러 번 클릭 (O111 때처럼 5초 안에 4번 이상, 3회 반복) → 프로그램이 꺼지지 않음
    2. 1의 터미널에 `Windows fatal exception`이 없음. 로그에 `Error writing to socket`이 없음 (있으면 줄을 알려 주세요)
    3. 탐색이 끝나면 마지막으로 고른 위치에서 재생됨
    4. 10분 넘게 재생을 그대로 둠 → 끊김·멈춤 없음 (잠금 때문에 하트비트가 늦어지지 않는지)

## 자가 검토
- PRD 기능 누락: 해당 없음 (안정성 수정, 인수 기준 변경 없음)
- 범위 밖: 읽기·쓰기 겹침(O106·T6의 통신 깨짐). 읽기까지 잠그면 소켓 스레드가 `recv` 중에 우리 명령을 막거나 그 반대가 생겨, 설계를 따로 봐야 함. 실기기 2에서 `Error writing`이 계속 나오면 새 Q로 묻는다
- 위험: 잠금을 잡은 채 `sendall`이 오래 막히면(네트워크가 막힘) 다른 쪽 쓰기도 기다림. 지금도 한 소켓이라 어차피 못 쓰는 상황이고, 명령 시간 제한(`CMD_TIMEOUT`)은 응답 대기라 그대로 동작
- pychromecast를 올리면 `send_message` 서명·내부 속성이 바뀌는지 확인 (R§5에 적음, droptest와 같은 부류)
- 순서 의존: 1 → 2 (빨강 먼저), 3·4는 2 뒤
