# -*- coding: utf-8 -*-
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not BOT_TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Создай файл .env со строкой BOT_TOKEN=твой_токен_от_BotFather "
        "или задай переменную окружения BOT_TOKEN."
    )

# --- настройки параллельности ---
# Количество одновременных проверок (больше → быстрее, но Telegram/Fragment
# могут начать отбивать запросы или давать капчу на Fragment).
CONCURRENCY = int(os.getenv("CONCURRENCY", "5"))

# Пауза между запуском новых проверок внутри одного воркера (секунды).
# При CONCURRENCY=5 и CHECK_DELAY_SECONDS=0.25 выходит примерно 20 проверок/сек.
CHECK_DELAY_SECONDS = float(os.getenv("CHECK_DELAY_SECONDS", "0.25"))

# --- пагинация ---
# Сколько находок на одной странице живого статуса поиска.
PAGE_SIZE_LIVE = int(os.getenv("PAGE_SIZE_LIVE", "6"))
# То же — для истории.
PAGE_SIZE_HISTORY = int(os.getenv("PAGE_SIZE_HISTORY", "10"))
# Максимальная длина одного сообщения Telegram (оставляем запас под заголовки/кнопки).
MAX_MESSAGE_CHARS = 3500

# --- прокси ---
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None

# --- БД ---
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "bot_data.db").strip()
