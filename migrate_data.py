# Файл: migrate_data.py (для одноразового запуска)

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path

# --- Настройки ---
# Убедитесь, что пути правильные
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot_data.db"
OLD_USER_STATS_PATH = Path("user_stats.json")  # Ищет в той же папке, что и migrate_data.py
OLD_LAST_ACTIVITY_PATH = Path("last_activity.json")  # Ищет там же
# -----------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def migrate():
    """Переносит данные из старых JSON файлов в новую SQLite базу."""
    if not OLD_USER_STATS_PATH.exists() and not OLD_LAST_ACTIVITY_PATH.exists():
        logging.info("Старые файлы данных (user_stats.json, last_activity.json) не найдены. Миграция не требуется.")
        return

    # Создаем папку data, если ее нет
    DATA_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создаем таблицы, если их нет
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historic_stats (
            user_id INTEGER NOT NULL,
            log_date TEXT NOT NULL,
            count INTEGER NOT NULL,
            PRIMARY KEY (user_id, log_date)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            user_id INTEGER PRIMARY KEY,
            last_seen_date TEXT NOT NULL
        )
    """)

    # Миграция user_stats.json
    if OLD_USER_STATS_PATH.exists():
        logging.info(f"Начинаю миграцию из {OLD_USER_STATS_PATH}...")
        with open(OLD_USER_STATS_PATH, "r", encoding="utf-8") as f:
            user_stats = json.load(f)

        for user_id_str, data in user_stats.items():
            user_id = int(user_id_str)
            history = data.get("daily_history", {})
            for date_str, count in history.items():
                try:
                    # Просто сохраняем дату как строку, без конвертации
                    cursor.execute(
                        "INSERT OR REPLACE INTO historic_stats (user_id, log_date, count) VALUES (?, ?, ?)",
                        (user_id, date_str, count)
                    )
                except Exception as e:
                    logging.warning(f"Ошибка при обработке {date_str} для пользователя {user_id}: {e}")
        logging.info("Миграция статистики завершена.")

    # Миграция last_activity.json
    if OLD_LAST_ACTIVITY_PATH.exists():
        logging.info(f"Начинаю миграцию из {OLD_LAST_ACTIVITY_PATH}...")
        with open(OLD_LAST_ACTIVITY_PATH, "r", encoding="utf-8") as f:
            last_activity = json.load(f)

        for user_id_str, date_str in last_activity.items():
            user_id = int(user_id_str)
            try:
                cursor.execute(
                    "INSERT OR REPLACE INTO activity (user_id, last_seen_date) VALUES (?, ?)",
                    (user_id, date_str)
                )
            except Exception as e:
                logging.warning(f"Ошибка при обработке {date_str} для пользователя {user_id}: {e}")
        logging.info("Миграция последней активности завершена.")

    conn.commit()
    conn.close()
    logging.info("Миграция данных успешно завершена!")


if __name__ == "__main__":
    migrate()