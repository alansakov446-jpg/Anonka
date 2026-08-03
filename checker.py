# -*- coding: utf-8 -*-
"""
Проверка занятости юзернейма.

v3 — ВАЖНОЕ ИЗМЕНЕНИЕ: раньше основная проверка шла через скрейпинг
t.me и fragment.com. Это ломалось на хостингах с ограниченным доступом
в интернет (например, бесплатный тариф PythonAnywhere пускает запросы
только на сайты из его собственного allow-list, а t.me и fragment.com
туда не входят) — обе проверки возвращали "не удалось определить", и
по прежней логике юз в таком случае никогда не показывался. Отсюда
баг "проверено много, найдено 0".

Теперь основная проверка — официальный Telegram Bot API (`getChat`).
Он использует ровно тот же api.telegram.org, с которым бот и так уже
обязан уметь работать (иначе он бы не отвечал на сообщения вообще) —
поэтому эта проверка работает на любом хостинге без дополнительной
настройки прокси/whitelist. Плюс это официальный API, а не парсинг
чужой HTML-вёрстки, которая может измениться в любой момент.

Fragment.com оставлен как ДОПОЛНИТЕЛЬНАЯ проверка — если он доступен,
используется, чтобы отсеять юзы, прямо сейчас выставленные на продажу.
Но если Fragment недоступен (как на PythonAnywhere free) — это больше
не блокирует находки, чекер просто полагается на официальный Bot API.
"""

import asyncio
import re
import functools

import aiohttp
import cloudscraper

from config import BOT_TOKEN, PROXY_URL

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {"User-Agent": USER_AGENT}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=10)

# один cloudscraper на процесс — пересоздавать его на каждый запрос дорого
_scraper = cloudscraper.create_scraper(browser={"custom": USER_AGENT})

_CHALLENGE_MARKERS = (
    "just a moment",
    "checking your browser",
    "cf-browser-verification",
    "attention required",
    "cf-chl-",
    "enable javascript and cookies",
)

_SALE_MARKERS_RE = re.compile(
    r"(current bid|place a bid|buy now|starting price|min\.\s*bid|"
    r"auction ends|highest bid|sold for|\d[\d,]*\s*ton\b|\$\s?\d)",
    re.IGNORECASE,
)


def _looks_like_challenge(html: str) -> bool:
    lowered = html.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


async def _check_via_bot_api(session: aiohttp.ClientSession, username: str) -> bool | None:
    """
    Официальная проверка через Telegram Bot API (getChat) — основной,
    самый надёжный источник. Работает на любом хостинге, где вообще
    может работать сам бот.

    True  — Telegram не знает такой чат (юз похоже свободен)
    False — юз занят активным пользователем/каналом/группой/ботом
    None  — не удалось определить (сетевая ошибка, лимиты и т.п.)
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChat"
    try:
        async with session.get(
            url,
            params={"chat_id": f"@{username}"},
            timeout=REQUEST_TIMEOUT,
            proxy=PROXY_URL,
        ) as resp:
            data = await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None

    if data.get("ok"):
        return False

    description = (data.get("description") or "").lower()
    if "chat not found" in description:
        return True
    if "too many requests" in description or "flood" in description:
        return None

    return None


# Статистика доступности Fragment с текущего хостинга — чтобы бот мог
# честно показать пользователю "Fragment: доступен / недоступен",
# а не молчать об этом.
_fragment_stats = {"total": 0, "reachable": 0}


def get_fragment_stats() -> dict:
    return dict(_fragment_stats)


def _fetch_fragment_sync(username: str):
    """Синхронный запрос через cloudscraper — вызывается в отдельном потоке."""
    url = f"https://fragment.com/username/{username}"
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_URL else None
    try:
        resp = _scraper.get(url, headers=HEADERS, timeout=12, proxies=proxies)
        return resp.status_code, resp.text
    except Exception:
        return None


async def _check_fragment(username: str) -> bool | None:
    """
    Дополнительная (не блокирующая) проверка. Если Fragment недоступен
    с текущего хостинга — просто возвращает None и не мешает основной
    проверке через Bot API.

    True  — страница получена и не похожа на активную продажу/аукцион
    False — явные признаки продажи/аукциона прямо сейчас (цена, бид и т.п.)
    None  — не удалось получить настоящую страницу
    """
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, functools.partial(_fetch_fragment_sync, username))

    _fragment_stats["total"] += 1

    if result is None:
        return None

    status_code, html = result

    if status_code == 404:
        _fragment_stats["reachable"] += 1
        return True
    if status_code != 200:
        return None
    if _looks_like_challenge(html):
        return None

    # если дошли сюда — страница реальная, Fragment действительно ответил
    _fragment_stats["reachable"] += 1
    if _SALE_MARKERS_RE.search(html):
        return False

    return True


class AvailabilityChecker:
    def __init__(self, session: aiohttp.ClientSession):
        self.session = session

    async def is_available(self, username: str) -> bool | None:
        api_result, fragment_result = await asyncio.gather(
            _check_via_bot_api(self.session, username),
            _check_fragment(username),
        )

        # если хоть один источник ЯВНО говорит "занято/для продажи" — занято
        if api_result is False or fragment_result is False:
            return False

        # официального Bot API достаточно, чтобы считать юз свободным —
        # Fragment используется только как дополнительный "красный флаг",
        # а не обязательное условие (иначе на ограниченных хостингах
        # находок никогда бы не было)
        if api_result is True:
            return True

        return None
