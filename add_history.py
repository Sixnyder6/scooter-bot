# Файл: add_history.py (для загрузки данных из history_update.json в базу)

import json
import sqlite3
import logging
from pathlib import Path

# --- Настройки ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "bot_data.db"
HISTORY_UPDATE_PATH = BASE_DIR / "history_update.json"
# -----------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def add_history_to_db():
    """
    Читает history_update.json и добавляет/обновляет записи
    в таблице historic_stats.
    """
    if not HISTORY_UPDATE_PATH.exists():
        logging.error(f"Файл {HISTORY_UPDATE_PATH} не найден. Сначала запустите extract_from_gsheet.py")
        return

    with open(HISTORY_UPDATE_PATH, "r", encoding="utf-8") as f:
        history_data = json.load(f)

    # Убедимся, что папка data существует
    DATA_DIR.mkdir(exist_ok=True)

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        logging.info(f"Подключен к базе данных {DB_PATH}")

        added_count = 0
        for user_id_str, data in history_data.items():
            user_id = int(user_id_str)
            daily_history = data.get("daily_history", {})

            if not daily_history:
                continue

            for date_str, count in daily_history.items():
                try:
                    # INSERT OR REPLACE очень удобен:
                    # он вставит новую запись, если ее нет,
                    # или заменит старую, если запись с таким user_id и log_date уже существует.
                    cursor.execute(
                        "INSERT OR REPLACE INTO historic_stats (user_id, log_date, count) VALUES (?, ?, ?)",
                        (user_id, date_str, count)
                    )
                    added_count += 1
                    logging.info(f"Добавлено/Обновлено: Пользователь {user_id}, Дата {date_str}, Количество {count}")
                except Exception as e:
                    logging.warning(f"Ошибка при обработке записи для user_id={user_id}, date={date_str}: {e}")

        conn.commit()
        logging.info(f"Готово! Всего добавлено/обновлено записей: {added_count}")

    except sqlite3.Error as e:
        logging.error(f"Ошибка при работе с базой данных SQLite: {e}")
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    add_history_to_db()