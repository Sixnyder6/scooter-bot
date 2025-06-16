# Файл: utils.py (Версия с интеграцией Web App для кнопки "Моя статистика")

import json
import os
from pathlib import Path
from typing import Dict, Optional
from telegram import ReplyKeyboardMarkup, WebAppInfo, KeyboardButton
from config import *

# <<< Эта строка важна для функции get_user_shift_message >>>
from database import get_last_activity

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def now_moscow():
    return datetime.now(MOSCOW_TZ)


# Глобальные переменные для кэширования данных о пользователях
USER_DATA: Dict = {}
USER_NAMES: Dict[int, str] = {}


def load_user_data():
    """Загружает данные пользователей из grafik.json и кэширует их."""
    global USER_DATA, USER_NAMES
    try:
        with open(GRAFIK_PATH, "r", encoding="utf-8") as f:
            USER_DATA = json.load(f)
    except FileNotFoundError:
        print(f"Критическая ошибка: Файл с данными пользователей не найден по пути {GRAFIK_PATH}")
        return

    for user_id_str, data in USER_DATA.items():
        user_id = int(user_id_str)
        USER_NAMES[user_id] = data.get("short_name", "Неизвестный")


def get_user_permissions(user_id: int) -> str:
    """Возвращает уровень доступа пользователя."""
    return USER_DATA.get(str(user_id), {}).get("permissions", "none")


def is_user_allowed(user_id: int) -> bool:
    return str(user_id) in USER_DATA


def is_special_user(user_id: int) -> bool:
    perms = get_user_permissions(user_id)
    return perms in ["admin", "special"]


def is_admin(user_id: int) -> bool:
    return get_user_permissions(user_id) == "admin"


def get_user_reply_markup(user_id: int, in_broadcast_mode: bool = False) -> ReplyKeyboardMarkup:
    """Возвращает клавиатуру в зависимости от прав и режима пользователя."""

    if in_broadcast_mode and is_special_user(user_id):
        return ReplyKeyboardMarkup([[BUTTON_RETURN]], resize_keyboard=True)

    perms = get_user_permissions(user_id)

    # ==============================================================================
    # <<< ИЗМЕНЕНИЕ ЗДЕСЬ: Превращаем кнопку "Моя статистика" в Web App кнопку >>>
    # ==============================================================================

    # 1. Формируем URL для Web App, добавляя в конец ID пользователя
    stats_web_app_url = f"{WEB_APP_URL}/stats/{user_id}"

    # 2. Создаем специальную кнопку, которая будет открывать этот URL
    stats_button = KeyboardButton(BUTTON_MY_STATS, web_app=WebAppInfo(url=stats_web_app_url))

    # 3. Кнопка для админ-панели (если она используется)
    # WEB_APP_URL здесь должен вести на главную страницу админки, а не на статистику
    admin_panel_button = KeyboardButton(BUTTON_ADMIN_PANEL, web_app=WebAppInfo(url=WEB_APP_URL))

    if perms == "admin":
        keyboard = [
            [admin_panel_button],
            [BUTTON_VYGRUZKA, BUTTON_TABLE],
            [BUTTON_BROADCAST, stats_button],  # <-- ЗАМЕНА
            [BUTTON_MY_SHIFTS, BUTTON_INFO],
            [BUTTON_CONTACT_ADMIN]
        ]
    elif perms == "special":
        keyboard = [
            [admin_panel_button],
            [BUTTON_VYGRUZKA, BUTTON_TABLE],
            [BUTTON_BROADCAST, stats_button],  # <-- ЗАМЕНА
            [BUTTON_CONTACT_ADMIN],
        ]
    elif perms == "user":
        keyboard = [
            [stats_button, BUTTON_MY_SHIFTS],  # <-- ЗАМЕНА
            [BUTTON_INFO, BUTTON_CONTACT_ADMIN]
        ]
    else:
        return ReplyKeyboardMarkup([[BUTTON_CONTACT_ADMIN]], resize_keyboard=True)

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def get_user_shift_message(user_id: int, days: int = 15) -> str:
    """Формирует сообщение о графике смен."""
    user_id_str = str(user_id)
    if user_id_str not in USER_DATA: return "Для вас график пока не назначен."
    shifts = USER_DATA[user_id_str].get("shifts", {})
    if not shifts: return "ℹ️ Для вас не задан график смен."

    today = now_moscow().date()
    # Вот здесь используется get_last_activity, поэтому импорт был важен
    last_activity_str = await get_last_activity(user_id)
    lines = ["🎯 *Ваш персональный график смен*  \n"]

    for i in range(days):
        d = today + timedelta(days=i)
        d_str, d_view = d.strftime("%Y-%m-%d"), d.strftime("%d.%m")
        shift_type = shifts.get(d_str, "off")
        symbol = SHIFT_SYMBOLS.get(shift_type, "❔ Без данных")
        lines.append(f"📅 {d_view} → {symbol}")

    lines.append("\n➖➖➖➖➖  \n✅ *Обновлено автоматически*")
    return "\n".join(lines)


