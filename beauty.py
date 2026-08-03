# -*- coding: utf-8 -*-
"""
beauty.py — оценка красоты/читаемости юзернейма 1–10 и форматирование вывода.
"""
import re
from typing import Optional, Dict, Any, Tuple, List

VOWELS = set("aeiouy")
CONSONANTS = set("bcdfghjklmnpqrstvwxz")
LEET = {'o': '0', 'i': '1', 'l': '1', 'e': '3', 'a': '4', 's': '5', 't': '7', 'b': '8', 'g': '9'}

# реально произносимые диграфы/триграфы английского — используются генератором
KNOWN_CLUSTERS = (
    "th","sh","ch","ph","wh","tr","pl","br","bl","dr","fl","gr","pr","st",
    "sp","sk","sn","sm","kl","kr","fr","sw","gl","sl","cl","cr","tw","qu",
)

# зарезервированные/служебные юзернеймы ТГ (не могут быть зарегистрированы)
RESERVED = {
    "telegram", "support", "bot", "bots", "api", "admin", "administrator",
    "root", "staff", "official", "channel", "group", "chat", "user",
    "users", "username", "usernames", "login", "logout", "signin",
    "signup", "register", "auth", "authentication", "security", "settings",
    "profile", "account", "accounts", "premium", "paid", "free",
    "wallet", "pay", "payment", "store", "shop", "gift", "gifts",
    "donate", "donation", "web", "www", "http", "https", "ftp",
    "sticker", "stickers", "gif", "gifs", "theme", "themes", "wallpaper",
    "emoji", "emojis", "verify", "verified", "help", "faq", "terms",
    "privacy", "abuse", "dmca", "spam", "scam", "news", "press",
    "team", "jobs", "career", "careers", "about", "contact",
    "contacts", "feedback", "beta", "alpha", "test", "testing",
    "dev", "developer", "developers", "download", "updates",
    "ios", "android", "windows", "macos", "linux", "desktop",
    "mobile", "webk", "webz", "tdlib", "botfather", "stickerbot",
    "gifbot", "pdfbot", "like", "share", "comment", "comments",
    "telegramus", "durov", "pavel", "nick", "nickname", "nicknames",
    "me", "you", "it", "he", "she", "we", "they", "tele", "gram",
    "telegr", "tme", "fragment", "ton", "nft", "auction", "auctions",
    "sold", "buy", "sell", "sale", "new", "home", "menu", "search",
    "start", "stop", "open", "close", "ok", "yes", "no", "cancel",
}


def is_reserved(username: str) -> bool:
    u = username.lower().strip().lstrip("@")
    if u in RESERVED:
        return True
    # запрещённые паттерны
    if re.fullmatch(r"[a-z]*telegram[a-z]*", u):
        return True
    if u.startswith("tgm") or u.startswith("tg_"):
        return True
    if u.endswith("bot") and len(u) < 8:
        return True
    return False


def leet_variants(username: str) -> List[str]:
    """Генерирует leet-замены букв на похожие цифры для фильтра 'заменять буквы цифрами'."""
    out = {username}
    # одна замена
    for i, ch in enumerate(username):
        if ch in LEET:
            out.add(username[:i] + LEET[ch] + username[i+1:])
    # две замены
    for i, ch1 in enumerate(username):
        if ch1 not in LEET:
            continue
        for j, ch2 in enumerate(username[i+1:], start=i+1):
            if ch2 in LEET:
                candidate = username[:i] + LEET[ch1] + username[i+1:j] + LEET[ch2] + username[j+1:]
                out.add(candidate)
    return list(out)


