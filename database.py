import sqlite3
from datetime import datetime

DB_PATH = "planner.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            datetime TEXT NOT NULL,
            duration INTEGER,
            assignee TEXT NOT NULL,
            creator_id INTEGER NOT NULL,
            creator_name TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            personal_notifications BOOLEAN DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def add_task(text, dt_str, duration, assignee, creator_id, creator_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tasks (text, datetime, duration, assignee, creator_id, creator_name)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (text, dt_str, duration, assignee, creator_id, creator_name))
    conn.commit()
    conn.close()

def get_all_tasks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks ORDER BY datetime")
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def delete_task_by_id(task_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()

def update_task(task_id, new_text, new_datetime):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE tasks
        SET text = ?, datetime = ?
        WHERE id = ?
    """, (new_text, new_datetime, task_id))
    conn.commit()
    conn.close()

def cleanup_old_tasks(days=7):
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tasks WHERE datetime < ?", (cutoff_iso,))
    conn.commit()
    conn.close()

def set_personal_notifications(user_id, enabled):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_settings (user_id, personal_notifications)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET personal_notifications = excluded.personal_notifications
    """, (user_id, int(enabled)))
    conn.commit()
    conn.close()

def get_personal_notifications(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT personal_notifications FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return bool(row[0]) if row else True

# === НОВАЯ ФУНКЦИЯ: проверка наложения ===
def check_overlap(new_start: str, new_duration: int = None):
    from datetime import datetime, timedelta
    new_start_dt = datetime.fromisoformat(new_start)
    new_end_dt = new_start_dt + timedelta(minutes=new_duration or 0)

    tasks = get_all_tasks()
    for task in tasks:
        old_start = datetime.fromisoformat(task['datetime'])
        old_duration = task['duration'] or 0
        old_end = old_start + timedelta(minutes=old_duration)

        if new_start_dt < old_end and old_start < new_end_dt:
            return True
    return False
