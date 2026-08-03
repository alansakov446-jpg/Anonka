# -*- coding: utf-8 -*-
"""
Постоянное хранилище найденных юзернеймов (SQLite, файл рядом с ботом).

Зачем это отдельно от оперативной памяти:
 - при перезапуске бота (обновление кода, перезагрузка сервера) история
   находок не должна теряться;
 - позволяет не показывать (и не перепроверять) один и тот же юзернейм
   дважды, даже если пользователь запускал поиск много раз в разные дни;
 - даёт возможность полноценно листать историю страницами и выгружать
   всё одним файлом.
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone

_DB_DIR = os.getenv("DB_DIR", ".")
DB_PATH = os.path.join(_DB_DIR, "username_hunter.db")

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS found_usernames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        username TEXT NOT NULL,
        score INTEGER NOT NULL,
        found_at TEXT NOT NULL,
        UNIQUE(chat_id, username)
    )
    """
)
_conn.commit()


def add_found(chat_id: int, username: str, score: int) -> None:
    with _lock:
        _conn.execute(
            "INSERT OR IGNORE INTO found_usernames (chat_id, username, score, found_at) VALUES (?, ?, ?, ?)",
            (chat_id, username, score, datetime.now(timezone.utc).isoformat()),
        )
        _conn.commit()


def already_known(chat_id: int, username: str) -> bool:
    with _lock:
        cur = _conn.execute(
            "SELECT 1 FROM found_usernames WHERE chat_id = ? AND username = ? LIMIT 1",
            (chat_id, username),
        )
        return cur.fetchone() is not None


def count(chat_id: int) -> int:
    with _lock:
        cur = _conn.execute("SELECT COUNT(*) FROM found_usernames WHERE chat_id = ?", (chat_id,))
        return cur.fetchone()[0]


def get_page(chat_id: int, page: int, page_size: int):
    """page — с нуля. Возвращает список (username, score, found_at), самые новые первыми."""
    with _lock:
        cur = _conn.execute(
            "SELECT username, score, found_at FROM found_usernames "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (chat_id, page_size, page * page_size),
        )
        return cur.fetchall()


def get_all(chat_id: int):
    with _lock:
        cur = _conn.execute(
            "SELECT username, score, found_at FROM found_usernames WHERE chat_id = ? ORDER BY id DESC",
            (chat_id,),
        )
        return cur.fetchall()


def get_top(chat_id: int, limit: int = 1):
    with _lock:
        cur = _conn.execute(
            "SELECT username, score FROM found_usernames WHERE chat_id = ? "
            "ORDER BY score DESC, id DESC LIMIT ?",
            (chat_id, limit),
        )
        return cur.fetchall()
