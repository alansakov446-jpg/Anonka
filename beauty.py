# -*- coding: utf-8 -*-
"""
Эвристическая оценка "красоты" юзернейма по шкале от 1 до 10.

v2: в основе — РЕАЛЬНАЯ читаемость, а не просто чередование гласных/согласных.
Раньше "whajs" и "dhshu" могли получать 5-6 баллов только потому, что в них
мало повторов — хотя произнести их невозможно. Теперь ключевую роль играют:

 1. Доля гласных в слове — если гласных мало, слово тяжело произнести
    целиком, даже если отдельные буквы не повторяются.
 2. Длина цепочек согласных подряд:
      - одна согласная — нормально,
      - две согласные, но это известное сочетание языка (th, sh, tr, bl…) —
        небольшой штраф,
      - две согласные, но сочетание "искусственное" (js, dh, hs…) —
        заметный штраф,
      - три и более согласных подряд — читать почти невозможно, сильный штраф.

Примеры (что и должно получаться):
  wezaz  — гласных много, кластеров нет            → высокий балл
  lerzu  — гласных много, один небольшой кластер    → хороший балл
  whajs  — гласных мало, кластеры по краям слова    → низкий балл
  dhshu  — гласных мало, кластер из 4 согласных      → минимальный балл
"""

import re

VOWELS = set("aeiouy")

# Устойчивые для языка сочетания согласных — если кластер из них,
# штраф меньше, потому что произнести такое сочетание не так сложно.
KNOWN_CLUSTERS = {
    "th", "sh", "ch", "ph", "wh", "gh", "ck", "ng", "qu",
    "bl", "br", "cl", "cr", "dr", "fl", "fr", "gl", "gr",
    "pl", "pr", "sc", "sk", "sl", "sm", "sn", "sp", "st", "sw", "tr", "tw", "wr",
}


def _readability(name: str) -> float:
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return 0.0

    vowel_ratio = sum(1 for c in letters if c in VOWELS) / len(letters)

    score = 0.0
    if vowel_ratio >= 0.4:
        score += 3.0
    elif vowel_ratio >= 0.3:
        score += 1.5
    elif vowel_ratio >= 0.2:
        score += 0.0
    else:
        score -= 2.5

    i, n = 0, len(name)
    while i < n:
        if name[i].isalpha() and name[i] not in VOWELS:
            j = i
            while j < n and name[j].isalpha() and name[j] not in VOWELS:
                j += 1
            run_len = j - i
            if run_len == 2:
                cluster = name[i:j]
                score -= 0.4 if cluster in KNOWN_CLUSTERS else 1.2
            elif run_len >= 3:
                score -= 1.5 * run_len
            i = j
        else:
            i += 1

    return score


def score_username(username: str) -> int:
    name = username.lower()
    length = len(name)
    score = 3.0

    score += _readability(name)

    if length == 5:
        score += 0.8
    elif length == 6:
        score += 0.5
    elif length == 7:
        score += 0.2

    if re.search(r"(.)\1\1", name):
        score -= 3
    elif re.search(r"(.)\1", name):
        score -= 1

    uniq_ratio = len(set(name)) / length
    if uniq_ratio == 1.0:
        score += 0.5

    if name and name[-1] in VOWELS:
        score += 0.3

    if name == name[::-1] and length > 1:
        score += 2.5

    if _has_sequence(name):
        score += 2.0

    digit_count = sum(c.isdigit() for c in name)
    if 1 <= digit_count <= 2:
        score += 0.3
    elif digit_count > 2:
        score -= 0.8

    return int(max(1, min(10, round(score))))


def _has_sequence(s: str, min_len: int = 3) -> bool:
    for i in range(len(s) - min_len + 1):
        chunk = s[i:i + min_len]
        if chunk.isdigit():
            nums = [int(ch) for ch in chunk]
            if all(nums[j + 1] - nums[j] == 1 for j in range(len(nums) - 1)):
                return True
        elif chunk.isalpha():
            codes = [ord(ch) for ch in chunk]
            if all(codes[j + 1] - codes[j] == 1 for j in range(len(codes) - 1)):
                return True
    return False
