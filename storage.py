# -*- coding: utf-8 -*-
"""
storage.py — единая точка работы с БД.

Приоритет: Supabase (PostgreSQL) через asyncpg, если задан DATABASE_URL.
Если подключения нет или asyncpg не установлен — безопасный фоллбэк на
локальный SQLite (bot_data.db).

Обратная совместимость со старой SQLite-схемой (из v1.0-v1.4) сохранена:
  - старая таблица findings со столбцами (id, user_id, username, score, found_at)
    читается без миграций, при отсутствии score проставляется 0;
  - настройки/калибровка подхватываются, если ранее были записаны.
"""

import os
import json
import sqlite3
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:  # pragma: no cover
    HAS_ASYNCPG = False

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SQLITE_PATH = os.getenv("SQLITE_PATH", "bot_data.db").strip()

log = logging.getLogger("username_hunter_bot.storage")


class DatabaseManager:
    """Абстрагирует SQL-различия между PostgreSQL (Supabase) и SQLite."""

    def __init__(self):
        self.is_postgres = bool(DATABASE_URL and HAS_ASYNCPG)
        self._pg_pool: Optional[Any] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # инициализация
    # ------------------------------------------------------------------
    async def init_db(self):
        if self.is_postgres:
            try:
                self._pg_pool = await asyncpg.create_pool(
                    dsn=DATABASE_URL,
                    min_size=1,
                    max_size=5,
                    timeout=10,
                )
                async with self._pg_pool.acquire() as conn:
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS user_settings (
                            user_id BIGINT PRIMARY KEY,
                            check_limit INT DEFAULT 1000,
                            no_mono BOOLEAN DEFAULT FALSE,
                            clean_output BOOLEAN DEFAULT FALSE,
                            silent_mode BOOLEAN DEFAULT FALSE
                        );
                    ''')
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS calibration_data (
                            user_id BIGINT PRIMARY KEY,
                            vowel_weight FLOAT DEFAULT 1.0,
                            consonant_penalty FLOAT DEFAULT 1.0,
                            rhythm_bonus FLOAT DEFAULT 1.0,
                            digit_penalty FLOAT DEFAULT 1.0,
                            underscore_penalty FLOAT DEFAULT 1.0,
                            is_completed BOOLEAN DEFAULT FALSE,
                            history TEXT DEFAULT '[]'
                        );
                    ''')
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS watchlist (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            username TEXT,
                            added_at TIMESTAMP DEFAULT NOW(),
                            UNIQUE(user_id, username)
                        );
                    ''')
                    await conn.execute('''
                        CREATE TABLE IF NOT EXISTS findings (
                            id SERIAL PRIMARY KEY,
                            user_id BIGINT,
                            username TEXT,
                            score FLOAT DEFAULT 0,
                            found_at TIMESTAMP DEFAULT NOW()
                        );
                    ''')
                    await conn.execute('''
                        CREATE INDEX IF NOT EXISTS idx_findings_user
                            ON findings(user_id, found_at DESC);
                    ''')
                    await conn.execute('''
                        CREATE INDEX IF NOT EXISTS idx_findings_user_uname
                            ON findings(user_id, username);
                    ''')
                log.info("✅ Успешно подключено к Supabase (PostgreSQL)")
                return
            except Exception as e:
                log.error(
                    "⚠️ Не удалось подключиться к PostgreSQL: %s. Переходим на SQLite.", e
                )
                self.is_postgres = False
                self._pg_pool = None

        self._init_sqlite()
        log.info("ℹ️ Локальная база данных SQLite готова (%s)", SQLITE_PATH)

    # ------------------------------------------------------------------
    def _init_sqlite(self):
        with sqlite3.connect(SQLITE_PATH) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            cur = conn.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    check_limit INTEGER DEFAULT 1000,
                    no_mono INTEGER DEFAULT 0,
                    clean_output INTEGER DEFAULT 0,
                    silent_mode INTEGER DEFAULT 0
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS calibration_data (
                    user_id INTEGER PRIMARY KEY,
                    vowel_weight REAL DEFAULT 1.0,
                    consonant_penalty REAL DEFAULT 1.0,
                    rhythm_bonus REAL DEFAULT 1.0,
                    digit_penalty REAL DEFAULT 1.0,
                    underscore_penalty REAL DEFAULT 1.0,
                    is_completed INTEGER DEFAULT 0,
                    history TEXT DEFAULT '[]'
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, username)
                )
            ''')
            # сохраняем старую схему, чтобы подтянулась вся старая история
            cur.execute('''
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    score REAL DEFAULT 0,
                    found_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # миграция для старых баз: добавляем столбец score, если его нет
            try:
                cur.execute("ALTER TABLE findings ADD COLUMN score REAL DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            try:
                cur.execute("ALTER TABLE findings ADD COLUMN found_at DATETIME DEFAULT CURRENT_TIMESTAMP")
            except sqlite3.OperationalError:
                pass

            cur.execute("CREATE INDEX IF NOT EXISTS idx_findings_user ON findings(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_watch_user ON watchlist(user_id)")
            conn.commit()

    # ------------------------------------------------------------------
    # settings
    # ------------------------------------------------------------------
    DEFAULT_SETTINGS = {
        "check_limit": 1000,
        "no_mono": False,
        "clean_output": False,
        "silent_mode": False,
    }

    async def get_settings(self, user_id: int) -> Dict[str, Any]:
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT check_limit, no_mono, clean_output, silent_mode "
                    "FROM user_settings WHERE user_id=$1",
                    user_id,
                )
            if not row:
                return dict(self.DEFAULT_SETTINGS)
            return {
                "check_limit": row["check_limit"],
                "no_mono": bool(row["no_mono"]),
                "clean_output": bool(row["clean_output"]),
                "silent_mode": bool(row["silent_mode"]),
            }
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT check_limit, no_mono, clean_output, silent_mode "
                        "FROM user_settings WHERE user_id=?",
                        (user_id,),
                    )
                    row = cur.fetchone()
                    if not row:
                        return dict(self.DEFAULT_SETTINGS)
                    return {
                        "check_limit": row["check_limit"] or 1000,
                        "no_mono": bool(row["no_mono"]),
                        "clean_output": bool(row["clean_output"]),
                        "silent_mode": bool(row["silent_mode"]),
                    }
            return await asyncio.to_thread(_sync)

    async def update_settings(self, user_id: int, key: str, value: Any):
        if key not in self.DEFAULT_SETTINGS:
            raise ValueError(f"Unknown setting key: {key}")
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(
                    f'''INSERT INTO user_settings (user_id, {key}) VALUES ($1, $2)
                        ON CONFLICT (user_id) DO UPDATE SET {key} = EXCLUDED.{key}''',
                    user_id, value,
                )
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        f'''INSERT INTO user_settings (user_id, {key}) VALUES (?, ?)
                            ON CONFLICT(user_id) DO UPDATE SET {key}=excluded.{key}''',
                        (user_id, value),
                    )
                    conn.commit()
            await asyncio.to_thread(_sync)

    # ------------------------------------------------------------------
    # calibration
    # ------------------------------------------------------------------
    DEFAULT_CALIB = {
        "vowel_weight": 1.0,
        "consonant_penalty": 1.0,
        "rhythm_bonus": 1.0,
        "digit_penalty": 1.0,
        "underscore_penalty": 1.0,
        "is_completed": False,
        "history": [],
    }

    async def get_calibration(self, user_id: int) -> Dict[str, Any]:
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM calibration_data WHERE user_id=$1", user_id
                )
            if not row:
                return dict(self.DEFAULT_CALIB)
            try:
                hist = json.loads(row["history"]) if row["history"] else []
            except Exception:
                hist = []
            return {
                "vowel_weight": row["vowel_weight"],
                "consonant_penalty": row["consonant_penalty"],
                "rhythm_bonus": row["rhythm_bonus"],
                "digit_penalty": row.get("digit_penalty", 1.0),
                "underscore_penalty": row.get("underscore_penalty", 1.0),
                "is_completed": bool(row["is_completed"]),
                "history": hist,
            }
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM calibration_data WHERE user_id=?", (user_id,))
                    row = cur.fetchone()
                    if not row:
                        return dict(self.DEFAULT_CALIB)
                    try:
                        hist = json.loads(row["history"]) if row["history"] else []
                    except Exception:
                        hist = []
                    d = {k: row[k] for k in row.keys()}
                    d.pop("user_id", None)
                    d["history"] = hist
                    d.setdefault("digit_penalty", 1.0)
                    d.setdefault("underscore_penalty", 1.0)
                    d["is_completed"] = bool(d["is_completed"])
                    return d
            return await asyncio.to_thread(_sync)

    async def save_calibration(self, user_id: int, data: Dict[str, Any]):
        hist_json = json.dumps(data.get("history", []), ensure_ascii=False)
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO calibration_data
                        (user_id, vowel_weight, consonant_penalty, rhythm_bonus,
                         digit_penalty, underscore_penalty, is_completed, history)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    ON CONFLICT (user_id) DO UPDATE SET
                        vowel_weight=EXCLUDED.vowel_weight,
                        consonant_penalty=EXCLUDED.consonant_penalty,
                        rhythm_bonus=EXCLUDED.rhythm_bonus,
                        digit_penalty=EXCLUDED.digit_penalty,
                        underscore_penalty=EXCLUDED.underscore_penalty,
                        is_completed=EXCLUDED.is_completed,
                        history=EXCLUDED.history
                ''', user_id,
                     data.get("vowel_weight", 1.0),
                     data.get("consonant_penalty", 1.0),
                     data.get("rhythm_bonus", 1.0),
                     data.get("digit_penalty", 1.0),
                     data.get("underscore_penalty", 1.0),
                     bool(data.get("is_completed", False)),
                     hist_json)
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    cur = conn.cursor()
                    # добавляем столбцы если это старая база
                    for col, dflt in [
                        ("digit_penalty", 1.0), ("underscore_penalty", 1.0),
                    ]:
                        try:
                            cur.execute(f"ALTER TABLE calibration_data ADD COLUMN {col} REAL DEFAULT {dflt}")
                        except sqlite3.OperationalError:
                            pass
                    cur.execute('''
                        INSERT INTO calibration_data
                            (user_id, vowel_weight, consonant_penalty, rhythm_bonus,
                             digit_penalty, underscore_penalty, is_completed, history)
                        VALUES (?,?,?,?,?,?,?,?)
                        ON CONFLICT(user_id) DO UPDATE SET
                            vowel_weight=excluded.vowel_weight,
                            consonant_penalty=excluded.consonant_penalty,
                            rhythm_bonus=excluded.rhythm_bonus,
                            digit_penalty=excluded.digit_penalty,
                            underscore_penalty=excluded.underscore_penalty,
                            is_completed=excluded.is_completed,
                            history=excluded.history
                    ''', (
                        user_id,
                        data.get("vowel_weight", 1.0),
                        data.get("consonant_penalty", 1.0),
                        data.get("rhythm_bonus", 1.0),
                        data.get("digit_penalty", 1.0),
                        data.get("underscore_penalty", 1.0),
                        1 if data.get("is_completed") else 0,
                        hist_json,
                    ))
                    conn.commit()
            await asyncio.to_thread(_sync)

    async def reset_calibration(self, user_id: int):
        await self.save_calibration(user_id, dict(self.DEFAULT_CALIB))

    # ------------------------------------------------------------------
    # findings
    # ------------------------------------------------------------------
    async def add_found(self, user_id: int, username: str, score: float = 0.0):
        username = username.lstrip("@").lower()
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO findings (user_id, username, score) VALUES ($1,$2,$3)",
                    user_id, username, float(score),
                )
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO findings (user_id, username, score) VALUES (?,?,?)",
                        (user_id, username, float(score)),
                    )
                    conn.commit()
            await asyncio.to_thread(_sync)

    def already_known_sync(self, user_id: int, username: str) -> bool:
        """Синхронная проверка — для быстрого использования в hot-path."""
        if self.is_postgres:
            # в горячем цикле используем кэш в памяти (set известных) вместо async-запросов
            return False
        username = username.lstrip("@").lower()
        with sqlite3.connect(SQLITE_PATH) as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM findings WHERE user_id=? AND username=? LIMIT 1",
                (user_id, username),
            )
            return cur.fetchone() is not None

    async def already_known(self, user_id: int, username: str) -> bool:
        username = username.lstrip("@").lower()
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT 1 FROM findings WHERE user_id=$1 AND username=$2 LIMIT 1",
                    user_id, username,
                )
                return row is not None
        return await asyncio.to_thread(self.already_known_sync, user_id, username)

    async def count(self, user_id: int) -> int:
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                return await conn.fetchval(
                    "SELECT COUNT(*) FROM findings WHERE user_id=$1", user_id
                ) or 0
        def _sync():
            with sqlite3.connect(SQLITE_PATH) as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM findings WHERE user_id=?", (user_id,))
                return cur.fetchone()[0]
        return await asyncio.to_thread(_sync)

    async def get_page(self, user_id: int, page: int, page_size: int) -> List[Tuple[str, float, str]]:
        offset = page * page_size
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT username, score, found_at FROM findings "
                    "WHERE user_id=$1 ORDER BY found_at DESC, id DESC "
                    "LIMIT $2 OFFSET $3",
                    user_id, page_size, offset,
                )
            return [(r["username"], float(r["score"] or 0), str(r["found_at"])) for r in rows]
        def _sync():
            with sqlite3.connect(SQLITE_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT username, score, found_at FROM findings "
                    "WHERE user_id=? ORDER BY found_at DESC, id DESC LIMIT ? OFFSET ?",
                    (user_id, page_size, offset),
                )
                out = []
                for r in cur.fetchall():
                    out.append((r["username"], float(r["score"] or 0), r["found_at"] or ""))
                return out
        return await asyncio.to_thread(_sync)

    async def get_all(self, user_id: int) -> List[Tuple[str, float, str]]:
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT username, score, found_at FROM findings "
                    "WHERE user_id=$1 ORDER BY found_at DESC, id DESC",
                    user_id,
                )
            return [(r["username"], float(r["score"] or 0), str(r["found_at"])) for r in rows]
        def _sync():
            with sqlite3.connect(SQLITE_PATH) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute(
                    "SELECT username, score, found_at FROM findings "
                    "WHERE user_id=? ORDER BY found_at DESC, id DESC",
                    (user_id,),
                )
                return [(r["username"], float(r["score"] or 0), r["found_at"] or "") for r in cur.fetchall()]
        return await asyncio.to_thread(_sync)

    async def get_session_findings(self, session_items: List[Tuple[str, float]]) -> List[Tuple[str, float, str]]:
        """Для экспорта текущей сессии."""
        return [(u, float(s), "") for u, s in session_items]

    # ------------------------------------------------------------------
    # watchlist
    # ------------------------------------------------------------------
    async def add_watch(self, user_id: int, username: str):
        username = username.lstrip("@").lower()
        if self.is_postgres:
            async with self._pg_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO watchlist (user_id, username) VALUES ($1,$2) "
                    "ON CONFLICT (user_id, username) DO NOTHING",
                    user_id, username,
                )
        else:
            def _sync():
                with sqlite3.connect(SQLITE_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT OR IGNORE INTO watchlist (user_id, username) VALUES (?,?)",
                        (user_id, username),
                    )
                    conn.commit()
            await asyncio.to_thread(_sync)


db = DatabaseManager()
