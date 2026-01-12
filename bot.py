import asyncio
import os
import threading
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, CallbackQueryHandler, filters
)
from database import (
    init_db, add_task, get_all_tasks, delete_task_by_id,
    set_personal_notifications, get_personal_notifications,
    update_task, check_overlap
)
from utils import parse_datetime, get_assignee_display, get_assignee_emoji
from scheduler import start_scheduler

load_dotenv()

# Состояния диалогов
DESCRIPTION, DATETIME, DURATION, ASSIGNEE = range(4)
EDIT_SELECT, EDIT_TEXT, EDIT_DATETIME = range(10, 13)

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ALENA_USER_ID = int(os.getenv("ALENA_USER_ID"))
OLEG_USER_ID = int(os.getenv("OLEG_USER_ID"))

if not all([BOT_TOKEN, GROUP_CHAT_ID, ALENA_USER_ID, OLEG_USER_ID]):
    raise ValueError("Ошибка: не все переменные окружения заданы в .env")

# ===== Команды =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я ваш планировщик. Используйте /n, чтобы добавить задачу.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🗓 *Помощь (SOS)*\n\n"
        "🔹 /n — добавить задачу\n"
        "🔹 /den — задачи на сегодня\n"
        "🔹 /ned — на неделю\n"
        "🔹 /del — удалить задачу\n"
        "🔹 /izm — изменить задачу\n"
        "🔹 /on — включить личные уведомления\n"
        "🔹 /off — отключить личные уведомления\n"
        "🔹 /sos — показать эту справку"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ===== Добавление задачи =====

async def new_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напишите описание задачи:")
    return DESCRIPTION

async def new_task_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['description'] = update.message.text
    await update.message.reply_text("Укажите дату и время (формат: ДД.ММ.ГГГГ ЧЧ:ММ):")
    return DATETIME

async def new_task_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dt = parse_datetime(update.message.text)
        context.user_data['datetime'] = dt.isoformat()
        await update.message.reply_text("Укажите продолжительность в минутах (или /пропустить):")
        return DURATION
    except:
        await update.message.reply_text("Неверный формат. Пример: 10.12.2025 15:30")
        return DATETIME

