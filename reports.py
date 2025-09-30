"""
Модуль для генерации отчетов и статистики по рабочему времени.
"""

import datetime
from typing import Dict, List, Optional, Any, Tuple, Union
import calendar
from collections import defaultdict

from database import Database, SESSION_STATUS

async def get_daily_stats(user_id: int, date: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Получение статистики за день для указанного пользователя."""
    if date is None:
        date = datetime.date.today()
    
    # Определяем начало и конец дня
    start_date = datetime.datetime.combine(date, datetime.time.min)
    end_date = datetime.datetime.combine(date, datetime.time.max)
    
    # Получаем все сессии за указанный день
    sessions = await Database.get_sessions_by_timeframe(
        user_id, start_date, end_date
    )
    
    # Инициализируем словарь с результатами
    result = {
        "date": date.strftime("%d.%m.%Y"),
        "total_work_seconds": 0,
        "total_work_formatted": "00:00:00",
        "sessions_count": 0,
        "categories": defaultdict(int),
        "sessions": []
    }
    
    # Если нет сессий, возвращаем пустую статистику
    if not sessions:
        return result
    
    # Обрабатываем каждую сессию
    total_seconds = 0
    for session in sessions:
        duration = session.get("duration", 0)
        total_seconds += duration
        category = session.get("category", "Без категории")
        result["categories"][category] += duration
        
        # Добавляем информацию о сессии
        session_info = {
            "id": session.get("id"),
            "start_time": session.get("start_time"),
            "end_time": session.get("end_time"),
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "category": category,
            "status": session.get("status")
        }
        result["sessions"].append(session_info)
    
    # Обновляем итоговую статистику
    result["total_work_seconds"] = total_seconds
    result["total_work_formatted"] = format_duration(total_seconds)
    result["sessions_count"] = len(sessions)
    
    # Преобразуем категории в более удобный формат
    categories_list = []
    for category, duration in result["categories"].items():
        categories_list.append({
            "name": category,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "percentage": (duration / total_seconds * 100) if total_seconds > 0 else 0
        })
    result["categories"] = sorted(categories_list, key=lambda x: x["duration"], reverse=True)
    
    return result

async def get_weekly_stats(user_id: int, week_start: Optional[datetime.date] = None) -> Dict[str, Any]:
    """Получение статистики за неделю для указанного пользователя."""
    if week_start is None:
        # Получаем понедельник текущей недели
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
    
    # Определяем даты начала и конца недели
    week_end = week_start + datetime.timedelta(days=6)
    
    # Статистика по дням недели
    days_stats = []
    total_week_seconds = 0
    categories_total = defaultdict(int)
    
    # Для каждого дня недели получаем статистику
    current_date = week_start
    while current_date <= week_end:
        daily_stats = await get_daily_stats(user_id, current_date)
        days_stats.append(daily_stats)
        
        # Суммируем общее время
        total_week_seconds += daily_stats["total_work_seconds"]
        
        # Суммируем время по категориям
        for category in daily_stats["categories"]:
            categories_total[category["name"]] += category["duration"]
        
        # Переходим к следующему дню
        current_date += datetime.timedelta(days=1)
    
    # Преобразуем категории в список
    categories_list = []
    for category, duration in categories_total.items():
        categories_list.append({
            "name": category,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "percentage": (duration / total_week_seconds * 100) if total_week_seconds > 0 else 0
        })
    
    # Возвращаем статистику за неделю
    return {
        "week_start": week_start.strftime("%d.%m.%Y"),
        "week_end": week_end.strftime("%d.%m.%Y"),
        "total_work_seconds": total_week_seconds,
        "total_work_formatted": format_duration(total_week_seconds),
        "average_daily_seconds": total_week_seconds / 7,
        "average_daily_formatted": format_duration(int(total_week_seconds / 7)),
        "days": days_stats,
        "categories": sorted(categories_list, key=lambda x: x["duration"], reverse=True)
    }

async def get_monthly_stats(user_id: int, year: int, month: int) -> Dict[str, Any]:
    """Получение статистики за месяц для указанного пользователя."""
    # Определяем первый и последний день месяца
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(
        year, month, calendar.monthrange(year, month)[1]
    )
    
    # Статистика по дням месяца
    days_stats = []
    total_month_seconds = 0
    categories_total = defaultdict(int)
    
    # Для каждого дня месяца получаем статистику
    current_date = first_day
    while current_date <= last_day:
        daily_stats = await get_daily_stats(user_id, current_date)
        days_stats.append(daily_stats)
        
        # Суммируем общее время
        total_month_seconds += daily_stats["total_work_seconds"]
        
        # Суммируем время по категориям
        for category in daily_stats["categories"]:
            categories_total[category["name"]] += category["duration"]
        
        # Переходим к следующему дню
        current_date += datetime.timedelta(days=1)
    
    # Преобразуем категории в список
    categories_list = []
    for category, duration in categories_total.items():
        categories_list.append({
            "name": category,
            "duration": duration,
            "duration_formatted": format_duration(duration),
            "percentage": (duration / total_month_seconds * 100) if total_month_seconds > 0 else 0
        })
    
    # Возвращаем статистику за месяц
    return {
        "year": year,
        "month": month,
        "month_name": calendar.month_name[month],
        "total_work_seconds": total_month_seconds,
        "total_work_formatted": format_duration(total_month_seconds),
        "average_daily_seconds": total_month_seconds / len(days_stats) if days_stats else 0,
        "average_daily_formatted": format_duration(int(total_month_seconds / len(days_stats))) if days_stats else "00:00:00",
        "days": days_stats,
        "categories": sorted(categories_list, key=lambda x: x["duration"], reverse=True),
        "working_days": len([day for day in days_stats if day["total_work_seconds"] > 0])
    }

def format_duration(seconds: int) -> str:
    """Форматирование продолжительности из секунд в читаемый формат."""
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
