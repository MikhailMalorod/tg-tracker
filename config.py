"""
Модуль конфигурации для Work Tracker Bot.
Загружает настройки из .env файла.
"""

import os
import json
import datetime
from typing import List, Dict, Any
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

# Глобальные переменные для категорий
_work_categories: List[str] = []
_note_categories: List[str] = []
_last_file_mtime: float = 0.0

def load_categories() -> Dict[str, Any]:
    """Загрузка категорий из JSON файла."""
    global _work_categories, _note_categories, _last_file_mtime

    categories_file = 'categories.json'

    # Проверяем время изменения файла
    try:
        current_mtime = os.path.getmtime(categories_file)
        if current_mtime == _last_file_mtime and _work_categories and _note_categories:
            # Файл не изменился, возвращаем текущие категории
            return {
                'work_categories': _work_categories,
                'note_categories': _note_categories,
                'loaded_from_file': True,
                'file_unchanged': True
            }
        _last_file_mtime = current_mtime
    except OSError:
        # Файл не существует или недоступен
        current_mtime = 0

    try:
        if os.path.exists(categories_file):
            with open(categories_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Загружаем категории
            work_cats = data.get('work_categories', [])
            note_cats = data.get('note_categories', [])

            # Валидация данных
            if isinstance(work_cats, list) and len(work_cats) > 0:
                _work_categories = work_cats
            else:
                print("Предупреждение: некорректные категории работы в categories.json, используются значения по умолчанию")
                _work_categories = ["Разработка", "Совещания", "Документация", "Обучение", "Другое"]

            if isinstance(note_cats, list) and len(note_cats) > 0:
                _note_categories = note_cats
            else:
                print("Предупреждение: некорректные категории заметок в categories.json, используются значения по умолчанию")
                _note_categories = ["Общее", "Идея", "Задача", "Проблема", "Встреча", "Личное"]

            return {
                'work_categories': _work_categories,
                'note_categories': _note_categories,
                'loaded_from_file': True
            }
        else:
            # Файл не существует, создаем с значениями по умолчанию
            print("Файл categories.json не найден, создаем с значениями по умолчанию")
            default_data = {
                "work_categories": ["Разработка", "Совещания", "Документация", "Обучение", "Другое"],
                "note_categories": ["Общее", "Идея", "Задача", "Проблема", "Встреча", "Личное"],
                "version": "1.0",
                "last_updated": datetime.datetime.now().isoformat() + "Z"
            }

            with open(categories_file, 'w', encoding='utf-8') as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)

            _work_categories = default_data['work_categories']
            _note_categories = default_data['note_categories']

            return {
                'work_categories': _work_categories,
                'note_categories': _note_categories,
                'loaded_from_file': False,
                'created_default': True
            }

    except json.JSONDecodeError as e:
        print(f"Ошибка парсинга JSON в categories.json: {e}")
        print("Используются значения по умолчанию")
        _work_categories = ["Разработка", "Совещания", "Документация", "Обучение", "Другое"]
        _note_categories = ["Общее", "Идея", "Задача", "Проблема", "Встреча", "Личное"]

        return {
            'work_categories': _work_categories,
            'note_categories': _note_categories,
            'loaded_from_file': False,
            'json_error': True
        }

    except Exception as e:
        print(f"Ошибка загрузки categories.json: {e}")
        print("Используются значения по умолчанию")
        _work_categories = ["Разработка", "Совещания", "Документация", "Обучение", "Другое"]
        _note_categories = ["Общее", "Идея", "Задача", "Проблема", "Встреча", "Личное"]

        return {
            'work_categories': _work_categories,
            'note_categories': _note_categories,
            'loaded_from_file': False,
            'error': True
        }

def get_work_categories() -> List[str]:
    """Получение списка категорий работы."""
    if not _work_categories:
        load_categories()
    return _work_categories.copy()

def get_note_categories() -> List[str]:
    """Получение списка категорий заметок."""
    if not _note_categories:
        load_categories()
    return _note_categories.copy()

def reload_categories() -> Dict[str, Any]:
    """Перезагрузка категорий из файла."""
    return load_categories()

def get_categories_info() -> Dict[str, Any]:
    """Получение полной информации о категориях."""
    return {
        'work_categories': get_work_categories(),
        'note_categories': get_note_categories(),
        'file_path': 'categories.json',
        'last_load_time': datetime.datetime.now().isoformat()
    }
