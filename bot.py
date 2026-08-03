# -*- coding: utf-8 -*-
"""
Охотник за юзернеймами — Telegram-бот (aiogram 3.x). Версия 1.5.0.
"""
import asyncio
import json
import logging
import math
import random
import time
from typing import Optional

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile, LinkPreviewOptions
from aiogram.exceptions import TelegramBadRequest

from config import (
    BOT_TOKEN, CHECK_DELAY_SECONDS, CONCURRENCY,
    PAGE_SIZE_LIVE, PAGE_SIZE_HISTORY, MAX_MESSAGE_CHARS,
)
from keyboards import (
    main_menu_kb, filters_kb, running_kb, paused_kb, remove_kb,
    search_pagination_kb, history_kb, settings_kb, calibration_kb,
    limit_choice_kb, back_to_settings_kb,
)
from username_gen import generate_username, LENGTH_LABELS, DIGIT_MODE_LABELS
from beauty import (
    evaluate_username_score, score_username, format_username_output,
    build_calibration_weights, is_reserved,
)
from checker import AvailabilityChecker, get_fragment_stats
from fancy_font import fancy_bold, fancy_italic, fancy_style, beauty_bar, circled_number
from storage import db as storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("username_hunter_bot")

BOT_VERSION = "1.5.1"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =====================================================================
#                              СЕССИИ ПОИСКА
# =====================================================================
class SearchSession:
    def __init__(self, length_choice: str, digit_mode: str, check_limit: int,
                 status_chat_id: int, status_message_id: int, settings: dict,
                 calib_weights: Optional[dict]):
        self.length_choice = length_choice
        self.digit_mode = digit_mode
        self.check_limit = check_limit  # 0 == без лимита
        self.status_chat_id = status_chat_id
        self.status_message_id = status_message_id
        self.settings = settings
        self.calib_weights = calib_weights or {}

        self.found: list[tuple[str, float]] = []   # (username, score)
        self.checked_count = 0
        self.reserved_skipped = 0
        self.seen: set[str] = set()
        self.known_cache: set[str] = set()         # кэш уже известных юзов, чтобы не дёргать БД каждый раз

        self.paused = asyncio.Event()
        self.paused.set()
        self.stopped = False
        self.task: asyncio.Task | None = None
        self.last_edit_lock = asyncio.Lock()
        self.view_page = 0
        self.follow_latest = True
        self.started_at = time.monotonic()


sessions: dict[int, SearchSession] = {}
pending_filters: dict[int, dict] = {}

# калибровка в процессе
calibration_state: dict[int, dict] = {}


# =====================================================================
#                          ФОРМАТИРОВАНИЕ / СТАТУС
# =====================================================================
def _fmt_entry(uname: str, score: float, settings: dict) -> str:
    score_int = int(round(score))
    if settings.get("clean_output"):
        return f"@{uname}"
    if settings.get("no_mono"):
        return (
            f"@{uname}   {circled_number(score_int)}/⑩ {beauty_bar(score_int)}\n"
            f"🔗 https://fragment.com/username/{uname}"
        )
    # стандарт: @юзернейм обычным текстом, ниже моно-версия + оценка + ссылка
    return (
        f"@{uname}\n"
        f"<code>{uname}</code>   {circled_number(score_int)}/⑩ {beauty_bar(score_int)}\n"
        f"🔗 https://fragment.com/username/{uname}"
    )


def _fragment_status_line() -> str:
    stats = get_fragment_stats()
    if stats["total"] < 5:
        return f"{fancy_italic('Fragment')}: ⏳ проверяю доступность…"
    if stats["reachable"] == 0:
        return (
            f"{fancy_italic('Fragment')}: ❌ недоступен с этого хостинга "
            f"(проверяй находки по ссылке 🔗 вручную)"
        )
    ratio = stats["reachable"] / stats["total"]
    if ratio < 0.5:
        return f"{fancy_italic('Fragment')}: ⚠️ доступен нестабильно"
    return f"{fancy_italic('Fragment')}: ✅ доступен"


def _paginate_findings(found: list[tuple[str, float]], page: int, page_size: int):
    total_pages = max(1, math.ceil(len(found) / page_size))
    page = max(0, min(page, total_pages - 1))
    start = page * page_size
    return found[start:start + page_size], total_pages, page


