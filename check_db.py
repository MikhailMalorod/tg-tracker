import sqlite3
import os
from datetime import datetime

def check_db():
    conn = sqlite3.connect('work_tracker.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=== USERS ===")
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    for user in users:
        print(dict(user))
    
    print("\n=== SESSIONS ===")
    cursor.execute("SELECT * FROM sessions")
    sessions = cursor.fetchall()
    for session in sessions:
        session_dict = dict(session)
        print(session_dict)
    
    print("\n=== BREAKS ===")
    try:
        cursor.execute("SELECT * FROM breaks")
        breaks = cursor.fetchall()
        for break_item in breaks:
            print(dict(break_item))
    except sqlite3.OperationalError:
        print("Таблица breaks еще не создана")
    
    conn.close()

def fix_sessions():
    conn = sqlite3.connect('work_tracker.db')
    cursor = conn.cursor()
    
    # Устанавливаем все активные сессии в завершенные
    cursor.execute("""
        UPDATE sessions 
        SET status = 'completed', 
            end_time = ?, 
            duration = strftime('%s', ?) - strftime('%s', start_time) 
        WHERE status IN ('active', 'paused')
    """, (datetime.now(), datetime.now()))
    
    print(f"Исправлено сессий: {cursor.rowcount}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    print("Текущее состояние базы данных:")
    check_db()
    
    choice = input("\nХотите исправить незавершенные сессии? (y/n): ")
    if choice.lower() == 'y':
        fix_sessions()
        print("\nСостояние базы данных после исправления:")
        check_db()
