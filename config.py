import os

# Можно либо создать файл .env рядом с ботом со строкой BOT_TOKEN=..., 
# либо просто задать переменную окружения BOT_TOKEN перед запуском.
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

# Задержка между проверками юзернеймов (в секундах).
# Не ставь слишком маленькое значение — t.me и fragment.com могут начать банить IP за частые запросы.
CHECK_DELAY_SECONDS = 1.3

# Сколько находок показывать на одной "странице" в живом сообщении поиска
# и в разделе "История находок" (постраничная навигация ⬅️➡️).
PAGE_SIZE_LIVE = 6
PAGE_SIZE_HISTORY = 10

# Опционально: адрес HTTP-прокси, если хостинг требует ходить в интернет
# только через него (например некоторые бесплатные тарифы). Если не нужно —
# просто не задавай эту переменную окружения, всё будет работать как обычно.
PROXY_URL = os.getenv("PROXY_URL", "").strip() or None
