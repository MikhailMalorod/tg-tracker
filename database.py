"""
Модуль для работы с базой данных SQLite.
Реализует асинхронные операции с использованием aiosqlite.
"""

import aiosqlite
import datetime
from typing import Optional, Dict, List, Any, Union

from config import DATABASE_PATH

# Статусы рабочих сессий
SESSION_STATUS = {
    "ACTIVE": "active",      # Активная сессия
    "PAUSED": "paused",      # Сессия на паузе (перерыв)
    "COMPLETED": "completed" # Завершенная сессия
}

class Database:
    """Класс для асинхронной работы с базой данных SQLite."""
    
    @staticmethod
    async def init_db() -> None:
        """Инициализация базы данных и создание необходимых таблиц."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Создаем таблицу пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Создаем таблицу рабочих сессий
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    status TEXT,
                    category TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Создаем таблицу заметок (если не существует)
            await db.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    session_id INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content TEXT,
                    category TEXT DEFAULT 'Общее',
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')

            # Проверяем и добавляем колонку category, если она отсутствует
            cursor = await db.execute("PRAGMA table_info(notes)")
            columns = await cursor.fetchall()
            column_names = [col[1] for col in columns]

            if 'category' not in column_names:
                print("Добавляем колонку category в таблицу notes...")
                await db.execute('ALTER TABLE notes ADD COLUMN category TEXT DEFAULT "Общее"')
                print("Колонка category успешно добавлена в таблицу notes")

                # Обновляем существующие записи, чтобы они имели значение по умолчанию
                await db.execute('UPDATE notes SET category = "Общее" WHERE category IS NULL')
                print("Обновлены существующие записи в таблице notes")
            
            # Создаем таблицу перерывов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    user_id INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    reason TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Создаем таблицу настроек напоминаний
            await db.execute('''
                CREATE TABLE IF NOT EXISTS reminder_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    work_reminder_enabled BOOLEAN DEFAULT 1,
                    work_reminder_minutes INTEGER DEFAULT 60,
                    break_reminder_enabled BOOLEAN DEFAULT 1,
                    break_reminder_minutes INTEGER DEFAULT 15,
                    long_break_reminder_enabled BOOLEAN DEFAULT 1,
                    long_break_reminder_minutes INTEGER DEFAULT 120,
                    daily_goal_enabled BOOLEAN DEFAULT 0,
                    daily_goal_minutes INTEGER DEFAULT 480,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(user_id)
                )
            ''')

            # Создаем таблицу отправленных напоминаний
            await db.execute('''
                CREATE TABLE IF NOT EXISTS sent_reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reminder_type TEXT,
                    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    session_id INTEGER,
                    message_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')

            await db.commit()
    
    @staticmethod
    async def add_user(user_id: int, username: str, first_name: str, last_name: str) -> None:
        """Добавление нового пользователя или обновление информации о существующем."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute('''
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            await db.commit()
    
    @staticmethod
    async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе по его ID."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    
    @staticmethod
    async def start_work_session(user_id: int, category: str = "work") -> int:
        """Начало новой рабочей сессии. Возвращает ID сессии."""
        now = datetime.datetime.now()
        
        print(f"DEBUG: Создание сессии для пользователя {user_id}, категория: {category}")
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Проверяем наличие активной или приостановленной сессии
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM sessions WHERE user_id = ? AND status IN (?, ?)', 
                (user_id, SESSION_STATUS["ACTIVE"], SESSION_STATUS["PAUSED"])
            ) as cursor:
                active_session = await cursor.fetchone()
                
                if active_session:
                    print(f"DEBUG: Найдена существующая сессия: {dict(active_session)}")
                    return -1  # Уже есть активная или приостановленная сессия
            
            # Создаем новую сессию
            cursor = await db.execute('''
                INSERT INTO sessions (user_id, start_time, status, category)
                VALUES (?, ?, ?, ?)
            ''', (user_id, now, SESSION_STATUS["ACTIVE"], category))
            
            session_id = cursor.lastrowid
            await db.commit()
            print(f"DEBUG: Создана новая сессия ID: {session_id}")
            return session_id
    
    @staticmethod
    async def end_work_session(user_id: int) -> Optional[Dict[str, Any]]:
        """Завершение активной рабочей сессии. Возвращает информацию о сессии."""
        now = datetime.datetime.now()
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Получаем активную сессию
            async with db.execute(
                'SELECT * FROM sessions WHERE user_id = ? AND status = ?', 
                (user_id, SESSION_STATUS["ACTIVE"])
            ) as cursor:
                active_session = await cursor.fetchone()
                
                if not active_session:
                    return None  # Нет активной сессии
                
                session_dict = dict(active_session)
                session_id = session_dict["id"]
                start_time = datetime.datetime.fromisoformat(session_dict["start_time"])
                
                # Вычисляем продолжительность в секундах
                duration = int((now - start_time).total_seconds())
                
                # Обновляем сессию
                await db.execute('''
                    UPDATE sessions 
                    SET end_time = ?, duration = ?, status = ? 
                    WHERE id = ?
                ''', (now, duration, SESSION_STATUS["COMPLETED"], session_id))
                
                await db.commit()
                
                # Получаем обновленную информацию о сессии
                async with db.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)) as cursor:
                    updated_session = await cursor.fetchone()
                    return dict(updated_session) if updated_session else None
    
    @staticmethod
    async def get_active_session(user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации об активной сессии пользователя."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM sessions WHERE user_id = ? AND status IN (?, ?)', 
                (user_id, SESSION_STATUS["ACTIVE"], SESSION_STATUS["PAUSED"])
            ) as cursor:
                session = await cursor.fetchone()
                return dict(session) if session else None
    
    @staticmethod
    async def add_note(user_id: int, content: str, session_id: Optional[int] = None, category: str = "Общее") -> int:
        """Добавление заметки. Если session_id не указан, пытаемся найти активную сессию."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Если ID сессии не указан, пробуем найти активную
            if session_id is None:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    'SELECT id FROM sessions WHERE user_id = ? AND status = ?',
                    (user_id, SESSION_STATUS["ACTIVE"])
                ) as cursor:
                    active_session = await cursor.fetchone()
                    session_id = active_session["id"] if active_session else None

            # Добавляем заметку
            cursor = await db.execute('''
                INSERT INTO notes (user_id, session_id, content, category)
                VALUES (?, ?, ?, ?)
            ''', (user_id, session_id, content, category))

            note_id = cursor.lastrowid
            await db.commit()
            return note_id
            
    @staticmethod
    async def get_sessions_by_timeframe(user_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict[str, Any]]:
        """Получение списка сессий за указанный период времени."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            query = '''
                SELECT * FROM sessions 
                WHERE user_id = ? 
                AND (
                    (start_time BETWEEN ? AND ?) OR 
                    (end_time BETWEEN ? AND ?) OR
                    (start_time <= ? AND (end_time >= ? OR end_time IS NULL))
                )
                ORDER BY start_time ASC
            '''
            params = (
                user_id, 
                start_date, end_date, 
                start_date, end_date,
                start_date, end_date
            )
            
            sessions = []
            async with db.execute(query, params) as cursor:
                async for row in cursor:
                    sessions.append(dict(row))
            
            return sessions
            
    @staticmethod
    async def pause_work_session(user_id: int, reason: str = "Перерыв") -> Optional[Dict[str, Any]]:
        """Поставить активную сессию на паузу."""
        now = datetime.datetime.now()
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Проверяем существование таблицы breaks
            await db.execute('''
                CREATE TABLE IF NOT EXISTS breaks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER,
                    user_id INTEGER,
                    start_time TIMESTAMP,
                    end_time TIMESTAMP,
                    duration INTEGER,
                    reason TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Находим активную сессию
            async with db.execute(
                'SELECT * FROM sessions WHERE user_id = ? AND status = ?', 
                (user_id, SESSION_STATUS["ACTIVE"])
            ) as cursor:
                session = await cursor.fetchone()
                if not session:
                    return None
                    
                session_dict = dict(session)
                session_id = session_dict["id"]
                
                # Обновляем статус сессии
                await db.execute(
                    'UPDATE sessions SET status = ? WHERE id = ?', 
                    (SESSION_STATUS["PAUSED"], session_id)
                )
                
                # Добавляем запись о перерыве
                await db.execute('''
                    INSERT INTO breaks (session_id, user_id, start_time, reason) 
                    VALUES (?, ?, ?, ?)
                ''', (session_id, user_id, now, reason))
                    
                await db.commit()
                return session_dict

    @staticmethod
    async def resume_work_session(user_id: int) -> Optional[Dict[str, Any]]:
        """Возобновить работу после перерыва."""
        now = datetime.datetime.now()
        
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Находим приостановленную сессию
            async with db.execute(
                'SELECT * FROM sessions WHERE user_id = ? AND status = ?', 
                (user_id, SESSION_STATUS["PAUSED"])
            ) as cursor:
                session = await cursor.fetchone()
                if not session:
                    return None
                    
                session_dict = dict(session)
                session_id = session_dict["id"]
                
                # Обновляем статус сессии
                await db.execute(
                    'UPDATE sessions SET status = ? WHERE id = ?', 
                    (SESSION_STATUS["ACTIVE"], session_id)
                )
                
                # Завершаем последний перерыв
                await db.execute('''
                    UPDATE breaks 
                    SET end_time = ?, duration = (strftime('%s', ?) - strftime('%s', start_time))
                    WHERE session_id = ? AND end_time IS NULL
                ''', (now, now, session_id))
                    
                await db.commit()
                return session_dict
                
    @staticmethod
    async def get_session_breaks(session_id: int) -> List[Dict[str, Any]]:
        """Получение списка всех перерывов для указанной сессии."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            breaks = []
            async with db.execute(
                'SELECT * FROM breaks WHERE session_id = ? ORDER BY start_time ASC', 
                (session_id,)
            ) as cursor:
                async for row in cursor:
                    breaks.append(dict(row))
            
            return breaks
            
    @staticmethod
    async def get_user_notes(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение списка заметок пользователя."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            query = '''
                SELECT n.id, n.content, n.timestamp, n.category,
                       s.category as session_category, s.start_time, s.status
                FROM notes n
                JOIN sessions s ON n.session_id = s.id
                WHERE n.user_id = ?
                ORDER BY n.timestamp DESC
                LIMIT ?
            '''
            
            notes = []
            async with db.execute(query, (user_id, limit)) as cursor:
                async for row in cursor:
                    notes.append(dict(row))
            
            return notes
            
    @staticmethod
    async def get_session_notes(session_id: int) -> List[Dict[str, Any]]:
        """Получение списка заметок для указанной сессии."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            notes = []
            async with db.execute(
                'SELECT * FROM notes WHERE session_id = ? ORDER BY timestamp ASC',
                (session_id,)
            ) as cursor:
                async for row in cursor:
                    notes.append(dict(row))

            return notes
            
    @staticmethod
    async def get_sessions_by_timeframe(user_id: int, start_date: datetime.datetime, end_date: datetime.datetime) -> List[Dict[str, Any]]:
        """Получение списка сессий пользователя за указанный период."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            query = '''
                SELECT * FROM sessions 
                WHERE user_id = ? 
                AND start_time >= ? 
                AND start_time <= ? 
                ORDER BY start_time DESC
            '''
            
            sessions = []
            async with db.execute(query, (user_id, start_date, end_date)) as cursor:
                async for row in cursor:
                    sessions.append(dict(row))
            
            return sessions
    
    @staticmethod
    async def get_daily_stats(user_id: int, date: datetime.date) -> Dict[str, Any]:
        """Получение статистики за день."""
        # Начало и конец дня
        start_date = datetime.datetime.combine(date, datetime.time.min)
        end_date = datetime.datetime.combine(date, datetime.time.max)
        
        # Получаем все сессии за день
        sessions = await Database.get_sessions_by_timeframe(user_id, start_date, end_date)
        
        # Инициализируем статистику
        stats = {
            "date": date.strftime("%d.%m.%Y"),
            "total_sessions": len(sessions),
            "total_duration": 0,
            "total_breaks": 0,
            "break_duration": 0,
            "categories": {},
            "completed_sessions": 0,
            "active_sessions": 0
        }
        
        # Обрабатываем каждую сессию
        for session in sessions:
            # Считаем только завершенные сессии для подсчета времени
            if session["status"] == SESSION_STATUS["COMPLETED"]:
                stats["total_duration"] += session["duration"]
                stats["completed_sessions"] += 1
                
                # Учитываем категории
                category = session["category"]
                if category not in stats["categories"]:
                    stats["categories"][category] = {
                        "count": 0,
                        "duration": 0
                    }
                stats["categories"][category]["count"] += 1
                stats["categories"][category]["duration"] += session["duration"]
            elif session["status"] in [SESSION_STATUS["ACTIVE"], SESSION_STATUS["PAUSED"]]:
                stats["active_sessions"] += 1
            
            # Получаем перерывы для сессии
            breaks = await Database.get_session_breaks(session["id"])
            stats["total_breaks"] += len(breaks)
            
            # Считаем продолжительность перерывов
            for break_item in breaks:
                if break_item["end_time"] and break_item["duration"]:
                    stats["break_duration"] += break_item["duration"]
        
        return stats
    
    @staticmethod
    async def get_weekly_stats(user_id: int, date: datetime.date) -> Dict[str, Any]:
        """Получение статистики за неделю."""
        # Определяем начало и конец недели (понедельник-воскресенье)
        weekday = date.weekday()
        start_date = date - datetime.timedelta(days=weekday)
        end_date = start_date + datetime.timedelta(days=6)
        
        # Статистика по дням недели
        daily_stats = []
        current_date = start_date
        
        while current_date <= end_date:
            day_stats = await Database.get_daily_stats(user_id, current_date)
            daily_stats.append(day_stats)
            current_date += datetime.timedelta(days=1)
        
        # Суммарная статистика за неделю
        weekly_summary = {
            "start_date": start_date.strftime("%d.%m.%Y"),
            "end_date": end_date.strftime("%d.%m.%Y"),
            "total_sessions": 0,
            "total_duration": 0,
            "total_breaks": 0,
            "break_duration": 0,
            "categories": {},
            "daily_stats": daily_stats
        }
        
        # Суммируем статистику по дням
        for day in daily_stats:
            weekly_summary["total_sessions"] += day["total_sessions"]
            weekly_summary["total_duration"] += day["total_duration"]
            weekly_summary["total_breaks"] += day["total_breaks"]
            weekly_summary["break_duration"] += day["break_duration"]
            
            # Суммируем по категориям
            for category, data in day["categories"].items():
                if category not in weekly_summary["categories"]:
                    weekly_summary["categories"][category] = {
                        "count": 0,
                        "duration": 0
                    }
                weekly_summary["categories"][category]["count"] += data["count"]
                weekly_summary["categories"][category]["duration"] += data["duration"]
        
        return weekly_summary
    
    @staticmethod
    async def get_monthly_stats(user_id: int, year: int, month: int) -> Dict[str, Any]:
        """Получение статистики за месяц."""
        # Определяем начало и конец месяца
        start_date = datetime.date(year, month, 1)
        
        # Определяем последний день месяца
        if month == 12:
            next_month = datetime.date(year + 1, 1, 1)
        else:
            next_month = datetime.date(year, month + 1, 1)
        end_date = next_month - datetime.timedelta(days=1)
        
        # Получаем все сессии за месяц
        start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
        end_datetime = datetime.datetime.combine(end_date, datetime.time.max)
        sessions = await Database.get_sessions_by_timeframe(user_id, start_datetime, end_datetime)
        
        # Статистика по неделям
        weekly_stats = []
        current_date = start_date
        
        # Получаем статистику для каждой недели месяца
        while current_date <= end_date:
            # Если это понедельник или первый день месяца, начинаем новую неделю
            if current_date.weekday() == 0 or current_date.day == 1:
                week_stats = await Database.get_weekly_stats(user_id, current_date)
                weekly_stats.append(week_stats)
                # Переходим к следующей неделе
                current_date += datetime.timedelta(days=7)
            else:
                # Находим ближайший понедельник
                days_to_monday = 7 - current_date.weekday()
                current_date += datetime.timedelta(days=days_to_monday)
        
        # Суммарная статистика за месяц
        monthly_summary = {
            "year": year,
            "month": month,
            "month_name": datetime.date(year, month, 1).strftime("%B"),
            "total_sessions": len(sessions),
            "total_duration": 0,
            "total_breaks": 0,
            "break_duration": 0,
            "categories": {},
            "weekly_stats": weekly_stats
        }
        
        # Обрабатываем каждую сессию
        for session in sessions:
            # Считаем только завершенные сессии для подсчета времени
            if session["status"] == SESSION_STATUS["COMPLETED"]:
                monthly_summary["total_duration"] += session["duration"]
                
                # Учитываем категории
                category = session["category"]
                if category not in monthly_summary["categories"]:
                    monthly_summary["categories"][category] = {
                        "count": 0,
                        "duration": 0
                    }
                monthly_summary["categories"][category]["count"] += 1
                monthly_summary["categories"][category]["duration"] += session["duration"]
            
            # Получаем перерывы для сессии
            breaks = await Database.get_session_breaks(session["id"])
            monthly_summary["total_breaks"] += len(breaks)
            
            # Считаем продолжительность перерывов
            for break_item in breaks:
                if break_item["end_time"] and break_item["duration"]:
                    monthly_summary["break_duration"] += break_item["duration"]
        
        return monthly_summary

    @staticmethod
    async def export_user_data_to_csv(user_id: int, file_path: str) -> bool:
        """Экспорт всех данных пользователя в CSV файл."""
        import csv

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row

                # Получаем данные пользователя
                async with db.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)) as cursor:
                    user = await cursor.fetchone()

                if not user:
                    return False

                user_dict = dict(user)

                # Получаем все сессии пользователя
                sessions_query = '''
                    SELECT s.*, u.first_name, u.last_name
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.user_id = ?
                    ORDER BY s.start_time DESC
                '''

                async with db.execute(sessions_query, (user_id,)) as cursor:
                    sessions = [dict(row) for row in await cursor.fetchall()]

                # Получаем все заметки пользователя
                notes_query = '''
                    SELECT n.*, s.category as session_category
                    FROM notes n
                    JOIN sessions s ON n.session_id = s.id
                    WHERE n.user_id = ?
                    ORDER BY n.timestamp DESC
                '''

                async with db.execute(notes_query, (user_id,)) as cursor:
                    notes = [dict(row) for row in await cursor.fetchall()]

                # Получаем все перерывы пользователя
                breaks_query = '''
                    SELECT b.*, s.category as session_category
                    FROM breaks b
                    JOIN sessions s ON b.session_id = s.id
                    WHERE b.user_id = ?
                    ORDER BY b.start_time DESC
                '''

                async with db.execute(breaks_query, (user_id,)) as cursor:
                    breaks = [dict(row) for row in await cursor.fetchall()]

            # Создаем CSV файл с тремя листами
            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Лист 1: Информация о пользователе
                writer.writerow(['ЛИСТ 1: ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ'])
                writer.writerow(['ID пользователя', 'Имя', 'Фамилия', 'Username'])
                writer.writerow([
                    user_dict['user_id'],
                    user_dict['first_name'] or '',
                    user_dict['last_name'] or '',
                    user_dict['username'] or ''
                ])
                writer.writerow([])  # Пустая строка

                # Лист 2: Рабочие сессии
                writer.writerow(['ЛИСТ 2: РАБОЧИЕ СЕССИИ'])
                writer.writerow([
                    'ID сессии', 'Дата начала', 'Дата окончания',
                    'Продолжительность (сек)', 'Категория', 'Статус'
                ])

                for session in sessions:
                    writer.writerow([
                        session['id'],
                        session['start_time'],
                        session['end_time'] or '',
                        session['duration'] or 0,
                        session['category'],
                        session['status']
                    ])
                writer.writerow([])  # Пустая строка

                # Лист 3: Заметки
                writer.writerow(['ЛИСТ 3: ЗАМЕТКИ'])
                writer.writerow([
                    'ID заметки', 'Текст заметки', 'Дата создания',
                    'Категория сессии'
                ])

                for note in notes:
                    writer.writerow([
                        note['id'],
                        note['content'],
                        note['timestamp'],
                        note['session_category']
                    ])
                writer.writerow([])  # Пустая строка

                # Лист 4: Перерывы
                writer.writerow(['ЛИСТ 4: ПЕРЕРЫВЫ'])
                writer.writerow([
                    'ID перерыва', 'ID сессии', 'Дата начала', 'Дата окончания',
                    'Продолжительность (сек)', 'Причина'
                ])

                for break_item in breaks:
                    writer.writerow([
                        break_item['id'],
                        break_item['session_id'],
                        break_item['start_time'],
                        break_item['end_time'] or '',
                        break_item['duration'] or 0,
                        break_item['reason']
                    ])

            return True

        except Exception as e:
            print(f"Ошибка при экспорте данных: {e}")
            return False

    @staticmethod
    async def export_sessions_to_csv(user_id: int, start_date: str = None, end_date: str = None, file_path: str = None) -> bool:
        """Экспорт сессий пользователя в CSV за указанный период."""
        import csv

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row

                # Базовый запрос
                query = '''
                    SELECT s.*, u.first_name, u.last_name
                    FROM sessions s
                    JOIN users u ON s.user_id = u.user_id
                    WHERE s.user_id = ?
                '''

                params = [user_id]

                # Добавляем фильтры по датам, если указаны
                if start_date:
                    query += ' AND s.start_time >= ?'
                    params.append(start_date)

                if end_date:
                    query += ' AND s.start_time <= ?'
                    params.append(end_date)

                query += ' ORDER BY s.start_time DESC'

                async with db.execute(query, params) as cursor:
                    sessions = [dict(row) for row in await cursor.fetchall()]

            # Создаем CSV файл
            if not file_path:
                import tempfile
                import os
                temp_dir = tempfile.gettempdir()
                file_path = os.path.join(temp_dir, f'sessions_{user_id}_{datetime.datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')

            with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)

                # Заголовок
                writer.writerow(['ОТЧЕТ ПО РАБОЧИМ СЕССИЯМ'])
                writer.writerow([f'Пользователь ID: {user_id}'])
                if start_date and end_date:
                    writer.writerow([f'Период: с {start_date} по {end_date}'])
                writer.writerow([])  # Пустая строка

                # Заголовки колонок
                writer.writerow([
                    'Дата', 'Время начала', 'Время окончания',
                    'Продолжительность', 'Категория', 'Статус'
                ])

                # Данные сессий
                total_duration = 0
                for session in sessions:
                    start_time = datetime.datetime.fromisoformat(session['start_time'])
                    end_time_str = session['end_time'] if session['end_time'] else 'Не завершена'

                    if session['end_time']:
                        end_time = datetime.datetime.fromisoformat(session['end_time'])
                        duration = session['duration']
                        total_duration += duration
                    else:
                        duration = 'Не завершена'

                    writer.writerow([
                        start_time.strftime('%Y-%m-%d'),
                        start_time.strftime('%H:%M:%S'),
                        end_time_str,
                        duration,
                        session['category'],
                        session['status']
                    ])

                writer.writerow([])  # Пустая строка

                # Итоговая статистика
                writer.writerow(['ИТОГО:'])
                if sessions:
                    hours, remainder = divmod(total_duration, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    writer.writerow([f'Общее время работы: {hours}ч {minutes}м {seconds}с'])
                    writer.writerow([f'Количество сессий: {len(sessions)}'])

            return True

        except Exception as e:
            print(f"Ошибка при экспорте сессий: {e}")
            return False

    @staticmethod
    async def get_reminder_settings(user_id: int) -> Dict[str, Any]:
        """Получение настроек напоминаний пользователя."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                'SELECT * FROM reminder_settings WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                settings = await cursor.fetchone()

            if settings:
                return dict(settings)
            else:
                # Возвращаем настройки по умолчанию
                return {
                    'user_id': user_id,
                    'work_reminder_enabled': 1,
                    'work_reminder_minutes': 60,
                    'break_reminder_enabled': 1,
                    'break_reminder_minutes': 15,
                    'long_break_reminder_enabled': 1,
                    'long_break_reminder_minutes': 120,
                    'daily_goal_enabled': 0,
                    'daily_goal_minutes': 480
                }

    @staticmethod
    async def update_reminder_settings(user_id: int, **settings) -> None:
        """Обновление настроек напоминаний пользователя."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            # Проверяем, существуют ли настройки пользователя
            async with db.execute(
                'SELECT id FROM reminder_settings WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                # Обновляем существующие настройки
                set_parts = []
                values = []
                for key, value in settings.items():
                    set_parts.append(f'{key} = ?')
                    values.append(value)

                values.append(user_id)

                query = f'UPDATE reminder_settings SET {", ".join(set_parts)}, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?'
                await db.execute(query, values)
            else:
                # Создаем новые настройки
                columns = ['user_id'] + list(settings.keys())
                placeholders = ['?'] * len(columns)
                values = [user_id] + list(settings.values())

                query = f'INSERT INTO reminder_settings ({", ".join(columns)}) VALUES ({", ".join(placeholders)})'
                await db.execute(query, values)

            await db.commit()

    @staticmethod
    async def log_sent_reminder(user_id: int, reminder_type: str, session_id: int = None, message_id: int = None) -> None:
        """Запись отправленного напоминания."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                'INSERT INTO sent_reminders (user_id, reminder_type, session_id, message_id) VALUES (?, ?, ?, ?)',
                (user_id, reminder_type, session_id, message_id)
            )
            await db.commit()

    @staticmethod
    async def get_last_reminder_time(user_id: int, reminder_type: str) -> datetime.datetime:
        """Получение времени последнего отправленного напоминания указанного типа."""
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row

            async with db.execute(
                'SELECT sent_at FROM sent_reminders WHERE user_id = ? AND reminder_type = ? ORDER BY sent_at DESC LIMIT 1',
                (user_id, reminder_type)
            ) as cursor:
                reminder = await cursor.fetchone()

            if reminder:
                return datetime.datetime.fromisoformat(reminder['sent_at'])
            else:
                # Если напоминаний не было, возвращаем время далеко в прошлом
                return datetime.datetime.min
