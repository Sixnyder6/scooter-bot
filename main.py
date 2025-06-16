# Файл: main.py (ФИНАЛЬНАЯ, БЛЯДЬ, ВЕРСИЯ)

import os
import re
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict

import cv2
import pytesseract
from pyzbar.pyzbar import decode
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import nest_asyncio

# Импорт из наших модулей
import config
import database as db
import g_sheets
import utils

# --- Настройка ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
nest_asyncio.apply()

if config.TESSERACT_CMD and os.path.exists(config.TESSERACT_CMD):
    pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD
else:
    logging.warning("Путь к Tesseract-OCR не найден или не указан.")

NUMBER_PATTERN = re.compile(r'(?:\b00\d{6}\b|\b\d{6,8}\b)')
user_broadcast_state: Dict[int, bool] = {}
last_broadcast_info: Dict = {}


# --- Функции для рассылки ---
async def start_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_special_user(user_id): return
    user_broadcast_state[user_id] = True
    reply_markup = utils.get_user_reply_markup(user_id, in_broadcast_mode=True)
    await update.message.reply_text("Вы в режиме рассылки. Отправьте текст или фото.", reply_markup=reply_markup)


async def send_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE, text: Optional[str] = None,
                                 photo_file_id: Optional[str] = None):
    sender_id = update.message.from_user.id
    sender_name = utils.USER_NAMES.get(sender_id, f"ID {sender_id}")
    caption = text or update.message.caption or ""
    full_message = f"📢 Сообщение от: *{sender_name}*\n\n{caption}"
    recipients = [uid for uid_str, data in utils.USER_DATA.items() if
                  data.get("permissions") == "user" and (uid := int(uid_str)) != sender_id]
    if not recipients:
        await context.bot.send_message(chat_id=sender_id, text="Не найдено сотрудников для рассылки.")
        return

    global last_broadcast_info
    last_broadcast_info = {'sender_id': sender_id, 'message_text': caption, 'recipients': recipients, 'message_ids': {},
                           'accepted': set(), 'skipped': set()}
    reply_markup = ReplyKeyboardMarkup([[config.BUTTON_ACCEPT_BROADCAST, config.BUTTON_SKIP_BROADCAST]],
                                       resize_keyboard=True)

    successful_sends, failed_sends = 0, 0
    for user_id in recipients:
        try:
            msg = await (context.bot.send_photo if photo_file_id else context.bot.send_message)(
                chat_id=user_id,
                **(dict(photo=photo_file_id, caption=full_message) if photo_file_id else dict(text=full_message)),
                parse_mode="Markdown", reply_markup=reply_markup
            )
            last_broadcast_info['message_ids'][user_id] = msg.message_id
            successful_sends += 1
        except Exception as e:
            logging.error(f"Не удалось отправить рассылку пользователю {user_id}: {e}")
            failed_sends += 1

    user_broadcast_state[sender_id] = False
    await context.bot.send_message(
        chat_id=sender_id, text=f"✅ Рассылка завершена!\nУспешно: {successful_sends}, Ошибок: {failed_sends}",
        reply_markup=utils.get_user_reply_markup(sender_id)
    )


