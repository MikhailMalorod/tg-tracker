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
            
            # Создаем таблицу заметок
            await db.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    session_id INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    content TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    FOREIGN KEY (session_id) REFERENCES sessions (id)
                )
            ''')
            
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
    async def add_note(user_id: int, content: str, session_id: Optional[int] = None) -> int:
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
                INSERT INTO notes (user_id, session_id, content)
                VALUES (?, ?, ?)
            ''', (user_id, session_id, content))
            
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
                SELECT n.id, n.content, n.timestamp, 
                       s.category, s.start_time, s.status 
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
