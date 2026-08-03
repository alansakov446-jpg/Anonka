# -*- coding: utf-8 -*-
"""
Генерация кандидатов юзернеймов под заданные фильтры:
 - длина: 5 / 6 / 7 / любая из 5-7
 - режим цифр:
     no_digits   — только буквы
     with_digits — буквы + 1-2 "обычные" цифры где-то внутри
     leet        — буквы с заменой части символов на похожие цифры (a->4, e->3, i->1, o->0 и т.д.)

Юзернеймы генерируются не абсолютно случайным набором букв, а по принципу
чередования согласная/гласная — так среди находок будет больше
произносимых и приятных на вид вариантов, а не наборов согласных подряд.
"""

import random
import string

from beauty import KNOWN_CLUSTERS

VOWELS = "aeiouy"
CONSONANTS = "".join(c for c in string.ascii_lowercase if c not in VOWELS)

# сгруппированные по первой букве известные сочетания — используем их,
# когда решаем поставить две согласные подряд, чтобы получалось произносимо
_CLUSTERS_BY_FIRST = {}
for _cl in KNOWN_CLUSTERS:
    _CLUSTERS_BY_FIRST.setdefault(_cl[0], []).append(_cl)

LEET_MAP = {
    "a": "4",
    "e": "3",
    "i": "1",
    "o": "0",
    "s": "5",
    "t": "7",
    "b": "8",
    "g": "9",
}

LENGTH_LABELS = {
    "5": "5 символов",
    "6": "6 символов",
    "7": "7 символов",
    "any": "5-7 символов",
}

DIGIT_MODE_LABELS = {
    "no_digits": "без цифр",
    "with_digits": "с цифрами",
    "leet": "замена букв на цифры",
}


def _syllable_word(length: int) -> str:
    chars = []
    use_consonant = random.random() < 0.75  # чаще начинаем с согласной — звучит естественнее
    while len(chars) < length:
        if use_consonant:
            # иногда ставим готовое, реально произносимое сочетание согласных
            # (th, sh, tr, bl...) вместо одной случайной согласной
            if random.random() < 0.15 and length - len(chars) >= 3:
                first = random.choice(list(_CLUSTERS_BY_FIRST.keys()))
                cluster = random.choice(_CLUSTERS_BY_FIRST[first])
                chars.extend(list(cluster))
            else:
                chars.append(random.choice(CONSONANTS))
        else:
            chars.append(random.choice(VOWELS))
        use_consonant = not use_consonant
    return "".join(chars[:length])


def _is_valid_username(name: str) -> bool:
    if not (5 <= len(name) <= 32):
        return False
    if not name[0].isalpha():
        return False
    if name.endswith("_"):
        return False
    if "__" in name:
        return False
    return all(c.isalnum() or c == "_" for c in name)


def _pick_length(length_choice: str) -> int:
    if length_choice == "any":
        return random.choice([5, 6, 7])
    return int(length_choice)


def generate_username(length_choice: str, digit_mode: str) -> str:
    length = _pick_length(length_choice)

    if digit_mode == "no_digits":
        base = _syllable_word(length)
        candidate = base

    elif digit_mode == "with_digits":
        # цифры входят в итоговую длину, а не добавляются сверх неё
        digits_to_insert = min(random.randint(1, 2), length - 4)
        digits_to_insert = max(digits_to_insert, 1)
        base = _syllable_word(length - digits_to_insert)
        chars = list(base)
        for _ in range(digits_to_insert):
            # не вставляем цифру на первую позицию — юзернейм должен начинаться с буквы
            pos = random.randint(1, len(chars))
            chars.insert(pos, random.choice(string.digits))
        candidate = "".join(chars)

    elif digit_mode == "leet":
        base = _syllable_word(length)
        chars = list(base)
        replaceable_positions = [
            i for i, c in enumerate(chars) if c in LEET_MAP and i != 0
        ]
        random.shuffle(replaceable_positions)
        n_replace = min(len(replaceable_positions), random.randint(1, 3))
        for idx in replaceable_positions[:n_replace]:
            chars[idx] = LEET_MAP[chars[idx]]
        candidate = "".join(chars)

    else:
        candidate = base

    if not _is_valid_username(candidate):
        return generate_username(length_choice, digit_mode)

    return candidate
