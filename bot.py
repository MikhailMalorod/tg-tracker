"""
Основной модуль Telegram бота для отслеживания рабочего времени.
"""

import logging
import datetime
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, CommandHandler, ContextTypes, 
    CallbackQueryHandler, ConversationHandler,
    MessageHandler, filters
)

from database import Database, SESSION_STATUS
from config import TELEGRAM_BOT_TOKEN

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
(START_WORK, WAITING_NOTE_TEXT) = range(2)

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

# Категории работы
WORK_CATEGORIES = ["Разработка", "Совещания", "Документация", "Обучение", "Другое"]

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
                [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
            ]
        else:
            # Если есть приостановленная сессия
            keyboard = [
                [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
                [InlineKeyboardButton("📝 Заметка", callback_data=CB_ADD_NOTE)],
                [InlineKeyboardButton("⏹️ Завершить работу", callback_data=CB_END_WORK)]
            ]
    else:
        # Если нет активных сессий
        keyboard = [
            [InlineKeyboardButton("▶️ Начать работу", callback_data=CB_START_WORK)]
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
        "/stats - Статистика рабочего времени",
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
                [InlineKeyboardButton("⏹️ Завершить", callback_data=CB_END_WORK)]
            ]
        elif active_session["status"] == "paused":
            status_message = "У вас есть приостановленная рабочая сессия!"
            keyboard = [
                [InlineKeyboardButton("▶️ Продолжить", callback_data=CB_RESUME_WORK)],
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
    keyboard = []
    for category in WORK_CATEGORIES:
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
    
    # Устанавливаем состояние разговора
    context.application.conversation_key_store[(WAITING_NOTE_TEXT, None, user.id)] = WAITING_NOTE_TEXT
    
    await update.message.reply_text(
        "📝 Введите текст заметки:"
    )
    
    return WAITING_NOTE_TEXT

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
            f"{i}. {timestamp} - {note['category']}\n"
            f"<i>{note['content'][:100]}{'...' if len(note['content']) > 100 else ''}</i>\n\n"
        )
    
    # Отправляем список заметок
    await update.message.reply_text(
        message_text,
        parse_mode="HTML"
    )
    
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stats для просмотра статистики."""
    user = update.effective_user
    
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
    
    print(f"DEBUG: Сохраняем заметку для сессии {session_id}: {note_text[:20]}...")
    
    # Добавляем заметку в базу данных
    note_id = await Database.add_note(user.id, note_text, session_id)
    
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
        context.user_data["original_message"] = query.message
        
        await query.edit_message_text(
            "📝 Отправьте новое сообщение с текстом заметки:"
        )

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
    application.add_handler(CommandHandler("start_work", start_work_command))
    
    # Обработчик для выбора категорий работы
    application.add_handler(CallbackQueryHandler(category_callback, pattern=r"^category_"))
    
    # Обработчик для выбора периода статистики
    application.add_handler(CallbackQueryHandler(stats_period_callback, pattern=r"^stats_"))
    
    # Обработчик для текстовых сообщений (заметки)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_note))
    
    # Обработчик для инлайн кнопок (должен быть последним)
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик ошибок."""
    logger.error("Произошла ошибка: %s", context.error)
    if update and isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка при обработке запроса. Попробуйте еще раз позже."
        )

if __name__ == "__main__":
    main()