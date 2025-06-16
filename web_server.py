# Файл: web_server.py (НОВЫЙ ФАЙЛ)

import json
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta

import database as db
import utils
from config import SIMULATED_YEAR

# --- Настройки ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - WEB - [%(levelname)s] - %(message)s")
app = FastAPI()
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR))  # Ищем шаблоны в корне проекта
MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def now_moscow():
    """Возвращает текущую дату с симулированным годом"""
    now = datetime.now(MOSCOW_TZ)
    if SIMULATED_YEAR:
        try:
            return now.replace(year=SIMULATED_YEAR)
        except ValueError:
            return now.replace(year=SIMULATED_YEAR, day=28)
    return now


async def get_chart_data_for_user(user_id: int):
    """
    Собирает данные для графиков почасовой и недельной активности пользователя.
    """
    now = now_moscow()
    today_str = now.strftime("%Y-%m-%d")
    seven_days_ago_str = (now - timedelta(days=6)).strftime("%Y-%m-%d")

    async with db.aiosqlite.connect(db.DB_PATH) as conn:
        # 1. Данные по часам за сегодня
        hourly_labels = [f"{h:02d}" for h in range(24)]
        hourly_values = [0] * 24
        cursor = await conn.execute(
            """
            SELECT strftime('%H', timestamp) as hour, COUNT(*)
            FROM scooter_log
            WHERE user_id = ? AND date(timestamp) = ?
            GROUP BY hour
            """,
            (user_id, today_str)
        )
        async for row in cursor:
            hour_index = int(row[0])
            hourly_values[hour_index] = row[1]

        # 2. Данные по дням за последние 7 дней (из обеих таблиц)
        weekly_labels = [(now - timedelta(days=i)).strftime('%d.%m') for i in range(6, -1, -1)]
        weekly_values_dict = {label: 0 for label in weekly_labels}

        # Данные из scooter_log
        cursor = await conn.execute(
            """
            SELECT strftime('%d.%m', date(timestamp)) as day, COUNT(*)
            FROM scooter_log
            WHERE user_id = ? AND date(timestamp) >= ?
            GROUP BY day
            """,
            (user_id, seven_days_ago_str)
        )
        async for row in cursor:
            if row[0] in weekly_values_dict:
                weekly_values_dict[row[0]] += row[1]

        # Данные из historic_stats
        cursor = await conn.execute(
            """
            SELECT strftime('%d.%m', log_date) as day, count
            FROM historic_stats
            WHERE user_id = ? AND log_date >= ?
            """,
            (user_id, seven_days_ago_str)
        )
        async for row in cursor:
            if row[0] in weekly_values_dict:
                weekly_values_dict[row[0]] += row[1]

        weekly_values = [weekly_values_dict[label] for label in weekly_labels]

    return {
        "hourly_labels": hourly_labels,
        "hourly_data": hourly_values,
        "weekly_labels": weekly_labels,
        "weekly_data": weekly_values,
    }


@app.get("/stats/{user_id}", response_class=HTMLResponse)
async def get_user_stats_page(request: Request, user_id: int):
    """
    Основная функция, которая собирает все данные и рендерит HTML-страницу.
    """
    utils.load_user_data()  # Убедимся, что данные о пользователях загружены
    user_name = utils.USER_NAMES.get(user_id, "Неизвестный")
    try:
        user_first_name = user_name.split()[1]
    except IndexError:
        user_first_name = user_name

    personal_stats = await db.get_personal_stats(user_id)
    chart_data = await get_chart_data_for_user(user_id)

    now = now_moscow()
    decade_start_day = 1 if now.day <= 10 else 11 if now.day <= 20 else 21

    # Собираем все данные в один словарь (контекст) для передачи в шаблон
    context = {
        "request": request,
        "user_first_name": user_first_name,
        "current_date": now.strftime("%d.%m.%Y"),
        "today_count": personal_stats.get('today_count', 0),
        "avg_time_today": "N/A",  # Эту метрику нужно будет вычислить дополнительно, если нужно
        "duplicates_today": personal_stats.get('today_duplicates', 0),
        "rank_today": "N/A",  # Эту метрику тоже нужно будет вычислить
        "total_users_today": "N/A",
        "decade_dates": f"{decade_start_day:02d}.{now.month:02d} - {now.day:02d}.{now.month:02d}",
        "decade_progress": personal_stats.get('decade_total', 0),
        "decade_norm": db.DECADE_NORM,
        "remaining_for_premium": max(0, db.DECADE_NORM - personal_stats.get('decade_total', 0)),
        "overall_total": personal_stats.get('overall_total', 0),
        "best_day_count": personal_stats.get('best_day_count', 0),
        "best_day_date": personal_stats.get('best_day_date', 'N/A'),
        "overall_rank": personal_stats.get('rank', 'N/A'),
        # Данные для JS, преобразуем в JSON-строку
        "hourly_labels_js": json.dumps(chart_data["hourly_labels"]),
        "hourly_data_js": json.dumps(chart_data["hourly_data"]),
        "weekly_labels_js": json.dumps(chart_data["weekly_labels"]),
        "weekly_data_js": json.dumps(chart_data["weekly_data"]),
    }

    logging.info(f"Отдаю страницу статистики для пользователя {user_id}")
    return templates.TemplateResponse("stats_template.html", context)