def format_personal_stats_message(user_name: str, stats: Dict) -> str:
    """Форматирует сообщение с личной статистикой. (Больше не используется для кнопки "Моя статистика")"""
    try:
        first_name = user_name.split()[1]
    except IndexError:
        first_name = user_name

    header = f"👤 *Ваша статистика*\n🟢 *В сети*\n\n*Имя:* {first_name}\n\n"
    today_part = (
        f"📅 *Сегодня:*\n— ✅ Самокатов: *{stats['today_count']}*\n— 🔄 Дубликатов: *{stats['today_duplicates']}*\n— ⏳ Последнее добавление: *{stats['last_addition']}*\n\n")

    if stats['decade_total'] >= DECADE_NORM:
        sverkh_normy = stats['decade_total'] - DECADE_NORM
        premiya = sverkh_normy * PREMIUM_RATE
        premiya_str = f"{premiya: ,}₽".replace(',', ' ')
        decade_part = (
            f"📊 *За декаду (10 дней):*\n⚡️ {stats['decade_total']} / {DECADE_NORM}\n🔥 Сверх нормы: *+{sverkh_normy}*\n💰 Премия: *{premiya_str}*\n\n")
        footer_part = "📌 *Прогресс обновляется ежедневно!*"
    else:
        ostalos = DECADE_NORM - stats['decade_total']
        decade_part = (
            f"📊 *За декаду (10 дней):*\n⚡️ {stats['decade_total']} / {DECADE_NORM}\n🔹 Осталось до премии: *{ostalos}*\n💰 Премия пока не начислена\n\n")
        footer_part = f"📌 *Добейте еще {ostalos} самокатов, чтобы получить премию!*"

    all_time_part = (
        f"📊 *За все время:*\n— 🚀 Общий результат: *{stats['overall_total']} самокатов*\n— 🌟 Лучший день: *{stats['best_day_date']} – {stats['best_day_count']} самокатов*\n— 📈 Среднее в день: *{stats['average_per_day']} самокатов*\n— 🏆 Ранг среди пользователей: *{stats['rank']} место*\n")
    return header + today_part + decade_part + all_time_part + "\n" + footer_part


def format_today_report_message(stats: Dict) -> str:
    """Форматирует отчет за сегодня."""
    users_data = stats.get("users", {})
    if not users_data: return "За сегодня еще нет данных."
    sorted_user_ids = sorted(users_data.keys(), key=lambda uid: users_data[uid]['count'], reverse=True)
    lines, overall_total, overall_duplicates = [], 0, 0

    for user_id in sorted_user_ids:
        data = users_data[user_id]
        user_name = USER_NAMES.get(user_id, f"ID {user_id}")
        count = data.get("count", 0)
        duplicates = data.get("duplicates", 0)
        last_add_str = data.get("last_add", "")
        last_add_formatted = datetime.fromisoformat(last_add_str).strftime(
            "%d.%m. %H:%M") if last_add_str else "нет данных"
        user_block = (f"🟢 {user_name}\nДата: {last_add_formatted}\nВсего самокатов: {count}\nДубликаты: {duplicates}")
        lines.append(user_block)
        overall_total += count
        overall_duplicates += duplicates

    lines.append(f"\n\nВсего самокатов: {overall_total}")
    lines.append(f"Всего дубликатов: {overall_duplicates}")
    lines.append(f"Исполнителей: {len(sorted_user_ids)}")
    return "\n\n".join(lines)


def format_decade_report_message(decade_num: int, stats: Dict) -> str:
    """Форматирует отчет за декаду (теперь использует месяц/год из stats)."""
    totals = stats.get("totals", {})
    month_name = stats.get("month_name", "N/A")
    year = stats.get("year", "N/A")

    if not totals:
        return f"Нет данных за {decade_num}-ю декаду ({month_name.lower()} {year} г.)."

    header = f"📊 *Отчет за {decade_num} Декаду ({month_name} {year})*\n\n"
    stats_lines, premium_users = ["👥 *Статистика сотрудников:*"], []
    sorted_users = sorted(totals.items(), key=lambda item: item[1], reverse=True)

    for user_id, total in sorted_users:
        user_name = USER_NAMES.get(user_id, f"ID {user_id}")
        stats_lines.append(f"📌 {user_name} — {total}/{DECADE_NORM}")
        if total > DECADE_NORM:
            premium_amount = (total - DECADE_NORM) * PREMIUM_RATE
            premium_users.append((user_name, premium_amount))

    premium_lines = []
    if premium_users:
        premium_lines.append("\n💰 *Премия за перевыполнение нормы:*")
        for name, amount in sorted(premium_users, key=lambda item: item[1], reverse=True):
            amount_str = f"{amount: ,}₽".replace(',', ' ')
            premium_lines.append(f"🏅 {name} — {amount_str}")

    return header + "\n".join(stats_lines) + "\n" + "\n".join(premium_lines)