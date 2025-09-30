"""
Модуль конфигурации для Work Tracker Bot.
Загружает настройки из .env файла.
"""

import os
from dotenv import load_dotenv

# Загрузка переменных из .env файла
load_dotenv()

# Токен Telegram бота
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Путь к базе данных SQLite
DATABASE_PATH = os.getenv("DATABASE_PATH", "work_tracker.db")

# Настройки рабочего дня (в часах)
WORK_DAY_START = 9  # 09:00
WORK_DAY_END = 18  # 18:00
LUNCH_BREAK_START = 13  # 13:00
LUNCH_BREAK_END = 14  # 14:00
WORK_DAY_HOURS = 8  # Стандартная продолжительность рабочего дня
