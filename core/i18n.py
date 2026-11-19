"""화면 언어 (F10, D084). 키는 코드의 한국어 문장, 언어마다 core/lang/{코드}.py의 STRINGS.

tr()은 글자를 보여 주는 순간에 부른다. 모듈 상수 안에서 부르면 언어를 바꿔도 그대로 남는다 (D085).
"""
from __future__ import annotations

from .lang import en, es, ja, ru, zh_CN   # 정적 import: PyInstaller가 찾을 수 있게

# 코드 → 그 언어로 쓴 이름 (메뉴 순서, D079)
LANGUAGES = {"en": "English", "ko": "한국어", "zh_CN": "简体中文", "ja": "日本語",
             "es": "Español", "ru": "Русский"}
_TABLES: dict[str, dict[str, str]] = {"en": en.STRINGS, "zh_CN": zh_CN.STRINGS, "ja": ja.STRINGS,
                                      "es": es.STRINGS, "ru": ru.STRINGS}
_lang = "ko"


def tr(key: str, **kw: object) -> str:
    """현재 언어의 문장. 사전에 없으면 키(한국어) 그대로. {이름}은 kw로 채운다."""
    text = _TABLES.get(_lang, {}).get(key, key)
    return text.format(**kw) if kw else text


def N_(key: str) -> str:
    """번역 키 표시만 한다 (상수용). 보여 줄 때 tr()로 바꾼다. 키 검사기가 tr()처럼 읽는다."""
    return key


def set_language(code: str) -> None:
    global _lang
    _lang = code if code in LANGUAGES else "en"


def language() -> str:
    return _lang


def startup_language(setting: str, ui_langs: list[str]) -> str:
    """옵션 값(system 또는 언어 코드) → 쓸 언어. system이면 Windows 표시 언어를 따른다 (D080)."""
    return pick_language(ui_langs) if setting == "system" else setting


def pick_language(ui_langs: list[str]) -> str:
    """Windows 표시 언어 목록(BCP 47, 선호순) → 지원하는 첫 언어, 없으면 en. 중국어는 간체만 (D086)."""
    for tag in ui_langs:
        parts = tag.replace("_", "-").lower().split("-")
        if parts[0] == "zh":
            if "hant" in parts or parts[-1] in ("tw", "hk", "mo"):
                continue
            return "zh_CN"
        if parts[0] in LANGUAGES:
            return parts[0]
    return "en"
