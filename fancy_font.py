# -*- coding: utf-8 -*-
"""
Конвертеры обычного текста в "красивые" unicode-шрифты для оформления бота
(заголовки, подписи, кнопки) — НИКОГДА не применяются к самим юзернеймам,
т.к. настоящий юзернейм Telegram может состоять только из a-z, 0-9 и "_".

Есть два вида стилизации:

1. fancy_bold / fancy_italic — математический alphanumeric-блок unicode
   (это НЕ обычный bold/italic из форматирования Telegram, а отдельные
   символы). Аккуратный, всегда читаемый стиль.

2. fancy_style — "дикий" стиль на похожих по начертанию буквах из
   кириллицы, греческого алфавита и IPA-расширений (например латинская
   "a" заменяется на кириллическую "а", которая выглядит идентично).
   Специально взяты буквы из ШИРОКО поддерживаемых unicode-блоков
   (кириллица, греческий, основные IPA-расширения) — они корректно
   отображаются практически на любом телефоне. Экзотические блоки типа
   коптского, чероки или огама намеренно не использованы: на части
   устройств такие символы показываются пустыми квадratиками "тофу"
   вместо букв, а нам нужно, чтобы бот было видно везде одинаково красиво.
"""

_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_LOWER = "abcdefghijklmnopqrstuvwxyz"
_DIGITS = "0123456789"


def _build_map(upper_start: int, lower_start: int, digit_start: int | None = None):
    mapping = {}
    for i, ch in enumerate(_UPPER):
        mapping[ch] = chr(upper_start + i)
    for i, ch in enumerate(_LOWER):
        mapping[ch] = chr(lower_start + i)
    if digit_start is not None:
        for i, ch in enumerate(_DIGITS):
            mapping[ch] = chr(digit_start + i)
    return mapping


# Математический Sans-Serif Bold
_BOLD_SANS = _build_map(0x1D5D4, 0x1D5EE, 0x1D7EC)

# Математический Sans-Serif Italic
_ITALIC_SANS = _build_map(0x1D608, 0x1D622)


def _convert(text: str, table: dict) -> str:
    return "".join(table.get(ch, ch) for ch in text)


def fancy_bold(text: str) -> str:
    return _convert(text, _BOLD_SANS)


def fancy_italic(text: str) -> str:
    return _convert(text, _ITALIC_SANS)


# --- "Дикий" confusable-стиль (кириллица/греческий/IPA) ---------------------

_STYLE_LOWER = {
    "a": "а", "b": "ϐ", "c": "с", "d": "ԁ", "e": "е", "f": "ƒ", "g": "ɡ",
    "h": "һ", "i": "і", "j": "ј", "k": "к", "l": "ⅼ", "m": "м", "n": "ɴ",
    "o": "о", "p": "р", "q": "ԛ", "r": "ʀ", "s": "ѕ", "t": "τ", "u": "υ",
    "v": "ν", "w": "ѡ", "x": "х", "y": "у", "z": "ᴢ",
}

_STYLE_UPPER = {
    "a": "А", "b": "В", "c": "С", "d": "D", "e": "Е", "f": "F", "g": "G",
    "h": "Н", "i": "I", "j": "J", "k": "К", "l": "L", "m": "М", "n": "N",
    "o": "О", "p": "Р", "q": "Q", "r": "R", "s": "S", "t": "Т", "u": "U",
    "v": "V", "w": "W", "x": "Х", "y": "У", "z": "Z",
}


def fancy_style(text: str) -> str:
    """"Дикий" стиль на похожих буквах — для самых заметных заголовков."""
    result = []
    for ch in text:
        if ch in _STYLE_UPPER:
            result.append(_STYLE_UPPER[ch])
        elif ch.lower() in _STYLE_LOWER and ch.islower():
            result.append(_STYLE_LOWER[ch])
        else:
            result.append(ch)
    return "".join(result)


_CIRCLED_DIGITS = {
    0: "⓪", 1: "①", 2: "②", 3: "③", 4: "④",
    5: "⑤", 6: "⑥", 7: "⑦", 8: "⑧", 9: "⑨", 10: "⑩",
}


def circled_number(n: int) -> str:
    return _CIRCLED_DIGITS.get(n, str(n))


def beauty_bar(score: int) -> str:
    score = max(1, min(10, score))
    return "★" * score + "☆" * (10 - score)
