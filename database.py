"""
SQLite Database layer for download history, search cache, bookmarks, and user activity logging.
"""

import sqlite3
from datetime import datetime
from config import DB_PATH, logger


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory, WAL mode, and concurrency timeout."""
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    return conn


def init_db():
    """Initialize all database tables."""
    conn = get_connection()
    try:
        with conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS download_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL,
                    title TEXT,
                    file_type TEXT,
                    file_path TEXT,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    search_type TEXT DEFAULT 'web',
                    results_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT,
                    summary TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    username TEXT,
                    first_name TEXT,
                    action_type TEXT,
                    details TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("Database initialized successfully")
    finally:
        conn.close()


def log_download(url: str, title: str = "", file_type: str = "", file_path: str = "", file_size: int = 0):
    """Log a completed download to history."""
    try:
        conn = get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO download_history (url, title, file_type, file_path, file_size) VALUES (?, ?, ?, ?, ?)",
                    (url, title, file_type, file_path, file_size),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to log download: {e}")


def log_search(query: str, search_type: str = "web", results_count: int = 0):
    """Log a search query."""
    try:
        conn = get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO search_history (query, search_type, results_count) VALUES (?, ?, ?)",
                    (query, search_type, results_count),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to log search: {e}")


def log_activity(user_id: int = 0, username: str = "", first_name: str = "", action_type: str = "usage", details: str = ""):
    """Log any user activity/usage for global analytics dashboard."""
    try:
        conn = get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO activity_logs (user_id, username, first_name, action_type, details) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username or "Anonymous", first_name or "User", action_type, details[:500]),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to log activity: {e}")


def get_recent_downloads(limit: int = 10) -> list:
    """Get recent download history."""
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM download_history ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_bookmark(url: str, title: str = "", summary: str = "", tags: str = ""):
    """Save a URL bookmark."""
    try:
        conn = get_connection()
        try:
            with conn:
                conn.execute(
                    "INSERT OR REPLACE INTO bookmarks (url, title, summary, tags) VALUES (?, ?, ?, ?)",
                    (url, title, summary, tags),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Failed to save bookmark: {e}")


def get_analytics_stats() -> dict:
    """Fetch comprehensive usage statistics for dashboard rendering."""
    conn = get_connection()
    
    total_logs = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
    total_downloads = conn.execute("SELECT COUNT(*) FROM download_history").fetchone()[0]
    total_searches = conn.execute("SELECT COUNT(*) FROM search_history").fetchone()[0]
    
    # Action type breakdown
    action_rows = conn.execute(
        "SELECT action_type, COUNT(*) as count FROM activity_logs GROUP BY action_type ORDER BY count DESC"
    ).fetchall()
    action_breakdown = {r['action_type']: r['count'] for r in action_rows}

    # Top active users
    user_rows = conn.execute(
        "SELECT first_name, username, COUNT(*) as count FROM activity_logs GROUP BY user_id ORDER BY count DESC LIMIT 5"
    ).fetchall()
    top_users = [dict(r) for r in user_rows]

    # Recent 50 activities
    recent_logs = conn.execute(
        "SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 50"
    ).fetchall()

    conn.close()
    return {
        "total_logs": total_logs,
        "total_downloads": total_downloads,
        "total_searches": total_searches,
        "action_breakdown": action_breakdown,
        "top_users": top_users,
        "recent_logs": [dict(r) for r in recent_logs]
    }