def build_status_text(session: SearchSession, finished: bool = False) -> str:
    header = fancy_style("Поиск юзернеймов")
    filt = (
        f"{fancy_italic('Длина')}: {LENGTH_LABELS[session.length_choice]}\n"
        f"{fancy_italic('Цифры')}: {DIGIT_MODE_LABELS[session.digit_mode]}"
    )
    status_line = (
        "⏹ Поиск остановлен" if finished
        else ("⏸ На паузе" if not session.paused.is_set() else "🔎 Идёт поиск…")
    )
    elapsed_min = max((time.monotonic() - session.started_at) / 60, 0.01)
    speed = session.checked_count / elapsed_min

    limit_str = "∞" if not session.check_limit else str(session.check_limit)

    lines = [
        header,
        filt,
        "",
        status_line,
        f"{fancy_italic('Проверено')}: {session.checked_count}/{limit_str}    "
        f"{fancy_italic('Найдено свободных')}: {len(session.found)}",
        f"{fancy_italic('Скорость')}: ~{speed:.0f} юз/мин    "
        f"{fancy_italic('Зарезерв./отсеяно')}: {session.reserved_skipped}",
        _fragment_status_line(),
        "",
    ]

    page_items, total_pages, session.view_page = _paginate_findings(
        session.found, session.view_page, PAGE_SIZE_LIVE
    )
    if session.follow_latest:
        session.view_page = total_pages - 1
        page_items = session.found[(total_pages - 1) * PAGE_SIZE_LIVE : total_pages * PAGE_SIZE_LIVE]

    if not session.found:
        lines.append(
            fancy_italic("Пока ничего не найдено, ищу дальше…")
            if not finished else fancy_italic("Ничего не найдено.")
        )
    else:
        lines.append(fancy_bold(f"Найденные юзернеймы (стр. {session.view_page + 1}/{total_pages}):"))
        for uname, score in page_items:
            lines.append(_fmt_entry(uname, score, session.settings))

    text = "\n".join(lines)
    # подстраховка: если текст вдруг вылез за лимит (из-за шрифтов) — обрезаем хвост
    if len(text) > MAX_MESSAGE_CHARS:
        text = text[: MAX_MESSAGE_CHARS - 40] + "\n\n…" + fancy_italic("слишком много находок, листай ➡️")
    return text


