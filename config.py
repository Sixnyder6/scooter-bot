# Файл: config.py (Полная версия с добавленной кнопкой)

import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# --- Основные настройки ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN")
TESSERACT_CMD: str = os.getenv("TESSERACT_CMD")
WEB_APP_URL: str = os.getenv("WEB_APP_URL") # URL для Web App
ADMIN_USER_ID: int = 1181905320 # ID главного администратора

# --- Пути ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
DB_PATH = DATA_DIR / "bot_data.db"
GRAFIK_PATH = DATA_DIR / "grafik.json"
INFO_PHOTOS_DIR = DATA_DIR / "info_photos"

# --- Google Sheets ---
GOOGLE_CREDENTIALS_PATH: str = os.getenv("GOOGLE_CREDENTIALS_PATH")
GOOGLE_SHEET_URL: str = os.getenv("GOOGLE_SHEET_URL")
GOOGLE_SHEET_NAME: str = "QR Codes"

# --- Тексты кнопок ---
# <<< ДОБАВЛЕНА НОВАЯ КНОПКА >>>
BUTTON_ADMIN_PANEL: str = "📊 Admin Panel"
# --- Остальные кнопки без изменений ---
BUTTON_VYGRUZKA: str = "📤 Выгрузка"
BUTTON_TABLE: str = "📊 Таблица"
BUTTON_BROADCAST: str = "📢 Отправить всем"
BUTTON_MY_STATS: str = "👤 Моя статистика"
BUTTON_MY_SHIFTS: str = "📅 Мой график"
BUTTON_CONTACT_ADMIN: str = "📩 Написать админу"
BUTTON_INFO: str = "ℹ️ Инфо"
BUTTON_RETURN: str = "🔙 Вернуться"

# --- КНОПКИ ДЛЯ РАССЫЛКИ ---
BUTTON_ACCEPT_BROADCAST: str = "✅ Принял"
BUTTON_SKIP_BROADCAST: str = "⏭ Пропустить"

# --- Кнопки для выгрузки ---
BUTTON_TODAY_REPORT: str = "📊 За сегодня"
BUTTON_DEKADA_1: str = "1️⃣ Декада (1-10)"
BUTTON_DEKADA_2: str = "2️⃣ Декада (11-20)"
BUTTON_DEKADA_3: str = "3️⃣ Декада (21-31)"

# --- Настройки логики ---
SIMULATED_YEAR = 2025
DECADE_NORM = 140
PREMIUM_RATE = 200
RUS_MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"
]
SHIFT_SYMBOLS = {"work": "🟢 Рабочий день", "closed": "🟡 Закрыто", "off": "🔴 Выходной"}