def evaluate_username_score(username: str, calib_weights: Optional[dict] = None) -> float:
    """
    Оценка красоты 1.0 – 10.0:
      * база 6.0
      * длина — короткие лучше
      * штраф за 3+ согласных подряд («каша» из букв)
      * штраф за 3+ гласных подряд (менее читаемо)
      * бонус за ритм — чередование гласн./согл. (wezaz)
      * бонус за произносимые диграфы (th, sh, ch, tr, pl, br, bl, dr, fl, gr, kl, pr, st, sp, sk, sn, sm)
      * штраф за цифры / подчёркивания
      * небольшой бонус за палиндромы и отсутствие повторов
    """
    if calib_weights is None:
        calib_weights = {}
    vw = calib_weights.get("vowel_weight", 1.0)
    cp = calib_weights.get("consonant_penalty", 1.0)
    rb = calib_weights.get("rhythm_bonus", 1.0)
    dp = calib_weights.get("digit_penalty", 1.0)
    up = calib_weights.get("underscore_penalty", 1.0)

    score = 6.0
    u = username.lower()

    # ------- длина -------
    L = len(u)
    if L <= 3:
        score += 3.0
    elif L == 4:
        score += 2.2
    elif L == 5:
        score += 1.4
    elif L == 6:
        score += 0.7
    elif L == 7:
        score += 0.2
    elif L >= 10:
        score -= 1.5

    # ------- штрафы за кластеры согласных -------
    for cluster in re.findall(r"[bcdfghjklmnpqrstvwxz]+", u):
        clen = len(cluster)
        if clen >= 5:
            score -= 3.0 * cp
        elif clen == 4:
            score -= 2.2 * cp
        elif clen == 3:
            score -= 1.2 * cp
        # ещё сильнее штрафуем неестественные стыки
        if re.search(r"[qjxv]{2,}", cluster):
            score -= 1.0 * cp

    # ------- кластеры гласных -------
    for cluster in re.findall(r"[aeiouy]+", u):
        if len(cluster) >= 4:
            score -= 1.2 * vw
        elif len(cluster) == 3:
            score -= 0.5 * vw

    # ------- ритм (чередование гласная-согласная) -------
    rhythm_runs = re.findall(r"((?:[aeiouy][bcdfghjklmnpqrstvwxz]){2,})", u)
    if rhythm_runs:
        longest = max(len(r)//2 for r in rhythm_runs)
        if longest >= 4:
            score += 2.0 * rb
        elif longest == 3:
            score += 1.4 * rb
        elif longest == 2:
            score += 0.7 * rb

    # ------- произносимые диграфы -------
    nice_digraphs = ("th","sh","ch","ph","tr","pl","br","bl","dr","fl","gr","pr","st","sp","sk","sn","sm","kl","kr","fr","sw")
    d_count = sum(u.count(d) for d in nice_digraphs)
    score += min(d_count * 0.3, 1.0) * rb

    # ------- гласные/согласные баланс -------
    letters = [c for c in u if c.isalpha()]
    if letters:
        vratio = sum(1 for c in letters if c in VOWELS) / len(letters)
        if 0.35 <= vratio <= 0.55:
            score += 0.6 * vw
        elif vratio < 0.2 or vratio > 0.8:
            score -= 0.8 * vw

    # ------- штраф за цифры/подчёркивания -------
    digits = sum(1 for c in u if c.isdigit())
    if digits:
        score -= (0.7 + 0.5 * (digits - 1)) * dp
        # цифры в начале/конце — немного грубее
        if u[0].isdigit():
            score -= 0.2 * dp
        if u[-1].isdigit():
            score -= 0.2 * dp

    underscores = u.count("_")
    if underscores:
        score -= 0.8 * up + 0.4 * max(underscores - 1, 0) * up
        if u.startswith("_") or u.endswith("_"):
            score -= 0.3 * up

    # ------- бонусы -------
    alpha_only = re.sub(r"[^a-z]", "", u)
    if alpha_only == alpha_only[::-1] and 4 <= len(alpha_only) <= 7:
        score += 0.6  # палиндром
    if re.search(r"(.)\1{2,}", u):
        score -= 0.6  # три одинаковых буквы подряд
    if re.fullmatch(r"[a-z]{4,7}", u):
        score += 0.4  # без цифр/подчёркиваний — аккуратно

    return max(1.0, min(10.0, round(score, 1)))


def score_username(username: str, calib_weights: Optional[dict] = None) -> float:
    """Синоним, чтобы не сломать импорты из старого bot.py."""
    return evaluate_username_score(username, calib_weights)


def format_username_output(username: str, score: float, settings: dict) -> str:
    if settings.get("clean_output"):
        return f"@{username}"
    if settings.get("no_mono"):
        return f"@{username} — {score}/10\n🔗 https://fragment.com/username/{username}"
    return (
        f"✨ <code>@{username}</code> — <b>{score}/10</b>\n"
        f"🔗 https://fragment.com/username/{username}"
    )


def build_calibration_weights(samples: List[Tuple[str, float]]) -> Dict[str, Any]:
    """
    Простая подгонка весов под пользователя:
    если он ставит высокие оценки коротким без цифр — увеличиваем бонусы,
    если прощает кашу согласных — снижаем штраф.
    """
    if not samples:
        return {
            "vowel_weight": 1.0, "consonant_penalty": 1.0, "rhythm_bonus": 1.0,
            "digit_penalty": 1.0, "underscore_penalty": 1.0,
        }
    avg = sum(s for _, s in samples) / len(samples)
    short = [s for u, s in samples if len(u) <= 5]
    long_ = [s for u, s in samples if len(u) >= 8]
    no_digits = [s for u, s in samples if not re.search(r"\d", u)]
    with_digits = [s for u, s in samples if re.search(r"\d", u)]
    cash = [s for u, s in samples if re.search(r"[bcdfghjklmnpqrstvwxz]{3,}", u)]

    def avg_of(lst, fallback):
        return (sum(lst) / len(lst)) if lst else fallback

    digit_penalty = 1.0
    if no_digits and with_digits:
        diff = avg_of(no_digits, avg) - avg_of(with_digits, avg)
        digit_penalty = max(0.3, min(2.0, 1.0 - diff / 3))

    consonant_penalty = 1.0
    if cash:
        diff = avg - avg_of(cash, avg)
        consonant_penalty = max(0.3, min(2.5, 1.0 + diff / 3))

    rhythm_bonus = 1.0
    if short:
        rhythm_bonus = max(0.5, min(2.0, avg_of(short, avg) / 8))

    return {
        "vowel_weight": 1.0,
        "consonant_penalty": round(consonant_penalty, 2),
        "rhythm_bonus": round(rhythm_bonus, 2),
        "digit_penalty": round(digit_penalty, 2),
        "underscore_penalty": 1.0,
    }
