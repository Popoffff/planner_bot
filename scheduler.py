import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from telegram import Bot
from database import get_all_tasks, cleanup_old_tasks
from utils import get_assignee_emoji, get_assignee_display

BOT_INSTANCE = None
GROUP_CHAT_ID = None

def format_tomorrow_summary():
    tomorrow = datetime.now().date() + timedelta(days=1)
    start_tomorrow = datetime.combine(tomorrow, datetime.min.time())
    end_tomorrow = start_tomorrow + timedelta(days=1)

    tasks = get_all_tasks()
    tomorrow_tasks = []
    for t in tasks:
        task_time = datetime.fromisoformat(t['datetime'])
        if start_tomorrow <= task_time < end_tomorrow:
            tomorrow_tasks.append(t)

    if not tomorrow_tasks:
        return None

    text = f"📅 *Завтра, {tomorrow.strftime('%d.%m')}*:\n\n"
    for t in tomorrow_tasks:
        emoji = get_assignee_emoji(t['assignee'])
        display = get_assignee_display(t['assignee'])
        time_only = datetime.fromisoformat(t['datetime']).strftime("%H:%M")
        text += f"{emoji} {display}: {t['text']} ({time_only})\n"
    return text

async def send_tomorrow_summary():
    if not BOT_INSTANCE:
        return
    summary = format_tomorrow_summary()
    if summary:
        await BOT_INSTANCE.send_message(chat_id=GROUP_CHAT_ID, text=summary, parse_mode="Markdown")

async def cleanup_job():
    cleanup_old_tasks(days=7)

def start_scheduler(bot, group_chat_id, alena_id, oleg_id, get_pn_func):
    global BOT_INSTANCE, GROUP_CHAT_ID
    BOT_INSTANCE = bot
    GROUP_CHAT_ID = group_chat_id

    scheduler = AsyncIOScheduler()
    # Ежедневно в 17:00 и 22:00 по местному времени сервера
    scheduler.add_job(send_tomorrow_summary, 'cron', hour=17, minute=0)
    scheduler.add_job(send_tomorrow_summary, 'cron', hour=22, minute=0)
    scheduler.add_job(cleanup_job, 'interval', hours=24)
    scheduler.start()