async def handle_broadcast_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not last_broadcast_info or user_id not in last_broadcast_info.get('recipients', []): return
    action = 'accepted' if update.message.text == config.BUTTON_ACCEPT_BROADCAST else 'skipped'
    last_broadcast_info[action].add(user_id)
    if original_msg_id := last_broadcast_info['message_ids'].get(user_id):
        try:
            await context.bot.delete_message(chat_id=user_id, message_id=original_msg_id)
        except Exception:
            pass
    await update.message.reply_text("Ваш ответ принят.", reply_markup=utils.get_user_reply_markup(user_id))
    if sender_id := last_broadcast_info.get('sender_id'):
        accepted = sorted([utils.USER_NAMES.get(uid) for uid in last_broadcast_info['accepted']])
        skipped = sorted([utils.USER_NAMES.get(uid) for uid in last_broadcast_info['skipped']])
        report_text = f"📢 Отчет:\n✅ Приняли ({len(accepted)}): {', '.join(accepted) or '-'}\n⏭ Пропустили ({len(skipped)}): {', '.join(skipped) or '-'}"
        try:
            await context.bot.send_message(chat_id=sender_id, text=report_text, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Не удалось отправить отчет о рассылке {sender_id}: {e}")


# --- Основные обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_broadcast_state: del user_broadcast_state[user_id]
    if not utils.is_user_allowed(user_id):
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text("Привет! Готов к работе.", reply_markup=utils.get_user_reply_markup(user_id))


async def process_and_add_scooter(user_id: int, scooter_number: str):
    await db.add_scooter(user_id, scooter_number)
    await db.update_last_activity(user_id)
    user_data = utils.USER_DATA.get(str(user_id), {})
    asyncio.create_task(
        g_sheets.append_to_google_sheets_async(user_data.get("short_name", ""), scooter_number,
                                               user_data.get("g_sheet_cols"))
    )


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    if not utils.is_user_allowed(user_id): return

    # Проверяем, является ли текст названием кнопки, которую нужно игнорировать
    # Это предотвращает краш, когда пользователь нажимает WebApp кнопку
    if text == config.BUTTON_MY_STATS:
        logging.info(f"Пользователь {user_id} нажал WebApp кнопку 'Моя статистика'. Игнорируем текстовое сообщение.")
        return

    if utils.is_special_user(user_id) and user_broadcast_state.get(user_id):
        await send_broadcast_message(update, context, text=text)
    elif NUMBER_PATTERN.search(text):
        number = NUMBER_PATTERN.search(text).group(0)
        await process_and_add_scooter(user_id, number)
        await update.message.reply_text(f"Самокат {number} сохранён.")
    else:
        # Если это не команда и не номер, проверяем, не является ли это текстом с другой кнопки
        # Это нужно, чтобы бот не отвечал "Команда не распознана" на каждую кнопку
        all_buttons = [config.BUTTON_MY_SHIFTS, config.BUTTON_RETURN, config.BUTTON_CONTACT_ADMIN, config.BUTTON_TABLE,
                       config.BUTTON_VYGRUZKA, config.BUTTON_TODAY_REPORT, config.BUTTON_DEKADA_1,
                       config.BUTTON_DEKADA_2, config.BUTTON_DEKADA_3, config.BUTTON_BROADCAST,
                       config.BUTTON_ACCEPT_BROADCAST, config.BUTTON_SKIP_BROADCAST, config.BUTTON_INFO]
        if text not in all_buttons:
            await update.message.reply_text("Команда не распознана.")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_user_allowed(user_id): return
    if utils.is_special_user(user_id) and user_broadcast_state.get(user_id):
        await send_broadcast_message(update, context, photo_file_id=update.message.photo[-1].file_id)
        return

    await context.bot.send_chat_action(chat_id=update.message.chat_id, action=ChatAction.TYPING)
    photo_file = await update.message.photo[-1].get_file()
    config.TEMP_DIR.mkdir(exist_ok=True)
    file_path = config.TEMP_DIR / f"{photo_file.file_id}.jpg"
    await photo_file.download_to_drive(file_path)

    scooter_number = extract_number_from_image(str(file_path))
    if scooter_number:
        await process_and_add_scooter(user_id, scooter_number)
        await update.message.reply_text(f"Распознан номер {scooter_number}. Данные сохранены.")
    else:
        await update.message.reply_text("Не удалось распознать номер самоката на фото.")
    try:
        os.remove(file_path)
    except OSError as e:
        logging.error(f"Не удалось удалить временный файл {file_path}: {e}")


async def handle_vygruzka(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_special_user(user_id): return
    keyboard = [[config.BUTTON_TODAY_REPORT], [config.BUTTON_DEKADA_1, config.BUTTON_DEKADA_2],
                [config.BUTTON_DEKADA_3], [config.BUTTON_RETURN]]
    await update.message.reply_text("Выберите период для отчета:",
                                    reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True))


async def handle_report_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_special_user(user_id): return
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    stats = await g_sheets.get_live_report_from_gsheet_async()
    message = utils.format_today_report_message(stats)
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_report_decade(update: Update, context: ContextTypes.DEFAULT_TYPE, decade_num: int):
    user_id = update.message.from_user.id
    if not utils.is_special_user(user_id): return
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
    stats_data = await db.get_report_stats("decade", decade_num=decade_num)
    message = utils.format_decade_report_message(decade_num, stats_data)
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_my_shifts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_user_allowed(user_id): return
    message = await utils.get_user_shift_message(user_id)
    await update.message.reply_text(message, parse_mode="Markdown")


async def handle_table_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_special_user(user_id): return
    keyboard = [[InlineKeyboardButton("Открыть таблицу", url=config.GOOGLE_SHEET_URL)]]
    await update.message.reply_text("Нажмите для открытия Google Таблицы:", reply_markup=InlineKeyboardMarkup(keyboard))


async def handle_contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_user_allowed(user_id): return
    await update.message.reply_text("По вопросам обращайтесь к администратору: @Cyberdyne_Industries")


async def handle_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if not utils.is_user_allowed(user_id): return

    photos_info = [
        ("1 QR.jpg", "📸 Фото 1 – QR-код на самокате\n🔹 *Отправь фото как из примера выше...*"),
        ("2 Nomer Text.jpg", "📸 Фото 2 – Скрин строки с номером\n🔹 *Отправь номер самоката в текстовом формате...*"),
        ("grafic.png", "📸 Фото 3 – Общий график\n🔹 *Общий график...*"),
    ]

    for filename, caption in photos_info:
        photo_path = config.INFO_PHOTOS_DIR / filename
        if photo_path.exists():
            try:
                await context.bot.send_photo(chat_id=update.message.chat_id, photo=photo_path, caption=caption,
                                             parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Не удалось отправить инфо-фото {filename}: {e}")
        else:
            logging.warning(f"Инфо-фото не найдено по пути: {photo_path}")


def rotate_image(image, angle):
    (h, w) = image.shape[:2];
    center = (w / 2, h / 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0);
    return cv2.warpAffine(image, M, (w, h))


def extract_number_from_image(image_path: str) -> Optional[str]:
    try:
        image = cv2.imread(image_path)
        if image is None: return None
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        for angle in [0, 90, 180, 270]:
            for obj in decode(rotate_image(gray, angle)):
                if match := re.search(r'\d{8}', obj.data.decode("utf-8")):
                    return match.group(0)
        if match := NUMBER_PATTERN.search(pytesseract.image_to_string(gray, config='--psm 6')):
            return match.group(0)
    except Exception as e:
        logging.error(f"Ошибка при обработке изображения {image_path}: {e}")
    return None


async def main():
    utils.load_user_data()
    await db.init_db()
    application = Application.builder().token(config.BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))

    button_handlers = {
        # ЭТОЙ СУКИ БОЛЬШЕ НЕТ, ТЕПЕРЬ ВСЁ БУДЕТ ЗАЕБИСЬ
        config.BUTTON_MY_SHIFTS: handle_my_shifts,
        config.BUTTON_RETURN: start,
        config.BUTTON_CONTACT_ADMIN: handle_contact_admin,
        config.BUTTON_TABLE: handle_table_button,
        config.BUTTON_VYGRUZKA: handle_vygruzka,
        config.BUTTON_TODAY_REPORT: handle_report_today,
        config.BUTTON_DEKADA_1: lambda u, c: handle_report_decade(u, c, 1),
        config.BUTTON_DEKADA_2: lambda u, c: handle_report_decade(u, c, 2),
        config.BUTTON_DEKADA_3: lambda u, c: handle_report_decade(u, c, 3),
        config.BUTTON_BROADCAST: start_broadcast,
        config.BUTTON_ACCEPT_BROADCAST: handle_broadcast_reply,
        config.BUTTON_SKIP_BROADCAST: handle_broadcast_reply,
        config.BUTTON_INFO: handle_info,
    }
    for button_text, callback in button_handlers.items():
        application.add_handler(MessageHandler(
            filters.TEXT & filters.Regex(f"^{re.escape(button_text)}$") & filters.Chat(
                chat_id=list(map(int, utils.USER_DATA.keys()))), callback))

    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    logging.info("Бот запускается...")
    await application.run_polling()


if __name__ == '__main__':
    asyncio.run(main())