async def update_status_message(session: SearchSession, finished: bool = False):
    async with session.last_edit_lock:
        text = build_status_text(session, finished=finished)
        total_pages = max(1, math.ceil(len(session.found) / PAGE_SIZE_LIVE))
        markup = None if finished else search_pagination_kb(session.view_page, total_pages)
        try:
            await bot.edit_message_text(
                chat_id=session.status_chat_id,
                message_id=session.status_message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                log.warning("Не удалось обновить статус-сообщение: %s", e)


# =====================================================================
#                           ГЛАВНЫЙ ЦИКЛ ПОИСКА
# =====================================================================
async def _worker(name: str, session: SearchSession, in_q: asyncio.Queue, checker: AvailabilityChecker):
    """Один воркер параллельной проверки."""
    while True:
        item = await in_q.get()
        if item is None:
            in_q.task_done()
            break
        candidate = item
        try:
            await session.paused.wait()
            if session.stopped:
                in_q.task_done()
                break

            if is_reserved(candidate):
                session.reserved_skipped += 1
                session.checked_count += 1
                in_q.task_done()
                continue

            result = await checker.is_available(candidate)
            session.checked_count += 1

            if result is True:
                score = evaluate_username_score(candidate, session.calib_weights)
                session.found.append((candidate, score))
                try:
                    await storage.add_found(session.status_chat_id, candidate, score)
                    session.known_cache.add(candidate)
                except Exception as e:
                    log.exception("Не удалось сохранить находку %s: %s", candidate, e)
                if not session.settings.get("silent_mode"):
                    await update_status_message(session)
            elif session.checked_count % 8 == 0:
                if not session.settings.get("silent_mode"):
                    await update_status_message(session)

            await asyncio.sleep(CHECK_DELAY_SECONDS)
        except Exception as e:
            log.exception("Воркер %s ошибка на %s: %s", name, candidate, e)
        finally:
            in_q.task_done()

        # лимит
        if session.check_limit and session.checked_count >= session.check_limit:
            session.stopped = True


async def _producer(session: SearchSession, in_q: asyncio.Queue):
    """Постійно підкидає нові кандидати в чер Until стоп."""
    while not session.stopped:
        await session.paused.wait()
        if session.stopped:
            break

        # если в очереди слишком много — ждём, чтобы не генерировать тонны впустую
        if in_q.qsize() >= CONCURRENCY * 4:
            await asyncio.sleep(0.1)
            continue

        candidate = generate_username(session.length_choice, session.digit_mode).lower()
        if candidate in session.seen or candidate in session.known_cache:
            continue
        session.seen.add(candidate)

        # асинхронная проверка по БД (использует кэш в синхр.-ветви для sqlite)
        try:
            known = await storage.already_known(session.status_chat_id, candidate)
        except Exception:
            known = False
        if known:
            session.known_cache.add(candidate)
            continue

        await in_q.put(candidate)

        if session.check_limit and session.checked_count >= session.check_limit:
            session.stopped = True
            break

        await asyncio.sleep(0)


async def search_loop(chat_id: int, session: SearchSession):
    connector = aiohttp.TCPConnector(limit=CONCURRENCY * 2, ttl_dns_cache=300)
    async with aiohttp.ClientSession(connector=connector) as http:
        checker = AvailabilityChecker(http)
        in_q: asyncio.Queue = asyncio.Queue(maxsize=CONCURRENCY * 6)

        workers = [
            asyncio.create_task(_worker(f"w{i}", session, in_q, checker))
            for i in range(CONCURRENCY)
        ]
        prod = asyncio.create_task(_producer(session, in_q))

        # ждём пока стоп не выстрелит
        while not session.stopped:
            await asyncio.sleep(0.2)

        # сигнал ворам остановиться
        for _ in workers:
            try:
                in_q.put_nowait(None)
            except Exception:
                pass
        prod.cancel()
        for w in workers:
            w.cancel()
        try:
            await asyncio.gather(*workers, return_exceptions=True)
        except Exception:
            pass

    await update_status_message(session, finished=True)


# =====================================================================
#                           /start и МЕНЮ
# =====================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message):
    await storage.init_db()
    text = (
        f"{fancy_style('Охотник за юзернеймами')} 👋  "
        f"{fancy_italic('v' + BOT_VERSION)}\n\n"
        f"{fancy_italic('Я подбираю свободные и редкие юзернеймы Telegram')} "
        f"{fancy_italic('(от 5 символов), жёстко проверяю их через Bot API и Fragment')} "
        f"{fancy_italic('(с обходом CloudFlare через cloudscraper)')} "
        f"{fancy_italic('и оцениваю красоту от 1 до 10.')}\n\n"
        f"{fancy_italic('Параллельная проверка включена — ')}~{CONCURRENCY}{fancy_italic(' потоков одновременно.')}"
    )
    await message.answer(text, reply_markup=main_menu_kb())


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    pending_filters.pop(callback.message.chat.id, None)
    calibration_state.pop(callback.message.chat.id, None)
    text = (
        f"{fancy_style('Охотник за юзернеймами')} 👋\n\n"
        f"{fancy_italic('Выбери раздел:')}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# =====================================================================
#                        ФИЛЬТРЫ / ЗАПУСК ПОИСКА
# =====================================================================
@dp.callback_query(F.data == "open_filters")
async def open_filters(callback: CallbackQuery):
    pending_filters[callback.message.chat.id] = {"length": None, "digits": None}
    await callback.message.edit_text(
        fancy_style("Настрой фильтры поиска") + "\n\n" +
        fancy_italic("Выбери длину (от 5) и режим цифр:"),
        reply_markup=filters_kb(None, None),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("len_"))
async def set_length_filter(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    value = callback.data.removeprefix("len_")
    filters = pending_filters.setdefault(chat_id, {"length": None, "digits": None})
    filters["length"] = value
    await callback.message.edit_reply_markup(reply_markup=filters_kb(filters["length"], filters["digits"]))
    await callback.answer(f"Длина: {LENGTH_LABELS[value]}")


@dp.callback_query(F.data.startswith("digits_"))
async def set_digits_filter(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    value = callback.data.removeprefix("digits_")
    filters = pending_filters.setdefault(chat_id, {"length": None, "digits": None})
    filters["digits"] = value
    await callback.message.edit_reply_markup(reply_markup=filters_kb(filters["length"], filters["digits"]))
    await callback.answer(f"Цифры: {DIGIT_MODE_LABELS[value]}")


@dp.callback_query(F.data == "start_search")
async def start_search(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    filters = pending_filters.get(chat_id)
    if not filters or not filters.get("length") or not filters.get("digits"):
        await callback.answer("Сначала выбери оба фильтра", show_alert=True)
        return

    if chat_id in sessions and sessions[chat_id].task and not sessions[chat_id].task.done():
        await callback.answer("Поиск уже запущен", show_alert=True)
        return

    settings = await storage.get_settings(chat_id)
    calib = await storage.get_calibration(chat_id)
    calib_weights = calib if calib.get("is_completed") else None

    await callback.message.edit_text(fancy_italic("Запускаю поиск…"))
    status_msg = await bot.send_message(chat_id, fancy_italic("Готовлю первую партию юзернеймов…"))

    session = SearchSession(
        length_choice=filters["length"],
        digit_mode=filters["digits"],
        check_limit=settings.get("check_limit", 1000) or 0,
        status_chat_id=chat_id,
        status_message_id=status_msg.message_id,
        settings=settings,
        calib_weights=calib_weights,
    )
    # затарим в кэш последние известные юзы (чтобы не долбить БД на каждом кандидате)
    try:
        recent = await storage.get_page(chat_id, 0, 500)
        session.known_cache = {u for u, _, _ in recent}
    except Exception:
        session.known_cache = set()

    sessions[chat_id] = session
    pending_filters.pop(chat_id, None)

    await bot.send_message(
        chat_id,
        fancy_style("Поиск запущен") + f" 🚀 ({CONCURRENCY} потоков)",
        reply_markup=running_kb(),
    )
    session.task = asyncio.create_task(search_loop(chat_id, session))
    await callback.answer()


# =====================================================================
#                       ПАГИНАЦИЯ В ПОИСКЕ
# =====================================================================
@dp.callback_query(F.data == "live_page_prev")
async def live_page_prev(callback: CallbackQuery):
    session = sessions.get(callback.message.chat.id)
    if not session:
        await callback.answer()
        return
    session.view_page = max(0, session.view_page - 1)
    session.follow_latest = False
    await update_status_message(session)
    await callback.answer()


@dp.callback_query(F.data == "live_page_next")
async def live_page_next(callback: CallbackQuery):
    session = sessions.get(callback.message.chat.id)
    if not session:
        await callback.answer()
        return
    total_pages = max(1, math.ceil(len(session.found) / PAGE_SIZE_LIVE))
    session.view_page = min(total_pages - 1, session.view_page + 1)
    session.follow_latest = session.view_page == total_pages - 1
    await update_status_message(session)
    await callback.answer()


# =====================================================================
#                      ПАУЗА / ПРОДОЛЖИТЬ / СТОП
# =====================================================================
@dp.message(F.text == "⏸ Пауза")
async def pause_search(message: Message):
    session = sessions.get(message.chat.id)
    if not session or session.stopped:
        return
    session.paused.clear()
    await update_status_message(session)
    await message.answer(fancy_italic("Поиск поставлен на паузу. Можно возобновить."), reply_markup=paused_kb())


@dp.message(F.text == "▶️ Продолжить")
async def resume_search(message: Message):
    session = sessions.get(message.chat.id)
    if not session or session.stopped:
        return
    session.paused.set()
    await update_status_message(session)
    await message.answer(fancy_italic("Продолжаю поиск…"), reply_markup=running_kb())


@dp.message(F.text == "⏹ Стоп")
async def stop_search(message: Message):
    chat_id = message.chat.id
    session = sessions.get(chat_id)
    if not session or session.stopped:
        return

    session.stopped = True
    session.paused.set()

    if session.task:
        try:
            await asyncio.wait_for(session.task, timeout=8)
        except asyncio.TimeoutError:
            session.task.cancel()

    await update_status_message(session, finished=True)

    top = ""
    if session.found:
        best_uname, best_score = max(session.found, key=lambda x: x[1])
        top = f"\n{fancy_italic('Лучшая находка')}: @{best_uname} ({circled_number(int(round(best_score)))}/⑩)"

    elapsed_min = max((time.monotonic() - session.started_at) / 60, 0.01)
    summary = (
        f"{fancy_style('Поиск завершён')} ✅\n\n"
        f"{fancy_italic('Проверено юзернеймов')}: {session.checked_count}\n"
        f"{fancy_italic('Найдено свободных')}: {len(session.found)}\n"
        f"{fancy_italic('Средняя скорость')}: ~{session.checked_count / elapsed_min:.0f}/мин"
        f"{top}\n\n"
        f"{fancy_italic('Полный список — в разделе История находок.')}"
    )
    await message.answer(summary, reply_markup=remove_kb())
    await message.answer(fancy_italic("Меню:"), reply_markup=main_menu_kb())

    sessions.pop(chat_id, None)


# =====================================================================
#                       ИСТОРИЯ НАХОДОК
# =====================================================================
def _history_page_text(chat_id: int, page: int, items=None, total=None,
                      prefix_title: str = "История находок") -> tuple[str, int]:
    if items is None or total is None:
        raise RuntimeError("items/total required")
    total_pages = max(1, math.ceil(total / PAGE_SIZE_HISTORY))
    page = max(0, min(page, total_pages - 1))
    page_items = items[page * PAGE_SIZE_HISTORY : (page + 1) * PAGE_SIZE_HISTORY]

    lines = [fancy_style(prefix_title), f"{fancy_italic('Всего')}: {total}", ""]
    if not page_items:
        lines.append(fancy_italic("Пока пусто."))
    else:
        for uname, score, found_at in page_items:
            date_part = (found_at or "")[:10]
            entry = _fmt_entry(uname, score, {"no_mono": False, "clean_output": False})
            lines.append(entry + (f"\n{fancy_italic(date_part)}" if date_part else ""))
    return "\n".join(lines), page, total_pages


async def _get_user_settings(chat_id: int):
    s = await storage.get_settings(chat_id)
    # в текущей сессии могут быть более свежие настройки
    if chat_id in sessions:
        return sessions[chat_id].settings
    return s


@dp.callback_query(F.data == "open_history")
async def open_history(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    items = await storage.get_all(chat_id)
    total = len(items)
    text, page, total_pages = _history_page_text(chat_id, 0, items=items, total=total)
    await callback.message.edit_text(
        text,
        reply_markup=history_kb(page, total_pages),
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("hist_page_"))
async def history_page(callback: CallbackQuery):
    page = int(callback.data.removeprefix("hist_page_"))
    chat_id = callback.message.chat.id
    items = await storage.get_all(chat_id)
    total = len(items)
    text, page, total_pages = _history_page_text(chat_id, page, items=items, total=total)
    await callback.message.edit_text(
        text,
        reply_markup=history_kb(page, total_pages),
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await callback.answer()


@dp.callback_query(F.data == "hist_export_txt")
async def history_export_txt(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    items = await storage.get_all(chat_id)
    if not items:
        await callback.answer("История пока пуста", show_alert=True)
        return
    lines = ["username\tscore\tfound_at"]
    for uname, score, found_at in items:
        lines.append(f"@{uname}\t{score:.1f}/10\t{found_at}")
    content = "\n".join(lines)
    file = BufferedInputFile(content.encode("utf-8"), filename="usernames_history.txt")
    await bot.send_document(chat_id, file, caption=fancy_italic(f"Всего в истории: {len(items)}"))
    await callback.answer()


@dp.callback_query(F.data == "hist_export_json")
async def history_export_json(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    items = await storage.get_all(chat_id)
    if not items:
        await callback.answer("История пока пуста", show_alert=True)
        return
    payload = [
        {"username": u, "score": s, "found_at": t} for u, s, t in items
    ]
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    file = BufferedInputFile(content.encode("utf-8"), filename="usernames_history.json")
    await bot.send_document(chat_id, file, caption=fancy_italic(f"Всего: {len(items)}"))
    await callback.answer()


# =====================================================================
#                           НАСТРОЙКИ
# =====================================================================
@dp.callback_query(F.data == "open_settings")
async def open_settings(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    settings = await storage.get_settings(chat_id)
    calib = await storage.get_calibration(chat_id)
    await callback.message.edit_text(
        fancy_style("Настройки") + "\n\n" +
        fancy_italic("Тумблеры применяются к новым поискам сразу."),
        reply_markup=settings_kb(settings, calib.get("is_completed", False)),
    )
    await callback.answer()


@dp.callback_query(F.data == "set_limit")
async def ask_limit(callback: CallbackQuery):
    await callback.message.edit_text(
        fancy_style("Лимит проверок за один прогон") + "\n\n" +
        fancy_italic("Выбери значение или 0 — без лимита:"),
        reply_markup=limit_choice_kb(),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("set_limit_"))
async def apply_limit(callback: CallbackQuery):
    val = int(callback.data.removeprefix("set_limit_"))
    await storage.update_settings(callback.message.chat.id, "check_limit", val)
    await open_settings(callback)


@dp.callback_query(F.data == "toggle_no_mono")
async def toggle_no_mono(callback: CallbackQuery):
    s = await storage.get_settings(callback.message.chat.id)
    await storage.update_settings(callback.message.chat.id, "no_mono", not s.get("no_mono"))
    await open_settings(callback)


@dp.callback_query(F.data == "toggle_clean_output")
async def toggle_clean(callback: CallbackQuery):
    s = await storage.get_settings(callback.message.chat.id)
    await storage.update_settings(callback.message.chat.id, "clean_output", not s.get("clean_output"))
    await open_settings(callback)


@dp.callback_query(F.data == "toggle_silent_mode")
async def toggle_silent(callback: CallbackQuery):
    s = await storage.get_settings(callback.message.chat.id)
    await storage.update_settings(callback.message.chat.id, "silent_mode", not s.get("silent_mode"))
    await open_settings(callback)


# =====================================================================
#                          КАЛИБРОВКА
# =====================================================================
CALIBRATION_SAMPLES = [
    "wezaz", "hdkjl", "zorty", "qxnrb", "mavlo", "triski", "blorem",
    "snake7", "pr1me", "0xbyte", "crystal", "kortex", "vylpe", "qzorx",
    "nebula", "f0xie", "t0ken", "plasma", "drak0", "veru",
    "k1ngs", "flame0", "storm", "bl4ze", "glowz",
]

@dp.callback_query(F.data == "start_calibration")
async def start_calibration(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    samples = random.sample(CALIBRATION_SAMPLES, k=min(10, len(CALIBRATION_SAMPLES)))
    calibration_state[chat_id] = {"step": 0, "samples": samples, "ratings": []}
    await _show_calibration_step(callback.message.edit_text, chat_id)
    await callback.answer()


async def _show_calibration_step(edit_fn, chat_id: int):
    state = calibration_state.get(chat_id)
    if not state:
        return
    step = state["step"]
    samples = state["samples"]
    if step >= len(samples) or step >= 25:
        await _finish_calibration(chat_id, edit_fn)
        return
    uname = samples[step]
    auto_score = evaluate_username_score(uname)
    can_finish = step >= 4  # с 5-го шага (step=4) можно закончить досрочно
    text = (
        f"{fancy_style('Калибровка оценки красоты')}\n\n"
        f"{fancy_italic('Шаг')} {step + 1}/{len(samples)}\n\n"
        f"Юзернейм: <code>{uname}</code>\n"
        f"Оценка бота по умолчанию: <b>{auto_score}/10</b>\n\n"
        f"{fancy_italic('Поставь свою оценку от 1 до 10 — я подстроюсь под твой вкус.')}"
    )
    await edit_fn(text, reply_markup=calibration_kb(step, len(samples), can_finish=can_finish),
                  parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))


async def _finish_calibration(chat_id: int, edit_fn):
    state = calibration_state.pop(chat_id, None)
    if not state or not state["ratings"]:
        await edit_fn(fancy_italic("Калибровка отменена (мало оценок)."),
                      reply_markup=back_to_settings_kb())
        return
    weights = build_calibration_weights(state["ratings"])
    await storage.save_calibration(chat_id, {
        **weights,
        "is_completed": True,
        "history": state["ratings"],
    })
    await edit_fn(
        f"{fancy_style('Калибровка сохранена')} ✅\n\n"
        + fancy_italic("Теперь оценка красоты будет подстроена под твои предпочтения."),
        reply_markup=back_to_settings_kb(),
    )


@dp.callback_query(F.data.startswith("calib_score_"))
async def calib_score(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    score = int(callback.data.removeprefix("calib_score_"))
    state = calibration_state.get(chat_id)
    if not state:
        await callback.answer("Калибровка не активна")
        return
    uname = state["samples"][state["step"]]
    state["ratings"].append((uname, float(score)))
    state["step"] += 1
    await _show_calibration_step(callback.message.edit_text, chat_id)
    await callback.answer()


@dp.callback_query(F.data == "calib_finish_early")
async def calib_finish_early(callback: CallbackQuery):
    await _finish_calibration(callback.message.chat.id, callback.message.edit_text)
    await callback.answer()


@dp.callback_query(F.data == "calib_cancel")
async def calib_cancel(callback: CallbackQuery):
    calibration_state.pop(callback.message.chat.id, None)
    await callback.message.edit_text(fancy_italic("Калибровка отменена."),
                                     reply_markup=back_to_settings_kb())
    await callback.answer()


# =====================================================================
async def main():
    await storage.init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
