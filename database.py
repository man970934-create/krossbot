import sqlite3
import datetime

DB_PATH = "kross_bot.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица users
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, first_name TEXT, username TEXT,
                  last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    # Таблица reading_sessions (базовая структура)
    c.execute('''CREATE TABLE IF NOT EXISTS reading_sessions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  session_id TEXT UNIQUE,
                  start_time TIMESTAMP,
                  end_time TIMESTAMP,
                  duration INTEGER DEFAULT 0)''')
    
    # Добавляем колонку last_heartbeat, если её нет (миграция)
    try:
        c.execute("ALTER TABLE reading_sessions ADD COLUMN last_heartbeat TIMESTAMP")
    except sqlite3.OperationalError:
        # Колонка уже существует
        pass
    
    # Таблица bot_state
    c.execute('''CREATE TABLE IF NOT EXISTS bot_state
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # Индексы (теперь колонка last_heartbeat гарантированно есть)
    c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON reading_sessions(user_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_last_heartbeat ON reading_sessions(last_heartbeat)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_sessions_duration ON reading_sessions(duration)')
    
    conn.commit()
    c.execute("INSERT OR IGNORE INTO bot_state (key, value) VALUES ('bot_active', '1')")
    conn.commit()
    conn.close()

def add_user(user_id, first_name, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO users (user_id, first_name, username, last_activity)
                 VALUES (?, ?, ?, CURRENT_TIMESTAMP)''',
              (user_id, first_name, username))
    conn.commit()
    conn.close()

def start_reading_session(user_id, session_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO reading_sessions (user_id, session_id, start_time, last_heartbeat)
                 VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)''', (user_id, session_id))
    conn.commit()
    conn.close()

def update_reading_session(session_id, duration):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE reading_sessions 
                 SET duration = ?, last_heartbeat = CURRENT_TIMESTAMP
                 WHERE session_id = ?''', (duration, session_id))
    conn.commit()
    conn.close()

def end_reading_session(session_id, duration):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''UPDATE reading_sessions 
                 SET end_time = CURRENT_TIMESTAMP, duration = ?, last_heartbeat = CURRENT_TIMESTAMP
                 WHERE session_id = ?''', (duration, session_id))
    conn.commit()
    conn.close()

def get_bot_state():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT value FROM bot_state WHERE key='bot_active'")
    row = c.fetchone()
    conn.close()
    return row[0] == '1' if row else True

def set_bot_state(active: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE bot_state SET value=? WHERE key='bot_active'", ('1' if active else '0',))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def get_reading_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.datetime.utcnow()
    day_ago = now - datetime.timedelta(days=1)
    week_ago = now - datetime.timedelta(weeks=1)
    month_ago = now - datetime.timedelta(days=30)

    c.execute("SELECT COUNT(DISTINCT user_id) FROM reading_sessions WHERE last_heartbeat > ?", (day_ago,))
    day_active = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT user_id) FROM reading_sessions WHERE last_heartbeat > ?", (week_ago,))
    week_active = c.fetchone()[0] or 0
    c.execute("SELECT COUNT(DISTINCT user_id) FROM reading_sessions WHERE last_heartbeat > ?", (month_ago,))
    month_active = c.fetchone()[0] or 0

    bins = [(5, '>5 мин'), (10, '>10 мин'), (30, '>30 мин'), (60, '>60 мин')]
    stats = {}
    for minutes, label in bins:
        c.execute('''SELECT COUNT(DISTINCT user_id) FROM reading_sessions 
                     WHERE duration >= ?''', (minutes * 60,))
        stats[label] = c.fetchone()[0] or 0

    conn.close()
    return {
        'day': day_active,
        'week': week_active,
        'month': month_active,
        'duration': stats
    }
