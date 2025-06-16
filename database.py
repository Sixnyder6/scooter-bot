# Файл: database.py (С УЧЕТОМ СИМУЛИРОВАННОГО ГОДА)

import aiosqlite
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional
import calendar
# Добавлен импорт SIMULATED_YEAR
from config import DB_PATH, RUS_MONTHS, DECADE_NORM, PREMIUM_RATE, SIMULATED_YEAR

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def now_moscow():
    """
    Возвращает текущую дату и время, но с годом, указанным в конфиге.
    Если SIMULATED_YEAR не задан, используется реальный год.
    """
    now = datetime.now(MOSCOW_TZ)
    if SIMULATED_YEAR:
        try:
            return now.replace(year=SIMULATED_YEAR)
        except ValueError:  # На случай, если 29 февраля в невисокосном году
            return now.replace(year=SIMULATED_YEAR, day=28)
    return now


async def init_db():
    """Инициализирует базу данных, создавая таблицы, если их нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scooter_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                scooter_number TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS activity (
                user_id INTEGER PRIMARY KEY,
                last_seen_date TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS historic_stats (
                user_id INTEGER NOT NULL,
                log_date TEXT NOT NULL,
                count INTEGER NOT NULL,
                PRIMARY KEY (user_id, log_date)
            )
        """)
        await db.commit()
    logging.info("База данных успешно инициализирована.")


async def add_scooter(user_id: int, scooter_number: str):
    """Добавляет запись о самокате в базу данных."""
    timestamp_str = now_moscow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO scooter_log (user_id, scooter_number, timestamp) VALUES (?, ?, ?)",
            (user_id, scooter_number, timestamp_str)
        )
        await db.commit()


async def update_last_activity(user_id: int):
    """Обновляет дату последней активности пользователя."""
    today_str = now_moscow().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO activity (user_id, last_seen_date) VALUES (?, ?)",
            (user_id, today_str)
        )
        await db.commit()


