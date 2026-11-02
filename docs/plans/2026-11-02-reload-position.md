# 다시 불러오는 동안 위치 0 막기
상태: active | 시작: 2026-11-02 | 근거: 2026-11-02 실기기 시험 중 발견 (사용자), PRD F3·F5-3

목표: 자막 싱크·음성 변경 등으로 다시 불러오는 동안에도 위치 표시와 좌우키 탐색 기준이 불러오기 시작 위치를 유지한다 (0:00으로 튀지 않음).
원인 (`castplayer.log` 10:32:47~50): LOAD 뒤 TV가 이전 세션 IDLE(위치 0) → 새 세션 BUFFERING(위치 0)을 약 2.6초 보낸 뒤에야 시작 위치를 보고한다. `CastManager.position()`과 상태 신호가 이 0을 그대로 내보내 `ui/main_window.py > _nudge`가 0을 기준으로 탐색을 계산한다.
구조:
- `core/cast_manager.py` — `_do_play`가 LOAD를 보낼 때 (요청, 이전 세션 번호)를 기억. 새 세션이 위치를 보고(위치 > 0 또는 PLAYING/PAUSED)할 때까지 `position()`과 `PlaybackState.position`은 요청 시작 위치. 새 세션이 안 생기고 끝나면(시간 초과·실패·연결 변경) 바로 해제
- `tools/cast_test.py` — 자가검사 1개 (`_manager_cases`)
전역 제약: `--selftest` 전부 통과·15초 이내, ruff·pyright 통과 (D063·D064·D068·D071). 테스트는 `tools/cast_test.py`만 (D031)

## 작업
- [x] 1. 실패하는 자가검사 — 2173.6초에서 다시 불러오기: 가짜 TV가 이전 세션 IDLE 0 → 새 세션 BUFFERING 0 → 새 세션 BUFFERING 2173.6 → PLAYING 2174.0을 보냄. 각 단계의 `position()`과 상태 신호 위치가 2173.6, 2173.6, 2173.6, 2174.0
  - 확인: `--selftest --log` → 이 항목만 실패
  - 결과: 73개 중 72개, 이 항목만 실패 — (위치, 상태 신호) 0.0, 0.0, 2173.6, 2174.0 (실기기 로그와 같은 순서)
- [x] 2. 고침 — 확인: `--selftest --log` 전부 통과, 3번 연속, `pyright` 0개
  - 결과: 3번 연속 73개 전부 통과, ruff·pyright 0개
- [x] 3. 문서·커밋 — REFERENCE 함정 대장에 한 줄
- [ ] 4. 실기기 (사용자, `.venv\Scripts\python -X faulthandler main.py -v`, 로그 기록 켬) — O111 계획 작업 4의 1번 재시험과 함께
    1. 재생 중 자막 싱크를 바꿈 → 위치 표시가 0:00으로 튀지 않음
    2. 자막 싱크를 바꾼 직후(다시 불러오는 중) 좌우키 여러 번 → 원래 위치 근처로 이동
    3. 화살표 키를 1초에 2~3번씩 연타, 다시 불러오는 중 탐색 바 여러 번 클릭 (3회 반복) → 프로그램이 꺼지지 않고, 로그에 `Error writing`·`Windows fatal exception` 없음

## 자가 검토
- 위치를 쓰는 곳: UI 표시·`_nudge`·`_on_poll`, `player._reload_for_subtitle`, 복구 뒤 다시 불러오기, 끊긴 위치 기록 — 모두 `position()`이나 상태 신호를 거치므로 한 곳 수정으로 덮음
- 처음 재생(시작 0)은 유지 값도 0이라 동작 변화 없음
