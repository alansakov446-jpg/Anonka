import os
import sqlite3
import json
import logging
from typing import Dict, Any, Optional

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False

DATABASE_URL = os.getenv("DATABASE_URL")

class DatabaseManager:
    def __init__(self):
        self.is_postgres = bool(DATABASE_URL and HAS_ASYNCPG)

    async def init_db(self):
        """Автоматическое создание всех нужных таблиц"""
        if self.is_postgres:
            try:
                conn = await asyncpg.connect(DATABASE_URL)
                await conn.execute('''
                    CREATE TABLE IF NOT EXISTS user_settings (
                        user_id BIGINT PRIMARY KEY,
                        check_limit INT DEFAULT 1000,
                        no_mono BOOLEAN DEFAULT FALSE,
                        clean_output BOOLEAN DEFAULT FALSE,
                        silent_mode BOOLEAN DEFAULT FALSE
                    );
                    
                    CREATE TABLE IF NOT EXISTS calibration_data (
                        user_id BIGINT PRIMARY KEY,
                        vowel_weight FLOAT DEFAULT 1.0,
                        consonant_penalty FLOAT DEFAULT 1.0,
                        rhythm_bonus FLOAT DEFAULT 1.0,
                        is_completed BOOLEAN DEFAULT FALSE,
                        history TEXT DEFAULT '[]'
                    );

                    CREATE TABLE IF NOT EXISTS watchlist (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT UNIQUE,
                        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );

                    CREATE TABLE IF NOT EXISTS findings (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT,
                        username TEXT,
                        found_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                await conn.close()
                logging.info("✅ Успешно подключено к облаку Supabase (PostgreSQL)")
                return
            except Exception as e:
                logging.error(f"⚠️ Не удалось подключиться к PostgreSQL: {e}. Переходим на SQLite.")
                self.is_postgres = False

        self._init_sqlite()

    def _init_sqlite(self):
        """Фоллбек-инициализация SQLite"""
        with sqlite3.connect("bot_data.db") as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    check_limit INTEGER DEFAULT 1000,
                    no_mono BOOLEAN DEFAULT 0,
                    clean_output BOOLEAN DEFAULT 0,
                    silent_mode BOOLEAN DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS calibration_data (
                    user_id INTEGER PRIMARY KEY,
                    vowel_weight REAL DEFAULT 1.0,
                    consonant_penalty REAL DEFAULT 1.0,
                    rhythm_bonus REAL DEFAULT 1.0,
                    is_completed BOOLEAN DEFAULT 0,
                    history TEXT DEFAULT '[]'
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT UNIQUE,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    found_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            logging.info("ℹ️ Локальная база данных SQLite готова к работе")

    async def get_settings(self, user_id: int) -> Dict[str, Any]:
        default = {"check_limit": 1000, "no_mono": False, "clean_output": False, "silent_mode": False}
        if self.is_postgres:
            conn = await asyncpg.connect(DATABASE_URL)
            row = await conn.fetchrow("SELECT check_limit, no_mono, clean_output, silent_mode FROM user_settings WHERE user_id = $1", user_id)
            await conn.close()
            return dict(row) if row else default
        else:
            with sqlite3.connect("bot_data.db") as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT check_limit, no_mono, clean_output, silent_mode FROM user_settings WHERE user_id = ?", (user_id,))
                row = cursor.fetchone()
                return dict(row) if row else default

    async def update_settings(self, user_id: int, key: str, value: Any):
        if self.is_postgres:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute(f'''
                INSERT INTO user_settings (user_id, {key}) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET {key} = EXCLUDED.{key}
            ''', user_id, value)
            await conn.close()
        else:
            with sqlite3.connect("bot_data.db") as conn:
                cursor = conn.cursor()
                cursor.execute(f'''
                    INSERT INTO user_settings (user_id, {key}) VALUES (?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET {key} = excluded.{key}
                ''', (user_id, value))
                conn.commit()

    async def save_finding(self, user_id: int, username: str):
        if self.is_postgres:
            conn = await asyncpg.connect(DATABASE_URL)
            await conn.execute("INSERT INTO findings (user_id, username) VALUES ($1, $2)", user_id, username)
            await conn.close()
        else:
            with sqlite3.connect("bot_data.db") as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO findings (user_id, username) VALUES (?, ?)", (user_id, username))
                conn.commit()

db = DatabaseManager()