async def get_last_activity(user_id: int) -> Optional[str]:
    """Получает дату последней активности пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_seen_date FROM activity WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None


async def get_personal_stats(user_id: int) -> Dict:
    """Собирает всю статистику для одного пользователя из БД."""
    now = now_moscow()
    today_start_str = now.strftime("%Y-%m-%d")
    decade_start_str = now.replace(day=(1 if now.day <= 10 else 11 if now.day <= 20 else 21)).strftime("%Y-%m-%d")

    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Статистика за сегодня
        cursor = await db.execute(
            "SELECT scooter_number, timestamp FROM scooter_log WHERE user_id = ? AND date(timestamp) = ?",
            (user_id, today_start_str)
        )
        today_rows = await cursor.fetchall()
        today_numbers = [row[0] for row in today_rows]

        # 2. Общая статистика и ранг
        all_users_totals = {}
        historic_totals_cursor = await db.execute("SELECT user_id, SUM(count) FROM historic_stats GROUP BY user_id")
        async for row in historic_totals_cursor: all_users_totals[row[0]] = row[1]
        live_totals_cursor = await db.execute("SELECT user_id, COUNT(*) FROM scooter_log GROUP BY user_id")
        async for row in live_totals_cursor: all_users_totals[row[0]] = all_users_totals.get(row[0], 0) + row[1]

        overall_total = all_users_totals.get(user_id, 0)
        sorted_ranks = sorted(all_users_totals.items(), key=lambda item: item[1], reverse=True)
        rank = next((i + 1 for i, (uid, total) in enumerate(sorted_ranks) if uid == user_id), "N/A")

        # 3. Статистика за текущую декаду
        cursor = await db.execute(
            """
            SELECT
                (SELECT IFNULL(SUM(count), 0) FROM historic_stats WHERE user_id = ? AND log_date >= ?) +
                (SELECT IFNULL(COUNT(*), 0) FROM scooter_log WHERE user_id = ? AND date(timestamp) >= ?)
            """,
            (user_id, decade_start_str, user_id, decade_start_str)
        )
        decade_total = (await cursor.fetchone())[0]

        # 4. Лучший день
        best_historic_day_cursor = await db.execute(
            "SELECT log_date, count FROM historic_stats WHERE user_id = ? ORDER BY count DESC, log_date DESC LIMIT 1",
            (user_id,))
        best_historic_day = await best_historic_day_cursor.fetchone()
        best_live_day_cursor = await db.execute(
            "SELECT date(timestamp), COUNT(*) as c FROM scooter_log WHERE user_id = ? GROUP BY date(timestamp) ORDER BY c DESC LIMIT 1",
            (user_id,))
        best_live_day = await best_live_day_cursor.fetchone()

        best_day_count, best_day_date = 0, "нет данных"
        if best_historic_day and best_historic_day[1] > best_day_count:
            best_day_count, best_day_date = best_historic_day[1], datetime.strptime(str(best_historic_day[0]),
                                                                                    "%Y-%m-%d").strftime("%d.%m")
        if best_live_day and best_live_day[1] > best_day_count:
            best_day_count, best_day_date = best_live_day[1], datetime.strptime(str(best_live_day[0]),
                                                                                "%Y-%m-%d").strftime("%d.%m")

        # 5. Среднее в день
        active_days_cursor = await db.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT log_date FROM historic_stats WHERE user_id = ? UNION SELECT DISTINCT date(timestamp) FROM scooter_log WHERE user_id = ?)",
            (user_id, user_id)
        )
        total_active_days = (await active_days_cursor.fetchone())[0]
        average_per_day = overall_total // total_active_days if total_active_days > 0 else 0

    last_addition_str = "нет данных"
    if today_rows:
        latest_timestamp_str = max([row[1] for row in today_rows])
        last_addition_str = datetime.fromisoformat(latest_timestamp_str).strftime("%H:%M")

    return {
        "today_count": len(today_numbers),
        "today_duplicates": len(today_numbers) - len(set(today_numbers)),
        "last_addition": last_addition_str,
        "decade_total": decade_total,
        "overall_total": overall_total,
        "best_day_count": best_day_count,
        "best_day_date": best_day_date,
        "average_per_day": average_per_day,
        "rank": rank,
    }


async def get_report_stats(period: str, decade_num: Optional[int] = None) -> Dict:
    """Собирает статистику для отчетов (за сегодня или декаду)."""
    now = now_moscow()

    if period == "today":
        today_str = now.strftime("%Y-%m-%d")
        results = {}
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                SELECT
                    user_id,
                    COUNT(*),
                    MAX(timestamp)
                FROM scooter_log
                WHERE date(timestamp) = ?
                GROUP BY user_id
                """,
                (today_str,)
            )
            async for row in cursor:
                user_id, count, last_add = row
                results[user_id] = {"count": count, "last_add": last_add}
            dup_cursor = await db.execute(
                """
                SELECT user_id, SUM(c) - COUNT(c)
                FROM (SELECT user_id, scooter_number, COUNT(*) as c FROM scooter_log WHERE date(timestamp) = ? GROUP BY user_id, scooter_number)
                WHERE c > 1 GROUP BY user_id
                """,
                (today_str,)
            )
            async for row in dup_cursor:
                user_id, dup_count = row
                if user_id in results:
                    results[user_id]["duplicates"] = dup_count
        return {"users": results}

    # --- ПРАВИЛЬНАЯ ЛОГИКА ДЛЯ ДЕКАД (ВСЕГДА ТЕКУЩИЙ МЕСЯЦ) ---
    if period == "decade":
        user_totals = {}

        # 1. Определяем целевой месяц и год - это ВСЕГДА текущие (с учетом SIMULATED_YEAR).
        target_year, target_month = now.year, now.month

        # 2. Определяем дни начала и конца декады.
        if decade_num == 1:
            start_day, end_day = 1, 10
        elif decade_num == 2:
            start_day, end_day = 11, 20
        else:  # decade_num == 3
            start_day = 21
            # Получаем последний день ТЕКУЩЕГО месяца.
            _, end_day = calendar.monthrange(target_year, target_month)

        start_date_str = f"{target_year}-{target_month:02d}-{start_day:02d}"
        end_date_str = f"{target_year}-{target_month:02d}-{end_day:02d}"

        # 3. Выполняем запросы к БД с правильным диапазоном.
        async with aiosqlite.connect(DB_PATH) as db:
            live_cursor = await db.execute(
                "SELECT user_id, COUNT(*) FROM scooter_log WHERE date(timestamp) BETWEEN ? AND ? GROUP BY user_id",
                (start_date_str, end_date_str))
            async for row in live_cursor:
                user_totals[row[0]] = user_totals.get(row[0], 0) + row[1]

            historic_cursor = await db.execute(
                "SELECT user_id, SUM(count) FROM historic_stats WHERE log_date BETWEEN ? AND ? GROUP BY user_id",
                (start_date_str, end_date_str))
            async for row in historic_cursor:
                user_totals[row[0]] = user_totals.get(row[0], 0) + row[1]

        # Возвращаем итоги, а также месяц/год, за которые они собраны.
        return {
            "totals": user_totals,
            "month_name": RUS_MONTHS[target_month - 1],
            "year": target_year
        }

    return {}