# 썸네일 자동 배치·도움말 창·README GIF (F9, §2.1, D123~D126)
Status: done (2026-11-21) | 시작: 2026-11-21 | 근거: PRD F9, §2.1 README (D123~D128)

목표: 단축키·지원 형식을 쉬운 말의 도움말(F1) 한 창으로 보인다. 파일이 열린 윗칸이 낮으면 썸네일이 왼쪽 고정 폭 칸에, 높으면 글자 아래에 온다. README "스크린샷" 절에는 다크·라이트 작동 장면 GIF 두 개만 있다.
구조:
- `ui/dialogs.py > build_help`, `MODES` — 도움말 창 (D126, D123 대체), `ui/menus.py`, 5개 사전
- `ui/main_window.py > _FilePage` — 높이로 배치를 고름 (D124), `_Cover.left`
- `tools/cast_test.py > make_shots` — `demo-light-en-v2.gif`·`demo-dark-ko-v2.gif` (D125, D129~D131)

## 작업
- [x] 1. 지원 형식 창 표 + 5개 사전 — 확인: 한국어·English 창 캡처를 보고 판단, 자가검사 통과
- [x] 2. 윗칸 자동 배치 — 확인: 자가검사 F9-12·F9-15·F9-17 (옆 칸 폭 160·글자 x 고정, 높이면 위아래, 그림 없으면 글자만)
- [x] 3. GIF 두 개(예시 트랙 영어·한국어)와 README 6개 — 확인: `--shots` 각 0.15MB, 프레임을 보고 판단
- [x] 4. 인수 F9-16 [사람] — 실제 창에서 두 배치와 바뀌는 지점, 지원 형식 창 (2026-11-21 사용자 확인: 배치 4항목 예, 지원 형식 창은 보기 나쁨 → 5)
- [x] 5. 도움말 한 창(F1) — `ui/dialogs.py > build_help`, `ui/menus.py`, 5개 사전, README 6개 단축키 표에 F1 (D126). 확인: 자가검사 F9-20·F10-4, 6개 언어·밝게 캡처(너비 600~830px, 잘림 없음)
- [x] 6. 도움말 창 다듬기 (D127) — 확인: 자가검사 139/139·F10-4, 6개 언어 캡처(너비 619~830px, 잘림 없음)
- [x] 7. 일본어·중국어 화면 글꼴 (D128) — `ui/main_window.py > apply_language_font`, `main.py`. 확인: 자가검사 F10-6, 실제 글꼴 판별(일본어 SimSun+맑은 고딕 → Yu Gothic UI, 중국어 → Microsoft YaHei UI, 한국어 그대로)·캡처
