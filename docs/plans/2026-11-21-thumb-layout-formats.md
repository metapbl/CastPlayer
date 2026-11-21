# 썸네일 자동 배치·지원 형식 창·README GIF (F9, §2.1, D123~D125)
Status: active | 시작: 2026-11-21 | 근거: PRD F9, §2.1 README (D123~D125)

목표: 지원 형식 창을 쉬운 말의 표로 보인다. 파일이 열린 윗칸이 낮으면 썸네일이 왼쪽 고정 폭 칸에, 높으면 글자 아래에 온다. README "스크린샷" 절에는 다크·라이트 작동 장면 GIF 두 개만 있다.
구조:
- `ui/dialogs.py > show_formats`, `FORMATS` — 표 (D123), 5개 사전
- `ui/main_window.py > _FilePage` — 높이로 배치를 고름 (D124), `_Cover.left`
- `tools/cast_test.py > make_shots` — `demo-dark.gif`·`demo-light.gif` (D125)

## 작업
- [x] 1. 지원 형식 창 표 + 5개 사전 — 확인: 한국어·English 창 캡처를 보고 판단, 자가검사 통과
- [x] 2. 윗칸 자동 배치 — 확인: 자가검사 F9-12·F9-15·F9-17 (옆 칸 폭 160·글자 x 고정, 높이면 위아래, 그림 없으면 글자만)
- [x] 3. GIF 두 개(예시 트랙 영어·한국어)와 README 6개 — 확인: `--shots` 각 0.15MB, 프레임을 보고 판단
- [ ] 4. 인수 F9-16 [사람] — 실제 창에서 두 배치와 바뀌는 지점, 지원 형식 창이 읽기 쉬운지
