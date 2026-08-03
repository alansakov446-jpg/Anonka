# -*- coding: utf-8 -*-
"""
keyboards.py — все инлайн- и реплай-клавиатуры бота.
Сохранены старые имена функций (main_menu_kb, filters_kb, running_kb, paused_kb,
remove_kb, search_pagination_kb, history_kb) для обратной совместимости.
"""
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from username_gen import LENGTH_LABELS, DIGIT_MODE_LABELS


# --- главное меню /start ---------------------------------------------------
def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Поиск", callback_data="open_filters")
    builder.button(text="📜 История находок", callback_data="open_history")
    builder.button(text="⚙️ Настройки", callback_data="open_settings")
    builder.adjust(1)
    return builder.as_markup()


def back_btn(target: str = "back_to_main") -> InlineKeyboardButton:
    return InlineKeyboardButton(text="◀️ Назад", callback_data=target)


# --- фильтры поиска --------------------------------------------------------
def filters_kb(selected_len: str | None, selected_digits: str | None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in LENGTH_LABELS.items():
        prefix = "✅ " if selected_len == key else ""
        builder.button(text=f"{prefix}{label}", callback_data=f"len_{key}")
    for key, label in DIGIT_MODE_LABELS.items():
        prefix = "✅ " if selected_digits == key else ""
        builder.button(text=f"{prefix}{label}", callback_data=f"digits_{key}")
    builder.adjust(len(LENGTH_LABELS), len(DIGIT_MODE_LABELS))
    builder.button(text="🚀 Начать поиск", callback_data="start_search")
    builder.button(text="◀️ В меню", callback_data="back_to_main")
    builder.adjust(len(LENGTH_LABELS), len(DIGIT_MODE_LABELS), 1, 1)
    return builder.as_markup()


# --- реплай-клавиатуры управления поиском ----------------------------------
def running_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⏸ Пауза"), KeyboardButton(text="⏹ Стоп")],
        ],
        resize_keyboard=True,
    )


def paused_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="▶️ Продолжить"), KeyboardButton(text="⏹ Стоп")],
        ],
        resize_keyboard=True,
    )


def remove_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True, remove_keyboard=True)


# --- пагинация живого поиска ----------------------------------------------
def search_pagination_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️", callback_data="live_page_prev")
    builder.button(text=f"📄 {page + 1}/{total_pages}", callback_data="noop")
    builder.button(text="▶️", callback_data="live_page_next")
    builder.adjust(3)
    return builder.as_markup()


# --- история находок -------------------------------------------------------
def history_kb(page: int, total_pages: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if total_pages > 1:
        builder.button(text="◀️ Назад", callback_data=f"hist_page_{max(page - 1, 0)}")
        builder.button(text=f"Страница {page + 1}/{total_pages}", callback_data="noop")
        builder.button(text="Вперёд ▶️", callback_data=f"hist_page_{min(page + 1, total_pages - 1)}")
    builder.button(text="📥 Скачать TXT", callback_data="hist_export_txt")
    builder.button(text="📦 Скачать JSON", callback_data="hist_export_json")
    builder.button(text="◀️ В меню", callback_data="back_to_main")
    if total_pages > 1:
        builder.adjust(3, 2, 1)
    else:
        builder.adjust(2, 1)
    return builder.as_markup()


# --- настройки -------------------------------------------------------------
def settings_kb(settings: dict, calib_completed: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    limit = settings.get("check_limit", 1000)
    builder.button(text=f"🔢 Лимит проверок/прогон: {limit}", callback_data="set_limit")

    mono = "✅" if settings.get("no_mono") else "❌"
    builder.button(text=f"{mono} Без моноширинного", callback_data="toggle_no_mono")

    clean = "✅" if settings.get("clean_output") else "❌"
    builder.button(text=f"{clean} Точный юзер (чистый текст)", callback_data="toggle_clean_output")

    silent = "✅" if settings.get("silent_mode") else "❌"
    builder.button(text=f"{silent} Тихий режим", callback_data="toggle_silent_mode")

    calib_label = "✅ Калибровка пройдена" if calib_completed else "⚠️ Калибровка не пройдена"
    builder.button(text=f"🔄 Пройти калибровку заново  ({calib_label})", callback_data="start_calibration")

    builder.button(text="◀️ В меню", callback_data="back_to_main")
    builder.adjust(1, 2, 1)
    return builder.as_markup()


# --- калибровка ------------------------------------------------------------
def calibration_kb(step: int, total_steps: int = 25, can_finish: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # оценки 1..10
    for score in range(1, 11):
        builder.button(text=str(score), callback_data=f"calib_score_{score}")
    builder.adjust(5, 5)
    if can_finish:
        builder.button(text="⚡ Завершить калибровку сейчас", callback_data="calib_finish_early")
    builder.button(text="❌ Отмена", callback_data="calib_cancel")
    builder.adjust(5, 5, 1 if can_finish else 2)
    return builder.as_markup()


def limit_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for val in (500, 1000, 2500, 5000, 10000, 0):
        label = "∞ (без лимита)" if val == 0 else str(val)
        builder.button(text=label, callback_data=f"set_limit_{val}")
    builder.button(text="◀️ Назад", callback_data="open_settings")
    builder.adjust(3, 3, 1)
    return builder.as_markup()


def back_to_settings_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="◀️ Назад", callback_data="open_settings")
    return b.as_markup()
