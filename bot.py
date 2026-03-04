import os
import asyncio
import uuid
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery
)

TOKEN = os.environ["TOKEN"]
SPECIAL_CHAR = "♮"

bot = Bot(token=TOKEN)
dp = Dispatcher()

anon_messages = {}


# --- INLINE ---
@dp.inline_query()
async def inline_handler(inline_query: InlineQuery):
    text = inline_query.query.strip()
    user = inline_query.from_user

    # ✅ Проверяем ТОЛЬКО имя
    if SPECIAL_CHAR not in (user.first_name or ""):
        return

    # Формат: @username текст
    if not text.startswith("@") or " " not in text:
        return

    target_username, message = text.split(" ", 1)
    target_username = target_username[1:]  # убрать @

    callback_id = str(uuid.uuid4())

    anon_messages[callback_id] = {
        "text": message[:200],
        "target_username": target_username.lower()
    }

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть",
                    callback_data=f"open_{callback_id}"
                )
            ]
        ]
    )

    result = InlineQueryResultArticle(
        id=str(uuid.uuid4()),
        title=f"Анонимное сообщение для @{target_username}",
        input_message_content=InputTextMessageContent(
            f"💌 Новое анонимное сообщение для @{target_username}"
        ),
        reply_markup=keyboard
    )

    await inline_query.answer([result], cache_time=0)


# --- CALLBACK ---
@dp.callback_query(F.data.startswith("open_"))
async def open_message(callback: CallbackQuery):
    callback_id = callback.data.replace("open_", "")
    user = callback.from_user

    if callback_id not in anon_messages:
        await callback.answer("❌ Сообщение недоступно", show_alert=True)
        return

    data = anon_messages[callback_id]

    # Проверяем что нажал нужный username
    if not user.username or user.username.lower() != data["target_username"]:
        await callback.answer("❌ Это сообщение не для тебя", show_alert=True)
        return

    await callback.answer(f"💌 {data['text']}", show_alert=True)

    del anon_messages[callback_id]


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
