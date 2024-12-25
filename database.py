import sqlite3
import os

DB_PATH = "db/instagram_bot.db"

def initialize_database():
    """
    Инициализация базы данных.
    """
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Создание таблицы для подписок
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            telegram_user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            last_sent_post_id TEXT,
            PRIMARY KEY (telegram_user_id, username)
        )
    """)
    conn.commit()
    conn.close()

def add_subscription(telegram_user_id: int, username: str):
    """
    Добавление подписки для пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        INSERT OR IGNORE INTO subscriptions (telegram_user_id, username, last_sent_post_id)
        VALUES (?, ?, NULL)
    """, (telegram_user_id, username))
    conn.commit()
    conn.close()

def remove_subscription(telegram_user_id: int, username: str):
    """
    Удаление подписки для пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM subscriptions
        WHERE telegram_user_id = ? AND username = ?
    """, (telegram_user_id, username))
    conn.commit()
    conn.close()

def get_subscriptions(telegram_user_id: int = None):
    """
    Получение списка подписок.
    Если указан telegram_user_id, возвращаются подписки только для этого пользователя.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if telegram_user_id:
        cursor.execute("""
            SELECT telegram_user_id, username, last_sent_post_id
            FROM subscriptions
            WHERE telegram_user_id = ?
        """, (telegram_user_id,))
    else:
        cursor.execute("""
            SELECT telegram_user_id, username, last_sent_post_id
            FROM subscriptions
        """)

    subscriptions = cursor.fetchall()
    conn.close()

    return subscriptions

def update_last_sent_post_id(telegram_user_id: int, username: str, last_sent_post_id: str):
    """
    Обновление последнего ID публикации.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE subscriptions
        SET last_sent_post_id = ?
        WHERE telegram_user_id = ? AND username = ?
    """, (last_sent_post_id, telegram_user_id, username))
    conn.commit()
    conn.close()

