# -*- coding: utf-8 -*-
import asyncio
import logging
import math
import time

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, BufferedInputFile, LinkPreviewOptions
from aiogram.exceptions import TelegramBadRequest

from config import BOT_TOKEN, CHECK_DELAY_SECONDS, PAGE_SIZE_LIVE, PAGE_SIZE_HISTORY
from keyboards import (
    main_menu_kb,
    filters_kb,
    running_kb,
    paused_kb,
    remove_kb,
    search_pagination_kb,
    history_kb,
)
from username_gen import generate_username, LENGTH_LABELS, DIGIT_MODE_LABELS
from beauty import score_username
from checker import AvailabilityChecker, get_fragment_stats
from fancy_font import fancy_bold, fancy_italic, fancy_style, beauty_bar, circled_number
import storage

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("username_hunter_bot")

BOT_VERSION = "1.4.0"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


class SearchSession:
    def __init__(self, length_choice: str, digit_mode: str, status_chat_id: int, status_message_id: int):
        self.length_choice = length_choice
        self.digit_mode = digit_mode
        self.status_chat_id = status_chat_id
        self.status_message_id = status_message_id

        self.found: list[tuple[str, int]] = []
        self.checked_count = 0
        self.seen: set[str] = set()

        self.paused = asyncio.Event()
        self.paused.set()
        self.stopped = False
        self.task: asyncio.Task | None = None
        self.last_edit_lock = asyncio.Lock()

        self.view_page = 0
        self.follow_latest = True
        self.started_at = time.monotonic()


# chat_id -> SearchSession
sessions: dict[int, SearchSession] = {}

# chat_id -> временно выбранные фильтры до старта поиска
pending_filters: dict[int, dict] = {}


