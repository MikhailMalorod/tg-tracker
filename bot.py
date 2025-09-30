"""
Основной модуль Telegram бота для отслеживания рабочего времени.
"""

import logging
import datetime
import asyncio
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters
)

import aiosqlite
from database import Database, SESSION_STATUS
from config import (
    TELEGRAM_BOT_TOKEN,
    get_work_categories,
    get_note_categories,
    reload_categories,
    get_categories_info
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(START_WORK, WAITING_NOTE_TEXT, WAITING_NOTE_CATEGORY) = range(3)

# Callback данные для кнопок
CB_START_WORK = "cb_start_work"
CB_END_WORK = "cb_end_work"
CB_BREAK_WORK = "break_work"
CB_RESUME_WORK = "resume_work"
CB_ADD_NOTE = "add_note"

# Callback данные для статистики
CB_STATS_DAY = "stats_day"
CB_STATS_WEEK = "stats_week"
CB_STATS_MONTH = "stats_month"

# Callback данные для экспорта
CB_EXPORT_CSV = "export_csv"

# Callback данные для напоминаний
CB_REMINDERS_SETTINGS = "reminders_settings"
CB_WORK_REMINDER_TOGGLE = "work_reminder_toggle"
CB_BREAK_REMINDER_TOGGLE = "break_reminder_toggle"
CB_LONG_BREAK_REMINDER_TOGGLE = "long_break_reminder_toggle"
CB_DAILY_GOAL_TOGGLE = "daily_goal_toggle"

# Callback данные для календаря
CB_CALENDAR_DAY = "calendar_day_"

# Категории загружаются динамически из config.py
# WORK_CATEGORIES и NOTE_CATEGORIES теперь получаются через функции get_work_categories() и get_note_categories()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    user = update.effective_user
    
    # Регистрируем пользователя в базе данных
    await Database.add_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )
    
    # Проверяем, есть ли активная сессия
    active_session = await Database.get_active_session(user.id)
    
    if active_session:
        if active_session["status"] == "active":
            # Если есть активная сессия
            keyboard = [
                [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
                [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
                [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                [InlineKeyboardButton("🔔 Напоминания", callback_data=CB_REMINDERS_SETTINGS)],
                [InlineKeyboardButton("📅 Календарь", callback_data="calendar_show")],
                [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
            ]
        else:
            # Если есть приостановленная сессия
            keyboard = [
                [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
                [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
                [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                [InlineKeyboardButton("🔔 Напоминания", callback_data=CB_REMINDERS_SETTINGS)],
                [InlineKeyboardButton("📅 Календарь", callback_data="calendar_show")],
                [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
            ]
    else:
        # Если нет активных сессий
        keyboard = [
            [InlineKeyboardButton("▶️ Начать работу", callback_data=CB_START_WORK)],
            [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
            [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
            [InlineKeyboardButton("🔔 Напоминания", callback_data=CB_REMINDERS_SETTINGS)],
            [InlineKeyboardButton("📅 Календарь", callback_data="calendar_show")]
        ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Приветственное сообщение
    await update.message.reply_text(
        f"Привет, {user.first_name}! Я бот для отслеживания рабочего времени.\n\n"
        "Используй следующие команды:\n"
        "/start_work - Начать рабочий день\n"
        "/break - Сделать перерыв\n"
        "/resume - Возобновить работу\n"
        "/note - Добавить заметку\n"
        "/my_notes - Просмотр заметок\n"
        "/end_work - Завершить рабочий день\n"
        "/stats - Статистика рабочего времени\n"
        "/export - Экспорт данных в CSV\n"
        "/reminders - Настройки напоминаний\n"
        "/calendar - Календарь работы\n"
        "/categories - Управление категориями",
        reply_markup=reply_markup
    )

async def start_work_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start_work."""
    user = update.effective_user
    
    # Определяем, вызов через сообщение или callback
    is_callback = update.callback_query is not None
    
    # Проверяем, есть ли активная сессия
    active_session = await Database.get_active_session(user.id)
    
    if active_session:
        # Если есть активная сессия, сообщаем об этом
        start_time = datetime.datetime.fromisoformat(active_session["start_time"])
        duration = datetime.datetime.now() - start_time
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        status_message = ""
        keyboard = []
        
        if active_session["status"] == "active":
            status_message = "У вас уже есть активная рабочая сессия!"
            keyboard = [
                [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
                [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
            ]
        elif active_session["status"] == "paused":
            status_message = "У вас есть приостановленная рабочая сессия!"
            keyboard = [
                [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
                [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = (
            f"{status_message}\n"
            f"Начата: {start_time.strftime('%H:%M:%S')}\n"
            f"Продолжительность: {hours}ч {minutes}м {seconds}с"
        )
        
        # Отправляем сообщение в зависимости от типа update
        if is_callback:
            await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(text=message_text, reply_markup=reply_markup)
            
        return ConversationHandler.END
    
    # Создаем клавиатуру с категориями работы
    work_categories = get_work_categories()
    keyboard = []
    for category in work_categories:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"category_{category}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "Выберите категорию работы:"
    
    # Отправляем сообщение в зависимости от типа update
    if is_callback:
        await update.callback_query.edit_message_text(text=message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=message_text, reply_markup=reply_markup)
    
    return START_WORK

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора категории работы."""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    category = query.data.replace("category_", "")
    
    print(f"DEBUG: Выбрана категория: {category}")
    
    # Начинаем новую рабочую сессию
    session_id = await Database.start_work_session(user.id, category)
    
    if session_id == -1:
        await query.edit_message_text("У вас уже есть активная рабочая сессия!")
        return ConversationHandler.END
    
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    
    # Создаем клавиатуру с доступными действиями
    keyboard = [
        [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
        [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
        [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
        [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
        [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ Начата рабочая сессия ({category})\n"
        f"⏱️ Время начала: {current_time}\n\n"
        f"Для завершения используйте /end_work",
        reply_markup=reply_markup
    )
    
    return ConversationHandler.END

async def end_work_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /end_work."""
    user = update.effective_user
    
    # Завершаем активную сессию
    session_info = await Database.end_work_session(user.id)
    
    if not session_info:
        await update.message.reply_text(
            "У вас нет активной рабочей сессии.\n"
            "Чтобы начать новую сессию, используйте /start_work"
        )
        return
    
    # Вычисляем продолжительность сессии в часах и минутах
    duration_seconds = session_info["duration"]
    hours, remainder = divmod(duration_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    start_time = datetime.datetime.fromisoformat(session_info["start_time"]).strftime("%H:%M:%S")
    end_time = datetime.datetime.fromisoformat(session_info["end_time"]).strftime("%H:%M:%S")
    
    # Отправляем информацию о завершенной сессии
    await update.message.reply_text(
        f"✅ Рабочая сессия завершена\n"
        f"🏷️ Категория: {session_info['category']}\n"
        f"⏱️ Начало: {start_time}\n"
        f"⏱️ Конец: {end_time}\n"
        f"⌛ Продолжительность: {hours}ч {minutes}м {seconds}с\n\n"
        f"Хорошей работы! Для начала новой сессии используйте /start_work"
    )

async def break_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /break."""
    user = update.effective_user
    
    print(f"DEBUG: Вызвана команда break пользователем {user.id}")
    
    # Получаем текст причины перерыва
    reason = "Перерыв"
    if context.args:
        reason = " ".join(context.args)
    
    # Проверяем, что у пользователя есть активная сессия
    active_session = await Database.get_active_session(user.id)
    if not active_session:
        await update.message.reply_text(
            "У вас нет активной рабочей сессии.\n"
            "Чтобы начать работу, используйте /start_work"
        )
        return
    
    # Проверяем статус активной сессии
    if active_session["status"] == SESSION_STATUS["PAUSED"]:
        await update.message.reply_text(
            "Ваша сессия уже на паузе.\n"
            "Чтобы продолжить работу, используйте /resume"
        )
        return
    
    # Приостанавливаем сессию
    session = await Database.pause_work_session(user.id, reason)
    
    if not session:
        await update.message.reply_text(
            "У вас нет активной рабочей сессии.\n"
            "Чтобы начать работу, используйте /start_work"
        )
        return
    
    # Формируем клавиатуру
    keyboard = [
        [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
        [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
        [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
        [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
        [InlineKeyboardButton("⏹️ Завершить день", callback_data=CB_END_WORK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение о паузе
    start_time = datetime.datetime.fromisoformat(session["start_time"])
    duration = datetime.datetime.now() - start_time
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    
    await update.message.reply_text(
        f"⏸️ Пауза: \"{reason}\"\n"
        f"⏱️ Отработано: {hours}ч {minutes}мин\n\n"
        f"Чтобы продолжить, используйте /resume",
        reply_markup=reply_markup
    )

async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /resume."""
    user = update.effective_user
    
    # Возобновляем сессию
    session = await Database.resume_work_session(user.id)
    
    if not session:
        await update.message.reply_text(
            "У вас нет приостановленных сессий.\n"
            "Чтобы начать работу, используйте /start_work"
        )
        return
    
    # Формируем клавиатуру
    keyboard = [
        [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
        [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
        [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
        [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
        [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем сообщение о возобновлении работы
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    
    await update.message.reply_text(
        f"▶️ Работа возобновлена\n"
        f"⏱️ Время: {current_time}\n\n"
        f"Для завершения используйте /end_work",
        reply_markup=reply_markup
    )

async def note_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /note для добавления заметок."""
    user = update.effective_user

    print(f"DEBUG: Запрошена команда /note пользователем {user.id}")

    # Проверяем, есть ли активная сессия
    active_session = await Database.get_active_session(user.id)

    if not active_session:
        await update.message.reply_text(
            "У вас нет активной рабочей сессии.\n"
            "Чтобы начать работу, используйте /start_work"
        )
        return ConversationHandler.END

    # Сохраняем ID активной сессии в контексте
    context.user_data["active_session_id"] = active_session["id"]
    context.user_data["is_callback"] = False

    # Создаем клавиатуру с категориями заметок
    note_categories = get_note_categories()
    keyboard = []
    for category in note_categories:
        keyboard.append([InlineKeyboardButton(category, callback_data=f"note_category_{category}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "📝 Выберите категорию заметки:",
        reply_markup=reply_markup
    )

    return WAITING_NOTE_CATEGORY

async def my_notes_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /my_notes для просмотра последних заметок."""
    user = update.effective_user
    
    # Получаем последние заметки пользователя (максимум 10)
    notes = await Database.get_user_notes(user.id, limit=10)
    
    if not notes:
        await update.message.reply_text(
            "У вас пока нет сохраненных заметок."
        )
        return
    
    # Формируем сообщение со списком заметок
    message_text = "📋 Ваши последние заметки:\n\n"
    
    for i, note in enumerate(notes, 1):
        timestamp = datetime.datetime.fromisoformat(note["timestamp"]).strftime("%d.%m.%Y %H:%M")
        message_text += (
            f"{i}. {timestamp} - [{note['category']}] - {note['session_category']}\n"
            f"<i>{note['content'][:100]}{'...' if len(note['content']) > 100 else ''}</i>\n\n"
        )
    
    # Отправляем список заметок
    await update.message.reply_text(
        message_text,
        parse_mode="HTML"
    )

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /export для экспорта данных в CSV."""
    user = update.effective_user

    # Проверяем, есть ли у пользователя данные для экспорта
    sessions = await Database.get_sessions_by_timeframe(user.id, datetime.datetime.min, datetime.datetime.max)

    if not sessions:
        await update.message.reply_text(
            "У вас пока нет данных для экспорта.\n"
            "Начните работать с ботом, чтобы накопить статистику!"
        )
        return

    # Отправляем сообщение о начале экспорта
    await update.message.reply_text(
        "📊 Готовлю CSV файл с вашими данными...\n"
        "Это может занять несколько секунд."
    )

    # Создаем временный файл для экспорта
    import tempfile
    import os

    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, f'work_tracker_export_{user.id}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

    try:
        # Экспортируем все данные пользователя
        success = await Database.export_user_data_to_csv(user.id, file_path)

        if success:
            # Отправляем файл пользователю
            await update.message.reply_document(
                document=open(file_path, 'rb'),
                filename=f'work_tracker_{user.first_name}_{datetime.datetime.now().strftime("%Y%m%d")}.csv',
                caption="📊 Ваш полный отчет по работе в формате CSV"
            )

            # Удаляем временный файл
            os.remove(file_path)

        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при создании CSV файла.\n"
                "Попробуйте позже или обратитесь к администратору."
            )

    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при экспорте: {str(e)}\n"
            "Попробуйте позже."
        )

        # Удаляем файл в случае ошибки
        try:
            os.remove(file_path)
        except:
            pass

async def reminders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /reminders для управления напоминаниями."""
    user = update.effective_user

    # Получаем настройки напоминаний пользователя
    settings = await Database.get_reminder_settings(user.id)

    # Создаем клавиатуру с настройками напоминаний
    keyboard = [
        [
            InlineKeyboardButton(
                f"💼 Работа {'✅' if settings['work_reminder_enabled'] else '❌'}",
                callback_data=CB_WORK_REMINDER_TOGGLE
            )
        ],
        [
            InlineKeyboardButton(
                f"☕ Перерыв {'✅' if settings['break_reminder_enabled'] else '❌'}",
                callback_data=CB_BREAK_REMINDER_TOGGLE
            )
        ],
        [
            InlineKeyboardButton(
                f"⏰ Длинный перерыв {'✅' if settings['long_break_reminder_enabled'] else '❌'}",
                callback_data=CB_LONG_BREAK_REMINDER_TOGGLE
            )
        ],
        [
            InlineKeyboardButton(
                f"🎯 Ежедневная цель {'✅' if settings['daily_goal_enabled'] else '❌'}",
                callback_data=CB_DAILY_GOAL_TOGGLE
            )
        ],
        [
            InlineKeyboardButton("⚙️ Настройки времени", callback_data=CB_REMINDERS_SETTINGS)
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Создаем сообщение с текущими настройками
    message_text = (
        "🔔 <b>Настройки напоминаний</b>\n\n"
        "💼 Напоминание о работе: каждые {} мин {}\n"
        "☕ Напоминание о перерыве: каждые {} мин {}\n"
        "⏰ Напоминание о длинном перерыве: каждые {} мин {}\n"
        "🎯 Ежедневная цель: {} мин {}\n\n"
        "Используйте кнопки ниже для включения/выключения напоминаний."
    ).format(
        settings['work_reminder_minutes'],
        '✅' if settings['work_reminder_enabled'] else '❌',
        settings['break_reminder_minutes'],
        '✅' if settings['break_reminder_enabled'] else '❌',
        settings['long_break_reminder_minutes'],
        '✅' if settings['long_break_reminder_enabled'] else '❌',
        settings['daily_goal_minutes'],
        '✅' if settings['daily_goal_enabled'] else '❌'
    )

    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def reminders_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки напоминаний."""
    query = update.callback_query
    await query.answer()

    user = query.from_user

    # Получаем текущие настройки
    settings = await Database.get_reminder_settings(user.id)

    if query.data == CB_WORK_REMINDER_TOGGLE:
        # Переключаем напоминание о работе
        await Database.update_reminder_settings(
            user.id,
            work_reminder_enabled=1 if not settings['work_reminder_enabled'] else 0
        )

    elif query.data == CB_BREAK_REMINDER_TOGGLE:
        # Переключаем напоминание о перерыве
        await Database.update_reminder_settings(
            user.id,
            break_reminder_enabled=1 if not settings['break_reminder_enabled'] else 0
        )

    elif query.data == CB_LONG_BREAK_REMINDER_TOGGLE:
        # Переключаем напоминание о длинном перерыве
        await Database.update_reminder_settings(
            user.id,
            long_break_reminder_enabled=1 if not settings['long_break_reminder_enabled'] else 0
        )

    elif query.data == CB_DAILY_GOAL_TOGGLE:
        # Переключаем ежедневную цель
        await Database.update_reminder_settings(
            user.id,
            daily_goal_enabled=1 if not settings['daily_goal_enabled'] else 0
        )

    elif query.data == CB_REMINDERS_SETTINGS:
        # Показываем меню настройки времени
        keyboard = [
            [
                InlineKeyboardButton("⏰ Установить время работы (мин)", callback_data="set_work_time"),
                InlineKeyboardButton(f"{settings['work_reminder_minutes']}", callback_data="work_time_current")
            ],
            [
                InlineKeyboardButton("☕ Установить время перерыва (мин)", callback_data="set_break_time"),
                InlineKeyboardButton(f"{settings['break_reminder_minutes']}", callback_data="break_time_current")
            ],
            [
                InlineKeyboardButton("⏰ Установить время длинного перерыва (мин)", callback_data="set_long_break_time"),
                InlineKeyboardButton(f"{settings['long_break_reminder_minutes']}", callback_data="long_break_time_current")
            ],
            [
                InlineKeyboardButton("🎯 Установить ежедневную цель (мин)", callback_data="set_daily_goal"),
                InlineKeyboardButton(f"{settings['daily_goal_minutes']}", callback_data="daily_goal_current")
            ],
            [
                InlineKeyboardButton("⬅️ Назад", callback_data="back_to_reminders")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "⚙️ <b>Настройка времени напоминаний</b>\n\n"
            "Нажмите на кнопку с временем, чтобы изменить значение.",
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
        return

    elif query.data.startswith("set_"):
        # Обработка кнопок установки времени
        time_type = query.data.replace("set_", "").replace("_time", "_reminder_minutes")

        # Сохраняем тип времени в контексте для последующей обработки
        context.user_data["setting_reminder_time"] = time_type
        context.user_data["is_callback"] = True

        await query.edit_message_text(
            f"⏰ Введите новое значение для {query.data.replace('set_', '').replace('_time', '').replace('_', ' ')} (в минутах):"
        )

    elif query.data == "back_to_reminders":
        # Возврат к главному меню напоминаний
        await reminders_command(query.message, context)

    elif query.data.endswith("_current"):
        # Обработка кнопок текущих значений времени - показываем инструкцию
        time_type = query.data.replace("_current", "").replace("_time", "_reminder_minutes")
        time_name = query.data.replace("_time_current", "").replace("_", " ").title()

        await query.edit_message_text(
            f"📊 <b>Текущее значение: {time_name}</b>\n\n"
            f"Нажмите на кнопку \"Установить {time_name}\" для изменения значения."
        )

    else:
        # Показываем обновленные настройки
        await reminders_command(query.message, context)

async def handle_reminder_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ввода нового значения времени напоминаний."""
    user = update.effective_user

    # Проверяем, что пользователь устанавливает время напоминаний
    if context.user_data.get("setting_reminder_time"):
        # Обрабатываем ввод времени напоминаний
        await _process_reminder_time_input(update, context)
    else:
        # Если не в режиме установки времени, передаем обработку заметкам
        await save_note(update, context)

async def _process_reminder_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Внутренняя функция для обработки ввода времени напоминаний."""
    user = update.effective_user

    try:
        # Получаем введенное значение
        minutes_str = update.message.text.strip()
        minutes = int(minutes_str)

        # Проверяем границы значений
        if minutes < 1 or minutes > 10080:  # Максимум неделя в минутах
            await update.message.reply_text(
                "❌ Неверное значение! Введите число от 1 до 10080 (максимум неделя в минутах)."
            )
            return

        # Получаем тип времени из контекста
        time_type = context.user_data["setting_reminder_time"]

        # Обновляем настройки в базе данных
        await Database.update_reminder_settings(user.id, **{time_type: minutes})

        # Очищаем контекст
        context.user_data.pop("setting_reminder_time", None)
        context.user_data.pop("is_callback", None)

        # Показываем обновленные настройки
        await update.message.reply_text(
            f"✅ Время напоминаний обновлено!\n"
            f"Отправьте /reminders для просмотра настроек."
        )

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат! Введите число минут (например: 60)."
        )
    except Exception as e:
        await update.message.reply_text(
            f"❌ Ошибка при обновлении настроек: {str(e)}"
        )

async def calendar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /calendar для просмотра календаря работы."""
    user = update.effective_user

    # Проверяем, есть ли у пользователя данные для календаря
    sessions = await Database.get_sessions_by_timeframe(user.id, datetime.datetime.min, datetime.datetime.max)

    if not sessions:
        await update.message.reply_text(
            "У вас пока нет данных для просмотра календаря.\n"
            "Начните работать с ботом, чтобы накопить статистику!"
        )
        return

    # Показываем календарь на текущий месяц
    await show_calendar_month(update.message, user.id)

async def categories_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /categories для управления категориями."""
    user = update.effective_user

    # Получаем информацию о категориях
    categories_info = get_categories_info()

    # Создаем клавиатуру для управления категориями
    keyboard = [
        [InlineKeyboardButton("📋 Показать категории", callback_data="show_categories")],
        [InlineKeyboardButton("🔄 Перезагрузить категории", callback_data="reload_categories")],
        [InlineKeyboardButton("✏️ Редактировать категории", callback_data="edit_categories")]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Создаем сообщение с информацией о категориях
    message_text = (
        "📂 <b>Управление категориями</b>\n\n"
        f"📋 Категорий работы: {len(categories_info['work_categories'])}\n"
        f"📝 Категорий заметок: {len(categories_info['note_categories'])}\n"
        f"📁 Файл конфигурации: {categories_info['file_path']}\n\n"
        "Используйте кнопки ниже для управления категориями."
    )

    await update.message.reply_text(
        message_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def show_calendar_month(message, user_id: int, year: int = None, month: int = None) -> None:
    """Показывает календарь на указанный месяц."""
    if year is None or month is None:
        today = datetime.date.today()
        year, month = today.year, today.month

    # Получаем календарь для месяца
    import calendar
    cal = calendar.monthcalendar(year, month)

    # Получаем статистику для каждого дня месяца
    month_stats = {}
    for week in cal:
        for day in week:
            if day > 0:
                day_date = datetime.date(year, month, day)
                stats = await Database.get_daily_stats(user_id, day_date)
                month_stats[day] = stats

    # Создаем клавиатуру календаря
    keyboard = []

    # Заголовок с месяцем и годом
    month_name = calendar.month_name[month]
    keyboard.append([InlineKeyboardButton(f"📅 {month_name} {year}", callback_data="calendar_ignore")])

    # Дни недели
    days_row = []
    for day_name in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']:
        days_row.append(InlineKeyboardButton(day_name, callback_data="calendar_ignore"))
    keyboard.append(days_row)

    # Дни месяца
    for week in cal:
        week_row = []
        for day in week:
            if day == 0:
                # Пустая ячейка для дней предыдущего/следующего месяца
                week_row.append(InlineKeyboardButton(" ", callback_data="calendar_ignore"))
            else:
                stats = month_stats.get(day, {})
                total_duration = stats.get('total_duration', 0)

                if total_duration > 0:
                    hours, remainder = divmod(total_duration, 3600)
                    minutes = remainder // 60

                    if hours > 0:
                        day_text = f"{day} ({hours}ч)"
                    else:
                        day_text = f"{day} ({minutes}м)"
                else:
                    day_text = str(day)

                week_row.append(InlineKeyboardButton(day_text, callback_data=f"calendar_day_{year}_{month}_{day}"))

        keyboard.append(week_row)

    # Кнопки навигации
    nav_row = []
    if month > 1:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data=f"calendar_month_{year}_{month-1}"))
    else:
        nav_row.append(InlineKeyboardButton("⬅️", callback_data="calendar_ignore"))

    nav_row.append(InlineKeyboardButton("Сегодня", callback_data=f"calendar_today"))
    nav_row.append(InlineKeyboardButton(f"{month}/{year}", callback_data="calendar_ignore"))

    if month < 12:
        nav_row.append(InlineKeyboardButton("➡️", callback_data=f"calendar_month_{year}_{month+1}"))
    else:
        nav_row.append(InlineKeyboardButton("➡️", callback_data="calendar_ignore"))

    keyboard.append(nav_row)

    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(
        "📅 <b>Календарь работы</b>\n\n"
        "Выберите день для просмотра детальной статистики.\n"
        "Числа показывают время работы в часах или минутах.",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на календарь."""
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "calendar_today" or data == "calendar_show":
        # Показываем календарь на текущий месяц
        await show_calendar_month(query.message, query.from_user.id)

    elif data.startswith("calendar_month_"):
        # Переход к другому месяцу
        parts = data.split("_")
        if len(parts) >= 4:
            year, month = parts[2], parts[3]
            await show_calendar_month(query.message, query.from_user.id, int(year), int(month))
        else:
            await query.edit_message_text("❌ Ошибка формата месяца календаря")
            return

    elif data.startswith("calendar_day_"):
        # Показываем статистику за выбранный день
        parts = data.split("_")
        if len(parts) >= 4:
            year, month, day = parts[2], parts[3], parts[4]
            selected_date = datetime.date(int(year), int(month), int(day))
        else:
            await query.edit_message_text("❌ Ошибка формата даты календаря")
            return

        stats = await Database.get_daily_stats(query.from_user.id, selected_date)
        await show_day_stats(query, stats)

    elif data == "calendar_ignore":
        # Игнорируем нажатие
        pass

async def show_day_stats(query, stats: Dict[str, Any]) -> None:
    """Показывает статистику за выбранный день."""
    # Форматируем продолжительность
    total_hours, remainder = divmod(stats["total_duration"], 3600)
    total_minutes, total_seconds = divmod(remainder, 60)

    break_hours, remainder = divmod(stats["break_duration"], 3600)
    break_minutes, break_seconds = divmod(remainder, 60)

    # Формируем сообщение
    message_text = (
        f"📊 <b>Статистика за {stats['date']}</b>\n\n"
        f"📝 Всего сессий: {stats['total_sessions']}\n"
        f"✅ Завершено: {stats['completed_sessions']}\n"
        f"⏱️ Активно: {stats['active_sessions']}\n\n"
        f"⌛ Общее время работы: {total_hours}ч {total_minutes}м {total_seconds}с\n"
        f"⏸️ Перерывов: {stats['total_breaks']}\n"
        f"☕ Время перерывов: {break_hours}ч {break_minutes}м {break_seconds}с\n\n"
    )

    # Добавляем информацию по категориям
    if stats["categories"]:
        message_text += "<b>По категориям:</b>\n"
        for category, data in stats["categories"].items():
            cat_hours, remainder = divmod(data["duration"], 3600)
            cat_minutes, cat_seconds = divmod(remainder, 60)
            message_text += f"- {category}: {data['count']} сессий, {cat_hours}ч {cat_minutes}м\n"
    else:
        message_text += "Нет данных по категориям."

    # Кнопка возврата к календарю
    keyboard = [[InlineKeyboardButton("⬅️ К календарю", callback_data="calendar_today")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем статистику
    await query.edit_message_text(
        text=message_text,
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def categories_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на кнопки управления категориями."""
    query = update.callback_query
    await query.answer()

    if query.data == "show_categories":
        # Показываем текущие категории
        categories_info = get_categories_info()

        message_text = (
            "📋 <b>Текущие категории</b>\n\n"
            "<b>Категории работы:</b>\n"
            f"{', '.join(f'• {cat}' for cat in categories_info['work_categories'])}\n\n"
            "<b>Категории заметок:</b>\n"
            f"{', '.join(f'• {cat}' for cat in categories_info['note_categories'])}\n\n"
            f"📁 Загружено из: {categories_info['file_path']}\n"
            f"🕐 Последняя загрузка: {categories_info['last_load_time'][:19]}"
        )

        await query.edit_message_text(
            text=message_text,
            parse_mode="HTML"
        )

    elif query.data == "reload_categories":
        # Перезагружаем категории из файла
        reload_result = reload_categories()

        if reload_result.get('loaded_from_file'):
            message_text = "✅ Категории успешно перезагружены из файла"
        else:
            message_text = "❌ Не удалось перезагрузить категории из файла"

        await query.edit_message_text(
            text=message_text
        )

    elif query.data == "edit_categories":
        # Показываем инструкцию по редактированию файла
        message_text = (
            "✏️ <b>Редактирование категорий</b>\n\n"
            "Для изменения категорий отредактируйте файл <code>categories.json</code>\n\n"
            "<b>Структура файла:</b>\n"
            "<code>{\n"
            '  "work_categories": ["Разработка", "Совещания", "Документация"],\n'
            '  "note_categories": ["Общее", "Идея", "Задача"]\n'
            "}</code>\n\n"
            "После редактирования используйте команду <code>/categories</code> → <code>Перезагрузить категории</code>"
        )

        await query.edit_message_text(
            text=message_text,
            parse_mode="HTML"
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stats для просмотра статистики."""
    user = update.effective_user

    # Проверяем, есть ли у пользователя данные для статистики
    sessions = await Database.get_sessions_by_timeframe(user.id, datetime.datetime.min, datetime.datetime.max)

    if not sessions:
        await update.message.reply_text(
            "У вас пока нет данных для просмотра статистики.\n"
            "Начните работать с ботом, чтобы накопить статистику!"
        )
        return

    # Создаем клавиатуру для выбора периода
    keyboard = [
        [
            InlineKeyboardButton("📅 День", callback_data=CB_STATS_DAY),
            InlineKeyboardButton("📆 Неделя", callback_data=CB_STATS_WEEK),
            InlineKeyboardButton("📊 Месяц", callback_data=CB_STATS_MONTH)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Отправляем сообщение с выбором периода
    await update.message.reply_text(
        "📊 Выберите период для просмотра статистики:",
        reply_markup=reply_markup
    )

async def stats_period_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора периода статистики."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    today = datetime.date.today()

    # Определяем тип статистики по callback_data
    if query.data == CB_STATS_DAY:
        # Статистика за день
        stats = await Database.get_daily_stats(user.id, today)
        await send_daily_stats(query, stats)

    elif query.data == CB_STATS_WEEK:
        # Статистика за неделю
        stats = await Database.get_weekly_stats(user.id, today)
        await send_weekly_stats(query, stats)

    elif query.data == CB_STATS_MONTH:
        # Статистика за месяц
        stats = await Database.get_monthly_stats(user.id, today.year, today.month)
        await send_monthly_stats(query, stats)

    # Обновляем кнопки статистики в интерфейсе, если пользователь нажал на кнопку статистики

async def note_category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик выбора категории заметки."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    category = query.data.replace("note_category_", "")

    # Сохраняем выбранную категорию в контексте
    context.user_data["note_category"] = category

    await query.edit_message_text(
        f"📝 Выбрана категория: {category}\n\n"
        "Теперь введите текст заметки:"
    )

    return WAITING_NOTE_TEXT

    # Обновляем кнопки статистики в интерфейсе, если пользователь нажал на кнопку статистики
    # (чтобы показать выбранный период)
    if hasattr(query, 'message') and query.message:
        # Получаем активную сессию для обновления кнопок
        active_session = await Database.get_active_session(user.id)

        if active_session:
            if active_session["status"] == "active":
                keyboard = [
                    [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
                    [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
                    [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                    [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                    [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
                    [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
                    [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                    [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)],
                    [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
                ]
        else:
            keyboard = [
                [InlineKeyboardButton("▶️ Начать работу", callback_data=CB_START_WORK)],
                [InlineKeyboardButton("📊 Статистика", callback_data=CB_STATS_DAY)],
                [InlineKeyboardButton("📁 Экспорт CSV", callback_data=CB_EXPORT_CSV)]
            ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Обновляем сообщение с новыми кнопками
        try:
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        except:
            pass  # Игнорируем ошибки обновления кнопок

async def send_daily_stats(query: CallbackQuery, stats: Dict[str, Any]) -> None:
    """Отправляет статистику за день."""
    # Форматируем продолжительность
    total_hours, remainder = divmod(stats["total_duration"], 3600)
    total_minutes, total_seconds = divmod(remainder, 60)
    
    break_hours, remainder = divmod(stats["break_duration"], 3600)
    break_minutes, break_seconds = divmod(remainder, 60)
    
    # Формируем сообщение
    message_text = (
        f"📊 <b>Статистика за {stats['date']}</b>\n\n"
        f"📝 Всего сессий: {stats['total_sessions']}\n"
        f"✅ Завершено: {stats['completed_sessions']}\n"
        f"⏱️ Активно: {stats['active_sessions']}\n\n"
        f"⌛ Общее время работы: {total_hours}ч {total_minutes}м {total_seconds}с\n"
        f"⏸️ Перерывов: {stats['total_breaks']}\n"
        f"☕ Время перерывов: {break_hours}ч {break_minutes}м {break_seconds}с\n\n"
    )
    
    # Добавляем информацию по категориям
    if stats["categories"]:
        message_text += "<b>По категориям:</b>\n"
        for category, data in stats["categories"].items():
            cat_hours, remainder = divmod(data["duration"], 3600)
            cat_minutes, cat_seconds = divmod(remainder, 60)
            message_text += f"- {category}: {data['count']} сессий, {cat_hours}ч {cat_minutes}м\n"
    else:
        message_text += "Нет данных по категориям."
    
    # Отправляем статистику
    await query.edit_message_text(
        text=message_text,
        parse_mode="HTML"
    )

async def send_weekly_stats(query: CallbackQuery, stats: Dict[str, Any]) -> None:
    """Отправляет статистику за неделю."""
    # Форматируем продолжительность
    total_hours, remainder = divmod(stats["total_duration"], 3600)
    total_minutes, total_seconds = divmod(remainder, 60)
    
    # Формируем сообщение
    message_text = (
        f"📊 <b>Статистика за неделю</b>\n"
        f"<i>с {stats['start_date']} по {stats['end_date']}</i>\n\n"
        f"📝 Всего сессий: {stats['total_sessions']}\n"
        f"⌛ Общее время работы: {total_hours}ч {total_minutes}м\n"
        f"⏸️ Перерывов: {stats['total_breaks']}\n\n"
    )
    
    # Добавляем информацию по категориям
    if stats["categories"]:
        message_text += "<b>По категориям:</b>\n"
        for category, data in stats["categories"].items():
            cat_hours, remainder = divmod(data["duration"], 3600)
            cat_minutes, cat_seconds = divmod(remainder, 60)
            message_text += f"- {category}: {data['count']} сессий, {cat_hours}ч {cat_minutes}м\n"
        
        message_text += "\n"
    
    # Добавляем информацию по дням недели
    message_text += "<b>По дням недели:</b>\n"
    days_of_week = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
    
    for i, day_stats in enumerate(stats["daily_stats"]):
        day_name = days_of_week[i]
        day_hours, remainder = divmod(day_stats["total_duration"], 3600)
        day_minutes, day_seconds = divmod(remainder, 60)
        
        message_text += f"- {day_name}: {day_stats['completed_sessions']} сессий, {day_hours}ч {day_minutes}м\n"
    
    # Отправляем статистику
    await query.edit_message_text(
        text=message_text,
        parse_mode="HTML"
    )

async def send_monthly_stats(query: CallbackQuery, stats: Dict[str, Any]) -> None:
    """Отправляет статистику за месяц."""
    # Форматируем продолжительность
    total_hours, remainder = divmod(stats["total_duration"], 3600)
    total_minutes, total_seconds = divmod(remainder, 60)
    
    # Формируем сообщение
    message_text = (
        f"📊 <b>Статистика за {stats['month_name']} {stats['year']}</b>\n\n"
        f"📝 Всего сессий: {stats['total_sessions']}\n"
        f"⌛ Общее время работы: {total_hours}ч {total_minutes}м\n"
        f"⏸️ Перерывов: {stats['total_breaks']}\n\n"
    )
    
    # Добавляем информацию по категориям
    if stats["categories"]:
        message_text += "<b>По категориям:</b>\n"
        for category, data in stats["categories"].items():
            cat_hours, remainder = divmod(data["duration"], 3600)
            cat_minutes, cat_seconds = divmod(remainder, 60)
            message_text += f"- {category}: {data['count']} сессий, {cat_hours}ч {cat_minutes}м\n"
        
        message_text += "\n"
    
    # Добавляем информацию по неделям
    message_text += "<b>По неделям:</b>\n"
    for i, week_stats in enumerate(stats["weekly_stats"], 1):
        week_hours, remainder = divmod(week_stats["total_duration"], 3600)
        week_minutes, week_seconds = divmod(remainder, 60)
        
        message_text += (
            f"- Неделя {i} ({week_stats['start_date']} - {week_stats['end_date']}): "
            f"{week_stats['total_sessions']} сессий, {week_hours}ч {week_minutes}м\n"
        )
    
    # Отправляем статистику
    await query.edit_message_text(
        text=message_text,
        parse_mode="HTML"
    )

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик сохранения текста заметки."""
    user = update.effective_user
    note_text = update.message.text

    # Проверяем, есть ли активная сессия
    active_session = await Database.get_active_session(user.id)

    if not active_session:
        await update.message.reply_text(
            "У вас нет активной рабочей сессии.\n"
            "Чтобы начать работу, используйте /start_work"
        )
        return

    session_id = active_session["id"]

    # Получаем категорию заметки из контекста
    note_category = context.user_data.get("note_category", "Общее")

    print(f"DEBUG: Сохраняем заметку для сессии {session_id}: {note_text[:20]}... Категория: {note_category}")

    # Добавляем заметку в базу данных
    note_id = await Database.add_note(user.id, note_text, session_id, note_category)
    
    # Формируем клавиатуру в зависимости от статуса сессии
    keyboard = []
    
    if active_session["status"] == SESSION_STATUS["ACTIVE"]:
        keyboard = [
            [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
            [InlineKeyboardButton("📝 Еще заметка", callback_data=CB_ADD_NOTE)],
            [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
        ]
    elif active_session["status"] == SESSION_STATUS["PAUSED"]:
        keyboard = [
            [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
            [InlineKeyboardButton("📝 Еще заметка", callback_data=CB_ADD_NOTE)],
            [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем подтверждение
    current_time = datetime.datetime.now().strftime("%H:%M:%S")
    
    await update.message.reply_text(
        f"📝 Заметка сохранена!\n"
        f"🕘 Время: {current_time}\n"
        f"💼 Активность: {active_session['category']}\n\n"
        f"Вы можете продолжать работу.",
        reply_markup=reply_markup
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена текущего диалога."""
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатия на инлайн кнопки."""
    query = update.callback_query
    await query.answer()
    
    print(f"DEBUG: Нажата кнопка: {query.data}")
    
    if query.data == CB_START_WORK:
        # Вызываем команду начала работы
        await start_work_command(update, context)
    
    elif query.data == CB_END_WORK:
        user = query.from_user
        session_info = await Database.end_work_session(user.id)
        
        if not session_info:
            await query.edit_message_text(
                "У вас нет активной рабочей сессии.\n"
                "Чтобы начать новую сессию, используйте /start_work"
            )
            return

        # Форматирование данных
        start_time = datetime.datetime.fromisoformat(session_info["start_time"])
        end_time = datetime.datetime.fromisoformat(session_info["end_time"]) 
        hours, remainder = divmod(session_info["duration"], 3600)
        minutes, seconds = divmod(remainder, 60)
        
        await query.edit_message_text(
            f"✅ Рабочая сессия завершена\n"
            f"🏷️ Категория: {session_info['category']}\n"
            f"⏱️ Начало: {start_time.strftime('%H:%M:%S')}\n"
            f"⏱️ Конец: {end_time.strftime('%H:%M:%S')}\n"
            f"⌛ Продолжительность: {hours}ч {minutes}м {seconds}с\n\n"
            f"Хорошей работы! Для начала новой сессии используйте /start_work"
        )
    
    elif query.data == CB_BREAK_WORK:
        user = query.from_user
        
        # Приостанавливаем сессию
        session = await Database.pause_work_session(user.id, "Перерыв")
        
        if not session:
            await query.edit_message_text(
                "У вас нет активной рабочей сессии.\n"
                "Чтобы начать работу, используйте /start_work"
            )
            return
        
        # Формируем клавиатуру
        keyboard = [
            [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
            [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
            [InlineKeyboardButton("⏹️ Завершить день", callback_data=CB_END_WORK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение о паузе
        start_time = datetime.datetime.fromisoformat(session["start_time"])
        duration = datetime.datetime.now() - start_time
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        await query.edit_message_text(
            f"⏸️ Пауза: \"Перерыв\"\n"
            f"⏱️ Отработано: {hours}ч {minutes}мин\n\n"
            f"Чтобы продолжить, используйте /resume",
            reply_markup=reply_markup
        )
    
    elif query.data == CB_RESUME_WORK:
        user = query.from_user
        
        # Возобновляем сессию
        session = await Database.resume_work_session(user.id)
        
        if not session:
            await query.edit_message_text(
                "У вас нет приостановленных сессий.\n"
                "Чтобы начать работу, используйте /start_work"
            )
            return
        
        # Формируем клавиатуру
        keyboard = [
            [InlineKeyboardButton("⏸️ Пауза", callback_data=CB_BREAK_WORK)],
            [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
            [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Отправляем сообщение о возобновлении работы
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        await query.edit_message_text(
            f"▶️ Работа возобновлена\n"
            f"⏱️ Время: {current_time}\n\n"
            f"Для завершения используйте /end_work",
            reply_markup=reply_markup
        )
    
    elif query.data == CB_ADD_NOTE:
        user = query.from_user

        # Проверяем, есть ли активная сессия
        active_session = await Database.get_active_session(user.id)

        if not active_session:
            await query.edit_message_text(
                "У вас нет активной рабочей сессии.\n"
                "Чтобы начать работу, используйте /start_work"
            )
            return

        # Сохраняем ID активной сессии в контексте
        context.user_data["active_session_id"] = active_session["id"]
        context.user_data["is_callback"] = True

        # Создаем клавиатуру с категориями заметок
        note_categories = get_note_categories()
        keyboard = []
        for category in note_categories:
            keyboard.append([InlineKeyboardButton(category, callback_data=f"note_category_{category}")])
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            "📝 Выберите категорию заметки:",
            reply_markup=reply_markup
        )

    elif query.data == CB_EXPORT_CSV:
        user = query.from_user

        # Проверяем, есть ли у пользователя данные для экспорта
        sessions = await Database.get_sessions_by_timeframe(user.id, datetime.datetime.min, datetime.datetime.max)

        if not sessions:
            await query.edit_message_text(
                "У вас пока нет данных для экспорта.\n"
                "Начните работать с ботом, чтобы накопить статистику!"
            )
            return

        # Отправляем сообщение о начале экспорта
        await query.edit_message_text(
            "📊 Готовлю CSV файл с вашими данными...\n"
            "Это может занять несколько секунд."
        )

        # Создаем временный файл для экспорта
        import tempfile
        import os

        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, f'work_tracker_export_{user.id}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

        try:
            # Экспортируем все данные пользователя
            success = await Database.export_user_data_to_csv(user.id, file_path)

            if success:
                # Отправляем файл пользователю через обычное сообщение (не через edit_message_text)
                # Сначала восстанавливаем исходное сообщение
                await query.edit_message_text(
                    "📊 Файл готов! Отправляю ваш отчет..."
                )

                # Создаем новое сообщение с файлом
                await context.bot.send_document(
                    chat_id=query.message.chat_id,
                    document=open(file_path, 'rb'),
                    filename=f'work_tracker_{user.first_name}_{datetime.datetime.now().strftime("%Y%m%d")}.csv',
                    caption="📊 Ваш полный отчет по работе в формате CSV"
                )

                # Удаляем временный файл
                os.remove(file_path)

            else:
                await query.edit_message_text(
                    "❌ Произошла ошибка при создании CSV файла.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )

        except Exception as e:
            await query.edit_message_text(
                f"❌ Ошибка при экспорте: {str(e)}\n"
                "Попробуйте позже."
            )

            # Удаляем файл в случае ошибки
            try:
                os.remove(file_path)
            except:
                pass

async def init() -> None:
    """Инициализация базы данных."""
    await Database.init_db()

def main() -> None:
    """Основная функция запуска бота."""
    # Инициализируем базу данных
    import asyncio
    asyncio.run(init())
    
    # Создаем и настраиваем бота с увеличенным таймаутом для соединения
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).connect_timeout(30.0).build()
    
    # Добавляем обработчик ошибок
    application.add_error_handler(error_handler)
    
    # Добавляем базовые обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("end_work", end_work_command))
    application.add_handler(CommandHandler("break", break_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("note", note_command))
    application.add_handler(CommandHandler("my_notes", my_notes_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("reminders", reminders_command))
    application.add_handler(CommandHandler("calendar", calendar_command))
    application.add_handler(CommandHandler("categories", categories_command))
    application.add_handler(CommandHandler("start_work", start_work_command))
    
    # Обработчик для выбора категорий работы
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category_"))

    # Обработчик для выбора периода статистики
    application.add_handler(CallbackQueryHandler(stats_period_callback, pattern=r"^stats_"))

    # Обработчик для выбора категории заметки
    application.add_handler(CallbackQueryHandler(note_category_callback, pattern=r"^note_category_"))

    # Обработчик для кнопок напоминаний
    application.add_handler(CallbackQueryHandler(reminders_callback, pattern=r"^reminders_"))

    # Обработчик для календаря
    application.add_handler(CallbackQueryHandler(calendar_callback, pattern=r"^calendar_"))

    # Обработчик для управления категориями
    application.add_handler(CallbackQueryHandler(categories_callback, pattern=r"^show_categories|reload_categories|edit_categories"))
    
    # Обработчик для ввода времени напоминаний (должен быть первым)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reminder_time_input))

    # Обработчик для текстовых сообщений (заметки)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_note))
    
    # Обработчик для инлайн кнопок (должен быть последним)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

    # Запускаем фоновые задачи
    asyncio.create_task(reminder_scheduler(application.bot))
    asyncio.create_task(categories_monitor())

async def reminder_scheduler(bot) -> None:
    """Фоновая задача для отправки напоминаний."""
    while True:
        try:
            await check_and_send_reminders(bot)
            await asyncio.sleep(60)  # Проверяем каждые 60 секунд
        except Exception as e:
            logger.error(f"Ошибка в планировщике напоминаний: {e}")
            await asyncio.sleep(60)

async def categories_monitor() -> None:
    """Фоновая задача для мониторинга изменений файла категорий."""
    while True:
        try:
            # Проверяем изменения файла categories.json каждые 5 минут
            await asyncio.sleep(300)  # 5 минут

            # Принудительно перезагружаем категории
            reload_result = reload_categories()

            if reload_result.get('loaded_from_file') and not reload_result.get('file_unchanged', False):
                logger.info("Файл categories.json изменен, категории перезагружены")
            elif reload_result.get('error'):
                logger.warning(f"Ошибка при мониторинге categories.json: {reload_result.get('error')}")

        except Exception as e:
            logger.error(f"Ошибка в мониторинге категорий: {e}")
            await asyncio.sleep(300)

async def check_and_send_reminders(bot) -> None:
    """Проверка и отправка напоминаний пользователям."""
    try:
        # Получаем всех пользователей
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT user_id FROM users') as cursor:
                users = [row['user_id'] for row in await cursor.fetchall()]

        for user_id in users:
            try:
                # Получаем настройки напоминаний пользователя
                settings = await Database.get_reminder_settings(user_id)

                # Проверяем активную сессию пользователя
                active_session = await Database.get_active_session(user_id)

                if active_session:
                    session_start = datetime.datetime.fromisoformat(active_session['start_time'])
                    current_time = datetime.datetime.now()
                    session_duration = (current_time - session_start).total_seconds() / 60  # в минутах

                    # Напоминание о работе (если сессия длится слишком долго)
                    if (settings['work_reminder_enabled'] and
                        session_duration >= settings['work_reminder_minutes']):

                        last_reminder = await Database.get_last_reminder_time(user_id, 'work_reminder')
                        minutes_since_last = (current_time - last_reminder).total_seconds() / 60

                        if minutes_since_last >= settings['work_reminder_minutes']:
                            await send_work_reminder(bot, user_id, active_session)
                            await Database.log_sent_reminder(user_id, 'work_reminder', active_session['id'])

                    # Напоминание о перерыве (если сессия длится слишком долго без перерыва)
                    if (settings['break_reminder_enabled'] and
                        session_duration >= settings['break_reminder_minutes']):

                        # Проверяем, был ли перерыв недавно
                        breaks = await Database.get_session_breaks(active_session['id'])
                        has_recent_break = any(
                            datetime.datetime.fromisoformat(b['start_time']) > current_time - datetime.timedelta(minutes=settings['break_reminder_minutes'])
                            for b in breaks if b['start_time']
                        )

                        if not has_recent_break:
                            last_reminder = await Database.get_last_reminder_time(user_id, 'break_reminder')
                            minutes_since_last = (current_time - last_reminder).total_seconds() / 60

                            if minutes_since_last >= settings['break_reminder_minutes']:
                                await send_break_reminder(bot, user_id, active_session)
                                await Database.log_sent_reminder(user_id, 'break_reminder', active_session['id'])

                    # Напоминание о длинном перерыве (если сессия очень долгая)
                    if (settings['long_break_reminder_enabled'] and
                        session_duration >= settings['long_break_reminder_minutes']):

                        last_reminder = await Database.get_last_reminder_time(user_id, 'long_break_reminder')
                        minutes_since_last = (current_time - last_reminder).total_seconds() / 60

                        if minutes_since_last >= settings['long_break_reminder_minutes']:
                            await send_long_break_reminder(bot, user_id, active_session)
                            await Database.log_sent_reminder(user_id, 'long_break_reminder', active_session['id'])

                # Напоминание о ежедневной цели
                if settings['daily_goal_enabled']:
                    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
                    today_end = datetime.datetime.combine(datetime.date.today(), datetime.time.max)

                    daily_sessions = await Database.get_sessions_by_timeframe(user_id, today_start, today_end)
                    daily_duration = sum(s['duration'] for s in daily_sessions if s['duration'])

                    if daily_duration >= settings['daily_goal_minutes'] * 60:  # переводим в секунды
                        last_reminder = await Database.get_last_reminder_time(user_id, 'daily_goal')
                        minutes_since_last = (datetime.datetime.now() - last_reminder).total_seconds() / 60

                        if minutes_since_last >= 60:  # Напоминаем раз в час после достижения цели
                            await send_daily_goal_reminder(bot, user_id, daily_duration)
                            await Database.log_sent_reminder(user_id, 'daily_goal')

            except Exception as e:
                logger.error(f"Ошибка при проверке напоминаний для пользователя {user_id}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при получении списка пользователей: {e}")

async def send_work_reminder(bot, user_id: int, session) -> None:
    """Отправка напоминания о длительной работе."""
    try:
        keyboard = [
            [InlineKeyboardButton("⏸️ Сделать перерыв", callback_data=CB_BREAK_WORK)],
            [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await bot.send_message(
            chat_id=user_id,
            text=(
                "💼 <b>Напоминание о работе</b>\n\n"
                "Вы работаете уже довольно долго. Рекомендуется сделать перерыв!\n\n"
                f"Категория: {session['category']}\n"
                "Используйте кнопки ниже для действий."
            ),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания о работе пользователю {user_id}: {e}")

async def send_break_reminder(bot, user_id: int, session) -> None:
    """Отправка напоминания о перерыве."""
    try:
        keyboard = [
            [InlineKeyboardButton("⏸️ Сделать перерыв", callback_data=CB_BREAK_WORK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await bot.send_message(
            chat_id=user_id,
            text=(
                "☕ <b>Рекомендация перерыва</b>\n\n"
                "Вы работаете уже некоторое время. Самое время сделать небольшой перерыв!\n\n"
                f"Категория: {session['category']}"
            ),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания о перерыве пользователю {user_id}: {e}")

async def send_long_break_reminder(bot, user_id: int, session) -> None:
    """Отправка напоминания о длинном перерыве."""
    try:
        keyboard = [
            [InlineKeyboardButton("⏸️ Сделать длинный перерыв", callback_data=CB_BREAK_WORK)]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await bot.send_message(
            chat_id=user_id,
            text=(
                "⏰ <b>Рекомендация длинного перерыва</b>\n\n"
                "Вы работаете уже очень долго! Рекомендуется сделать более длительный перерыв для отдыха.\n\n"
                f"Категория: {session['category']}"
            ),
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания о длинном перерыве пользователю {user_id}: {e}")

async def send_daily_goal_reminder(bot, user_id: int, daily_duration: int) -> None:
    """Отправка напоминания о достижении ежедневной цели."""
    try:
        hours, remainder = divmod(daily_duration, 3600)
        minutes, seconds = divmod(remainder, 60)

        await bot.send_message(
            chat_id=user_id,
            text=(
                "🎯 <b>Поздравляем!</b>\n\n"
                "Вы достигли своей ежедневной цели по времени работы!\n\n"
                f"Сегодня отработано: {hours}ч {minutes}м\n"
                "Отличная работа! Продолжайте в том же духе или завершите рабочий день."
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания о цели пользователю {user_id}: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок."""
    logger.error("Произошла ошибка: %s", context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке запроса. Попробуйте еще раз позже."
        )

if __name__ == "__main__":
    main()