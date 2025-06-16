# Файл: g_sheets.py (Версия, готовая к деплою на Railway)

import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import asyncio
import os
import json
from pathlib import Path
from typing import Dict, Tuple, Optional
# Добавлен импорт GOOGLE_CREDENTIALS_PATH для локальной работы
from config import GOOGLE_SHEET_URL, GOOGLE_SHEET_NAME, GOOGLE_CREDENTIALS_PATH
from datetime import datetime
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def now_moscow():
    return datetime.now(MOSCOW_TZ)


def get_gsheet_client() -> gspread.Client:
    """
    ЕДИНАЯ ФУНКЦИЯ ДЛЯ ПОДКЛЮЧЕНИЯ К GOOGLE SHEETS.
    Работает и на сервере (через переменные окружения), и локально (через файл).
    """
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

    # 1. Пытаемся получить креды из переменной окружения (для Railway)
    creds_json_str = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json_str:
        logging.info("Использую Google креды из переменной окружения.")
        try:
            creds_dict = json.loads(creds_json_str)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception as e:
            logging.error(f"Ошибка парсинга GOOGLE_CREDENTIALS_JSON: {e}")
            raise

    # 2. Если переменной нет, используем локальный путь (для тестов на компьютере)
    elif GOOGLE_CREDENTIALS_PATH and Path(GOOGLE_CREDENTIALS_PATH).exists():
        logging.info(f"Использую Google креды из локального файла: {GOOGLE_CREDENTIALS_PATH}")
        creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDENTIALS_PATH, scope)
        return gspread.authorize(creds)

    # 3. Если ничего не найдено, выбрасываем ошибку
    else:
        raise Exception(
            "Не найдены креды для Google Sheets. Проверьте переменную окружения GOOGLE_CREDENTIALS_JSON или путь GOOGLE_CREDENTIALS_PATH в .env")


async def append_to_google_sheets_async(user_short_name: str, scooter_number: str, columns: Optional[Tuple[int, int]]):
    """Асинхронно добавляет данные в Google Sheets."""
    if not columns:
        logging.warning(f"Для пользователя {user_short_name} не заданы колонки в Google Sheets. Пропускаю запись.")
        return

    loop = asyncio.get_running_loop()
    for attempt in range(3):
        try:
            def sync_append():
                client = get_gsheet_client()
                spreadsheet = client.open_by_url(GOOGLE_SHEET_URL)
                sheet = spreadsheet.worksheet(GOOGLE_SHEET_NAME)
                number_col, date_col = columns
                next_row = len(sheet.col_values(number_col)) + 1
                existing_numbers = sheet.col_values(number_col)
                if scooter_number in existing_numbers:
                    logging.warning(f"Найден дубликат {scooter_number}.")
                sheet.update_cell(next_row, number_col, scooter_number)
                sheet.update_cell(next_row, date_col, now_moscow().strftime("%d.%m. %H:%M"))
                logging.info(f"Данные для {user_short_name} успешно добавлены в Google Sheets.")

            await loop.run_in_executor(None, sync_append)
            return
        except Exception as e:
            logging.error(f"Ошибка при записи в Google Sheets (попытка {attempt + 1}): {e}")
            await asyncio.sleep(2)
    logging.error(f"Не удалось записать данные в Google Sheets для {user_short_name}.")


async def get_live_report_from_gsheet_async() -> Dict:
    """Читает данные напрямую из Google Sheets для отчета 'За сегодня'."""
    from utils import USER_DATA
    loop = asyncio.get_running_loop()

    def sync_read_and_analyze():
        client = get_gsheet_client()
        spreadsheet = client.open_by_url(GOOGLE_SHEET_URL)
        sheet = spreadsheet.worksheet(GOOGLE_SHEET_NAME)
        all_data = sheet.get_all_values()
        today_check_str = now_moscow().strftime("%d.%m")
        results = {}
        current_year = now_moscow().year

        for user_id_str, user_info in USER_DATA.items():
            user_id = int(user_id_str)
            cols = user_info.get("g_sheet_cols")
            if not cols: continue

            num_col_idx, date_col_idx = cols[0] - 1, cols[1] - 1
            user_scooters_today = []
            latest_timestamp_dt: Optional[datetime] = None

            for row in all_data[1:]:
                if len(row) > max(num_col_idx, date_col_idx):
                    scooter_num, date_str = row[num_col_idx], row[date_col_idx]

                    if scooter_num and date_str.strip().startswith(today_check_str):
                        user_scooters_today.append(scooter_num)
                        try:
                            current_dt = datetime.strptime(date_str.strip(), "%d.%m. %H:%M").replace(year=current_year)
                            if latest_timestamp_dt is None or current_dt > latest_timestamp_dt:
                                latest_timestamp_dt = current_dt
                        except ValueError:
                            logging.warning(f"Не удалось распознать формат даты '{date_str}' в Google Sheet.")
                            pass

            if user_scooters_today:
                count = len(user_scooters_today)
                duplicates = count - len(set(user_scooters_today))
                iso_timestamp = latest_timestamp_dt.isoformat() if latest_timestamp_dt else ""

                results[user_id] = {
                    "count": count,
                    "last_add": iso_timestamp,
                    "duplicates": duplicates
                }

        return {"users": results}

    try:
        stats = await loop.run_in_executor(None, sync_read_and_analyze)
        return stats
    except Exception as e:
        logging.error(f"Ошибка при чтении данных из Google Sheets для отчета: {e}")
        return {"users": {}}