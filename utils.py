from datetime import datetime

def parse_datetime(dt_str):
    """Преобразует '10.12.2025 15:30' → datetime"""
    return datetime.strptime(dt_str.strip(), "%d.%m.%Y %H:%M")

def format_datetime(dt: datetime):
    return dt.strftime("%d.%m.%Y %H:%M")

def get_assignee_display(assignee: str) -> str:
    mapping = {
        'alena': 'АЛЕНА',
        'oleg': 'ОЛЕГ',
        'common': 'ОБЩЕЕ'
    }
    return mapping.get(assignee, assignee.upper())

def get_assignee_emoji(assignee: str) -> str:
    return {
        'alena': '🔵',
        'oleg': '🟢',
        'common': '🟡'
    }.get(assignee, '📌')
