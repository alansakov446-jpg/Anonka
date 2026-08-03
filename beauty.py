import re
from typing import Optional

def evaluate_username_score(username: str, calib_weights: Optional[dict] = None) -> float:
    """
    Расчет красоты/читаемости юзернейма по шкале 1.0 - 10.0
    """
    if calib_weights is None:
        calib_weights = {"vowel_weight": 1.0, "consonant_penalty": 1.0, "rhythm_bonus": 1.0}

    score = 7.0
    u = username.lower()

    # 1. Длина
    if len(u) <= 4:
        score += 2.5
    elif len(u) <= 6:
        score += 1.0
    elif len(u) >= 10:
        score -= 1.5

    # 2. Штраф за 3+ согласных подряд (например, "hdkjl")
    consonant_pattern = r'[bcdfghjklmnpqrstvwxyz]{3,}'
    if re.search(consonant_pattern, u):
        score -= 2.0 * calib_weights.get("consonant_penalty", 1.0)

    # 3. Бонус за ритм (чередование гласная-согласная: "wezaz", "lerzu")
    rhythm_pattern = r'([aeiouy][bcdfghjklmnpqrstvwxz]){2,}'
    if re.search(rhythm_pattern, u):
        score += 1.5 * calib_weights.get("rhythm_bonus", 1.0)

    # 4. Штраф за цифры и подчеркивания
    if re.search(r'\d', u):
        score -= 1.0
    if '_' in u:
        score -= 0.5

    return max(1.0, min(10.0, round(score, 1)))