def _fmt_entry(uname: str, score: int) -> str:
    return (
        f"@{uname}\n<code>{uname}</code>   {circled_number(score)}/⑩  {beauty_bar(score)}\n"
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

    lines = [
        header,
        filt,
        "",
        status_line,
        f"{fancy_italic('Проверено')}: {session.checked_count}    "
        f"{fancy_italic('Найдено')}: {len(session.found)}    "
        f"{fancy_italic('Скорость')}: ~{speed:.0f}/мин",
        _fragment_status_line(),
        "",
    ]

    total_pages = max(1, math.ceil(len(session.found) / PAGE_SIZE_LIVE))
    if session.follow_latest:
        session.view_page = total_pages - 1
    else:
        session.view_page = min(session.view_page, total_pages - 1)

    if not session.found:
        lines.append(fancy_italic("Пока ничего не найдено, ищу дальше…") if not finished else fancy_italic("Ничего не найдено."))
    else:
        start = session.view_page * PAGE_SIZE_LIVE
        page_items = session.found[start:start + PAGE_SIZE_LIVE]
        lines.append(fancy_bold("Найденные юзернеймы:"))
        for uname, score in page_items:
            lines.append(_fmt_entry(uname, score))

    return "\n".join(lines)


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


async def search_loop(chat_id: int, session: SearchSession):
    async with aiohttp.ClientSession() as http:
        checker = AvailabilityChecker(http)
        while not session.stopped:
            await session.paused.wait()
            if session.stopped:
                break

            candidate = generate_username(session.length_choice, session.digit_mode)
            if candidate in session.seen:
                await asyncio.sleep(0.05)
                continue
            session.seen.add(candidate)

            # если этот юз уже есть в истории (с прошлых запусков) — не тратим
            # время на повторную сетевую проверку
            if storage.already_known(chat_id, candidate):
                continue

            result = await checker.is_available(candidate)
            session.checked_count += 1

            if result is True:
                score = score_username(candidate)
                session.found.append((candidate, score))
                storage.add_found(chat_id, candidate, score)
                await update_status_message(session)
            elif session.checked_count % 15 == 0:
                await update_status_message(session)

            await asyncio.sleep(CHECK_DELAY_SECONDS)


def _history_page_text(chat_id: int, page: int) -> tuple[str, int]:
    total = storage.count(chat_id)
    total_pages = max(1, math.ceil(total / PAGE_SIZE_HISTORY))
    page = max(0, min(page, total_pages - 1))
    items = storage.get_page(chat_id, page, PAGE_SIZE_HISTORY)

    lines = [fancy_style("История находок"), f"{fancy_italic('Всего сохранено')}: {total}", ""]
    if not items:
        lines.append(fancy_italic("Пока пусто — запусти поиск, чтобы начать собирать историю."))
    else:
        for uname, score, found_at in items:
            date_part = found_at[:10]
            lines.append(_fmt_entry(uname, score) + f"\n{fancy_italic(date_part)}")
    return "\n".join(lines), page


@dp.message(CommandStart())
async def cmd_start(message: Message):
    text = (
        f"{fancy_style('Охотник за юзернеймами')} 👋  "
        f"{fancy_italic('v' + BOT_VERSION)}\n\n"
        f"{fancy_italic('Я подбираю свободные и редкие юзернеймы Telegram')} "
        f"({fancy_italic('5-7 символов')}) {fancy_italic('и оцениваю их красоту от 1 до 10.')}\n\n"
        "Нажми кнопку ниже, чтобы задать фильтры и начать поиск, "
        "или загляни в историю прошлых находок."
    )
    await message.answer(text, reply_markup=main_menu_kb())


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    pending_filters.pop(callback.message.chat.id, None)
    text = (
        f"{fancy_style('Охотник за юзернеймами')} 👋\n\n"
        f"{fancy_italic('Нажми кнопку ниже, чтобы задать фильтры и начать поиск.')}"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb())
    await callback.answer()


@dp.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()


# --- Фильтры и запуск поиска -------------------------------------------------

@dp.callback_query(F.data == "open_filters")
async def open_filters(callback: CallbackQuery):
    pending_filters[callback.message.chat.id] = {"length": None, "digits": None}
    await callback.message.edit_text(
        fancy_style("Настрой фильтры поиска") + "\n\n" + fancy_italic("Выбери длину и режим цифр:"),
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
    if not filters or not filters["length"] or not filters["digits"]:
        await callback.answer("Сначала выбери оба фильтра", show_alert=True)
        return

    if chat_id in sessions and sessions[chat_id].task and not sessions[chat_id].task.done():
        await callback.answer("Поиск уже запущен", show_alert=True)
        return

    await callback.message.edit_text(fancy_italic("Запускаю поиск…"))
    status_msg = await bot.send_message(chat_id, fancy_italic("Готовлю первую партию юзернеймов…"))

    session = SearchSession(
        length_choice=filters["length"],
        digit_mode=filters["digits"],
        status_chat_id=chat_id,
        status_message_id=status_msg.message_id,
    )
    sessions[chat_id] = session
    pending_filters.pop(chat_id, None)

    await bot.send_message(chat_id, fancy_style("Поиск запущен") + " 🚀", reply_markup=running_kb())

    session.task = asyncio.create_task(search_loop(chat_id, session))
    await callback.answer()


# --- Пагинация живого поиска -------------------------------------------------

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


# --- Пауза / Стоп -------------------------------------------------------------

@dp.message(F.text == "⏸ Пауза")
async def pause_search(message: Message):
    session = sessions.get(message.chat.id)
    if not session or session.stopped:
        return
    session.paused.clear()
    await update_status_message(session)
    await message.answer(fancy_italic("Поиск поставлен на паузу."), reply_markup=paused_kb())


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
            await asyncio.wait_for(session.task, timeout=5)
        except asyncio.TimeoutError:
            session.task.cancel()

    await update_status_message(session, finished=True)

    top = ""
    if session.found:
        best_uname, best_score = max(session.found, key=lambda x: x[1])
        top = f"\n{fancy_italic('Лучшая находка')}: @{best_uname} ({circled_number(best_score)}/⑩)"

    summary = (
        f"{fancy_style('Поиск завершён')} ✅\n\n"
        f"{fancy_italic('Проверено юзернеймов')}: {session.checked_count}\n"
        f"{fancy_italic('Найдено свободных')}: {len(session.found)}"
        f"{top}\n\n"
        f"{fancy_italic('Полный список — в разделе История находок.')}"
    )
    await message.answer(summary, reply_markup=remove_kb())
    await message.answer(fancy_italic("Меню:"), reply_markup=main_menu_kb())

    sessions.pop(chat_id, None)


# --- История находок -----------------------------------------------------------

@dp.callback_query(F.data == "open_history")
async def open_history(callback: CallbackQuery):
    text, page = _history_page_text(callback.message.chat.id, 0)
    total = storage.count(callback.message.chat.id)
    total_pages = max(1, math.ceil(total / PAGE_SIZE_HISTORY))
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
    text, page = _history_page_text(callback.message.chat.id, page)
    total = storage.count(callback.message.chat.id)
    total_pages = max(1, math.ceil(total / PAGE_SIZE_HISTORY))
    await callback.message.edit_text(
        text,
        reply_markup=history_kb(page, total_pages),
        parse_mode="HTML",
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await callback.answer()


@dp.callback_query(F.data == "hist_export")
async def history_export(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    items = storage.get_all(chat_id)
    if not items:
        await callback.answer("История пока пуста", show_alert=True)
        return

    lines = [f"{uname}\t{score}/10\t{found_at}" for uname, score, found_at in items]
    content = "username\tscore\tfound_at\n" + "\n".join(lines)
    file = BufferedInputFile(content.encode("utf-8"), filename="usernames_history.txt")
    await bot.send_document(chat_id, file, caption=fancy_italic(f"Всего в истории: {len(items)}"))
    await callback.answer()


async def main():
    # на случай, если на боте когда-то был выставлен вебхук (например, во время
    # экспериментов с другим способом хостинга) — иначе Telegram будет сбрасывать
    # getUpdates и polling не заработает (TelegramConflictError)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
