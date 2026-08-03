from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_pagination_kb(page: int, total_pages: int, prefix: str = "page") -> InlineKeyboardMarkup:
    """
    Клавиатура пагинации для списков (Вотчлист, История, Находки)
    """
    buttons = []
    nav_row = []

    # Кнопка "Назад"
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"{prefix}_{page - 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔", callback_data="noop"))

    # Счётчик страниц
    nav_row.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))

    # Кнопка "Вперёд"
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"{prefix}_{page + 1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="⛔", callback_data="noop"))

    buttons.append(nav_row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_calibration_kb(current_step: int) -> InlineKeyboardMarkup:
    """
    Клавиатура оценки юзернеймов при калибровке
    """
    buttons = [
        [
            InlineKeyboardButton(text="1 ⭐", callback_data="calib_rate_1"),
            InlineKeyboardButton(text="2 ⭐", callback_data="calib_rate_2"),
            InlineKeyboardButton(text="3 ⭐", callback_data="calib_rate_3"),
            InlineKeyboardButton(text="4 ⭐", callback_data="calib_rate_4"),
            InlineKeyboardButton(text="5 ⭐", callback_data="calib_rate_5"),
        ]
    ]
    # Появляется с 5-го шага (максимум 25)
    if current_step >= 5:
        buttons.append([
            InlineKeyboardButton(text="⚡ Завершить калибровку сейчас", callback_data="calib_finish_early")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_settings_kb(settings: dict) -> InlineKeyboardMarkup:
    """
    Главное меню настроек с тумблерами и перепрохождением
    """
    no_mono_str = "✅ Без моноширинного" if settings.get("no_mono") else "❌ Без моноширинного"
    clean_str = "✅ Точный юзер" if settings.get("clean_output") else "❌ Точный юзер"
    silent_str = "✅ Тихий режим" if settings.get("silent_mode") else "❌ Тихий режим"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⚙️ Лимит проверок: {settings.get('check_limit', 1000)}", callback_data="set_limit")],
        [InlineKeyboardButton(text=no_mono_str, callback_data="toggle_nomono")],
        [InlineKeyboardButton(text=clean_str, callback_data="toggle_clean")],
        [InlineKeyboardButton(text=silent_str, callback_data="toggle_silent")],
        [InlineKeyboardButton(text="🔄 Пройти калибровку заново (до 25)", callback_data="reset_calibration")],
    ])
    return keyboard


def get_export_kb() -> InlineKeyboardMarkup:
    """
    Экспорт находок текущей сессии
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📄 Скачать TXT", callback_data="export_txt"),
            InlineKeyboardButton(text="📦 Скачать JSON", callback_data="export_json")
        ]
    ])
