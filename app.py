# -*- coding: utf-8 -*-
"""
Точка входа для Hugging Face Spaces (SDK: Gradio).

Spaces умеет постоянно держать живым только веб-процесс — обычный
"фоновый скрипт без интерфейса" туда не задеплоить. Поэтому сам
Telegram-бот (bot.main()) запускается в отдельном потоке со своим
event loop, а Gradio показывает простую страницу-статус: она нужна
только чтобы Spaces видел "живой" процесс и не останавливал его.

Сам бот при этом работает как обычно — через Telegram, эта страница
никак не участвует в его логике.
"""

import asyncio
import threading
import time

import gradio as gr

from bot import main as bot_main, BOT_VERSION


def _run_bot_forever():
    """Работает в отдельном потоке — свой event loop, не мешает Gradio."""
    while True:
        try:
            asyncio.run(bot_main())
        except Exception as e:
            print(f"[bot] упал с ошибкой, перезапускаю через 5 секунд: {e}")
            time.sleep(5)


_bot_thread = threading.Thread(target=_run_bot_forever, daemon=True)
_bot_thread.start()


with gr.Blocks(title="Username Hunter Bot") as demo:
    gr.Markdown(
        f"# 🤖 Username Hunter Bot\n\n"
        f"Версия: **{BOT_VERSION}**\n\n"
        f"Бот работает в фоне и общается только через Telegram — "
        f"эта страница ничего не делает сама по себе, она нужна "
        f"только чтобы Hugging Face Spaces держал процесс запущенным."
    )

demo.launch()
