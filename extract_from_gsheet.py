# Файл: extract_from_gsheet.py (теперь использует общую функцию)

import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Импортируем нашу единую функцию подключения
from g_sheets import get_gsheet_client

# Загружаем переменные из .env
load_dotenv()
import config


def extract_daily_stats():
    """
    Читает Google Таблицу и обновляет файл history_update.json.
    """
    date_input = input("Введите дату для извлечения статистики в формате ДД.ММ (например, 12.06): ")
    if not date_input:
        print("Дата не введена. Выход.")
        return

    try:
        day, month = map(int, date_input.split('.'))
        year = datetime.now().year
        full_date_str_db = f"{year:04d}-{month:02d}-{day:02d}"
    except ValueError:
        print("Неверный формат даты. Пожалуйста, используйте ДД.ММ")
        return

    print(f"Начинаю извлечение данных за {date_input}...")

    try:
        client = get_gsheet_client()  # <-- ВЫЗЫВАЕМ ПРАВИЛЬНУЮ ФУНКЦИЮ
        spreadsheet = client.open_by_url(config.GOOGLE_SHEET_URL)
        sheet = spreadsheet.worksheet(config.GOOGLE_SHEET_NAME)
        all_data = sheet.get_all_values()
        print("Успешно подключился к Google Sheets.")
    except Exception as e:
        print(f"Ошибка подключения к Google Sheets: {e}")
        return

    with open(config.GRAFIK_PATH, "r", encoding="utf-8") as f:
        user_config = json.load(f)

    daily_counts = {}
    for user_id_str, info in user_config.items():
        user_id, cols = int(user_id_str), info.get("g_sheet_cols")
        if not cols: continue
        num_col_idx, date_col_idx = cols[0] - 1, cols[1] - 1
        count = 0
        for row in all_data[1:]:
            if len(row) > max(num_col_idx, date_col_idx):
                date_from_sheet = row[date_col_idx].strip()
                # Проверяем, что дата из таблицы содержит нужную нам часть (например, "12.06")
                if row[num_col_idx] and date_input in date_from_sheet:
                    count += 1
        if count > 0:
            daily_counts[user_id] = count
            print(f"Найдено для '{info.get('short_name')}': {count} записей.")

    if not daily_counts:
        print("Не найдено данных за указанную дату.")
        return

    history_file = Path("history_update.json")
    if history_file.exists():
        with open(history_file, 'r', encoding='utf-8') as f:
            history_data = json.load(f)
        print(f"Обновляю существующий файл {history_file}...")
    else:
        history_data = {uid: {"comment": info.get("short_name"), "daily_history": {}} for uid, info in
                        user_config.items()}
        print(f"Создаю новый файл {history_file}...")

    for user_id, count in daily_counts.items():
        if str(user_id) in history_data:
            history_data[str(user_id)]["daily_history"][full_date_str_db] = count

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history_data, f, indent=2, ensure_ascii=False)

    print("-" * 20)
    print(f"Готово! Файл '{history_file}' успешно обновлен.")
    print("Теперь можно запускать 'add_history.py'.")


if __name__ == "__main__":
    extract_daily_stats()