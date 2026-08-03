# -*- coding: utf-8 -*-
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)

from username_gen import LENGTH_LABELS, DIGIT_MODE_LABELS


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Найти юзернейм", callback_data="open_filters")],
            [InlineKeyboardButton(text="📜 История находок", callback_data="open_history")],
        ]
    )


def filters_kb(selected_length: str | None, selected_digit_mode: str | None) -> InlineKeyboardMarkup:
    def mark(value: str, current: str | None) -> str:
        return "✅ " if value == current else ""

    rows = [
        [InlineKeyboardButton(text="Длина юзернейма ⬇️", callback_data="noop")],
        [
            InlineKeyboardButton(text=f"{mark('5', selected_length)}5", callback_data="len_5"),
            InlineKeyboardButton(text=f"{mark('6', selected_length)}6", callback_data="len_6"),
            InlineKeyboardButton(text=f"{mark('7', selected_length)}7", callback_data="len_7"),
            InlineKeyboardButton(text=f"{mark('any', selected_length)}5-7", callback_data="len_any"),
        ],
        [InlineKeyboardButton(text="Цифры ⬇️", callback_data="noop")],
        [
            InlineKeyboardButton(
                text=f"{mark('no_digits', selected_digit_mode)}Без цифр",
                callback_data="digits_no_digits",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{mark('with_digits', selected_digit_mode)}С цифрами",
                callback_data="digits_with_digits",
            )
        ],
        [
            InlineKeyboardButton(
                text=f"{mark('leet', selected_digit_mode)}Замена букв на цифры",
                callback_data="digits_leet",
            )
        ],
    ]

    if selected_length and selected_digit_mode:
        rows.append([InlineKeyboardButton(text="▶️ Начать поиск", callback_data="start_search")])

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def running_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="⏸ Пауза"), KeyboardButton(text="⏹ Стоп")]],
        resize_keyboard=True,
    )


def paused_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="▶️ Продолжить"), KeyboardButton(text="⏹ Стоп")]],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove()


def search_pagination_kb(page: int, total_pages: int) -> InlineKeyboardMarkup | None:
    """Пагинация, прикреплённая к живому сообщению поиска."""
    if total_pages <= 1:
        return None
    row = []
    if page > 0:
        row.append(InlineKeyboardButton(text="⬅️", callback_data="live_page_prev"))
    row.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        row.append(InlineKeyboardButton(text="➡️", callback_data="live_page_next"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


def history_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Пагинация + экспорт для истории находок."""
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="⬅️", callback_data=f"hist_page_{page - 1}"))
    nav_row.append(InlineKeyboardButton(text=f"{page + 1}/{max(total_pages, 1)}", callback_data="noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="➡️", callback_data=f"hist_page_{page + 1}"))

    rows = [nav_row] if nav_row else []
    rows.append([InlineKeyboardButton(text="📥 Скачать всё (.txt)", callback_data="hist_export")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