async def new_task_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "/пропустить":
        context.user_data['duration'] = None
    else:
        try:
            context.user_data['duration'] = int(update.message.text)
        except:
            context.user_data['duration'] = None

    keyboard = [
        [InlineKeyboardButton("Алена", callback_data="alena")],
        [InlineKeyboardButton("Олег", callback_data="oleg")],
        [InlineKeyboardButton("Общее", callback_data="common")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Для кого задача?", reply_markup=reply_markup)
    return ASSIGNEE

async def new_task_assignee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    assignee = query.data
    context.user_data['assignee'] = assignee

    # Проверка наложения
    if check_overlap(context.user_data['datetime'], context.user_data['duration']):
        await query.message.reply_text("⚠️ На это время уже запланировано мероприятие!")

    # Сохраняем
    creator_id = update.effective_user.id
    creator_name = update.effective_user.first_name
    add_task(
        text=context.user_data['description'],
        dt_str=context.user_data['datetime'],
        duration=context.user_data['duration'],
        assignee=assignee,
        creator_id=creator_id,
        creator_name=creator_name
    )

    emoji = get_assignee_emoji(assignee)
    display = get_assignee_display(assignee)
    await query.edit_message_text(f"✅ Задача сохранена!\n{emoji} {display}: {context.user_data['description']}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.")
    return ConversationHandler.END

# ===== Просмотр =====

from datetime import datetime, timedelta

async def show_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    tasks = get_all_tasks()
    today_tasks = [t for t in tasks if start_of_day <= datetime.fromisoformat(t['datetime']) < end_of_day]

    if not today_tasks:
        await update.message.reply_text("📌 На сегодня нет задач.")
        return

    text = "📆 *Задачи на сегодня:*\n\n"
    for t in today_tasks:
        emoji = get_assignee_emoji(t['assignee'])
        display = get_assignee_display(t['assignee'])
        dt = t['datetime'].replace('T', ' ')
        creator = t['creator_name']
        text += f"{emoji} {display}: {t['text']}\n   🕒 {dt} (создал: {creator})\n\n"
    await update.message.reply_text(text, parse_mode="Markdown")

async def show_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = datetime.now()
    end_of_week = now + timedelta(days=7)

    tasks = get_all_tasks()
    week_tasks = [t for t in tasks if now <= datetime.fromisoformat(t['datetime']) <= end_of_week]

    if not week_tasks:
        await update.message.reply_text("📅 На неделю задач нет.")
        return

    from collections import defaultdict
    grouped = defaultdict(list)
    for t in week_tasks:
        date_key = datetime.fromisoformat(t['datetime']).strftime("%d.%m.%Y")
        grouped[date_key].append(t)

    text = "🗓 *Задачи на неделю:*\n\n"
    for date_str in sorted(grouped.keys()):
        text += f"🔹 *{date_str}*:\n"
        for t in grouped[date_str]:
            emoji = get_assignee_emoji(t['assignee'])
            display = get_assignee_display(t['assignee'])
            time_only = datetime.fromisoformat(t['datetime']).strftime("%H:%M")
            creator = t['creator_name']
            text += f"  {emoji} {display}: {t['text']} ({time_only}) (создал: {creator})\n"
        text += "\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# ===== Удаление =====

async def delete_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_all_tasks()
    if not tasks:
        await update.message.reply_text("Нет задач.")
        return
    text = "Выберите номер задачи для удаления:\n"
    for t in tasks:
        dt = t['datetime'].replace('T', ' ')
        assignee = get_assignee_display(t['assignee'])
        text += f"{t['id']}. {assignee}: {t['text']} — {dt}\n"
    text += "\nОтправьте номер."
    await update.message.reply_text(text)
    return 1

async def delete_task_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(update.message.text)
        delete_task_by_id(task_id)
        await update.message.reply_text("✅ Задача удалена.")
    except:
        await update.message.reply_text("Ошибка. Попробуйте снова.")
    return ConversationHandler.END

# ===== Редактирование (/izm) =====

async def edit_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_all_tasks()
    if not tasks:
        await update.message.reply_text("Нет задач для редактирования.")
        return ConversationHandler.END
    text = "Выберите номер задачи для редактирования:\n"
    for t in tasks:
        dt = t['datetime'].replace('T', ' ')
        assignee = get_assignee_display(t['assignee'])
        text += f"{t['id']}. {assignee}: {t['text']} — {dt}\n"
    text += "\nОтправьте номер."
    await update.message.reply_text(text)
    return EDIT_SELECT

async def edit_task_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        task_id = int(update.message.text)
        context.user_data['edit_task_id'] = task_id
        tasks = get_all_tasks()
        task = next((t for t in tasks if t['id'] == task_id), None)
        if not task:
            raise ValueError("Задача не найдена")
        context.user_data.update({
            'old_text': task['text'],
            'old_datetime': task['datetime'],
            'old_duration': task['duration'],
            'old_assignee': task['assignee'],
            'old_creator_id': task['creator_id'],
            'old_creator_name': task['creator_name']
        })
        await update.message.reply_text(
            f"Текущее описание: {task['text']}\n"
            "Введите новое описание или /оставить:"
        )
        return EDIT_TEXT
    except:
        await update.message.reply_text("Ошибка. Попробуйте снова.")
        return ConversationHandler.END

async def edit_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "/оставить":
        new_text = context.user_data['old_text']
    else:
        new_text = update.message.text
    context.user_data['new_text'] = new_text

    old_dt_str = context.user_data['old_datetime'].replace('T', ' ')
    await update.message.reply_text(
        f"Текущая дата/время: {old_dt_str}\n"
        "Введите новую дату и время (ДД.ММ.ГГГГ ЧЧ:ММ) или /оставить:"
    )
    return EDIT_DATETIME

async def edit_task_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.lower() == "/оставить":
        new_dt_iso = context.user_data['old_datetime']
    else:
        try:
            new_dt = parse_datetime(update.message.text)
            new_dt_iso = new_dt.isoformat()
        except:
            await update.message.reply_text("Неверный формат. Попробуйте снова.")
            return EDIT_DATETIME

    # Проверка наложения
    duration = context.user_data['old_duration']
    if check_overlap(new_dt_iso, duration):
        await update.message.reply_text("⚠️ На это время уже запланировано мероприятие!")

    # Обновляем
    update_task(context.user_data['edit_task_id'], context.user_data['new_text'], new_dt_iso)
    await update.message.reply_text("✅ Задача обновлена!")
    return ConversationHandler.END

# ===== Настройки уведомлений =====

async def enable_personal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_personal_notifications(user_id, True)
    await update.message.reply_text("✅ Личные уведомления включены.")

async def disable_personal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    set_personal_notifications(user_id, False)
    await update.message.reply_text("🔕 Личные уведомления отключены. Все сообщения — только в общем чате.")

# ===== ФИКТИВНЫЙ HTTP-СЕРВЕР ДЛЯ RENDER =====

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_http_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"HTTP server running on port {port}")
    server.serve_forever()

# ===== ЗАПУСК =====

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv_new = ConversationHandler(
        entry_points=[CommandHandler("n", new_task_start)],
        states={
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_task_description)],
            DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_task_datetime)],
            DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_task_duration)],
            ASSIGNEE: [CallbackQueryHandler(new_task_assignee)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    conv_del = ConversationHandler(
        entry_points=[CommandHandler("del", delete_task_start)],
        states={1: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_task_confirm)]},
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    conv_edit = ConversationHandler(
        entry_points=[CommandHandler("izm", edit_task_start)],
        states={
            EDIT_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_select)],
            EDIT_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_text)],
            EDIT_DATETIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_datetime)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("sos", help_command))
    app.add_handler(CommandHandler("den", show_today))
    app.add_handler(CommandHandler("ned", show_week))
    app.add_handler(CommandHandler("on", enable_personal))
    app.add_handler(CommandHandler("off", disable_personal))
    app.add_handler(conv_new)
    app.add_handler(conv_del)
    app.add_handler(conv_edit)

    start_scheduler(app.bot, GROUP_CHAT_ID, ALENA_USER_ID, OLEG_USER_ID, get_personal_notifications)

    # Запуск HTTP-сервера в фоне
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
