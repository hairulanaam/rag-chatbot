"""
Database module for dashboard authentication and query logging.
Uses SQLite to store admin credentials with hashing and chatbot query logs.
"""
import sqlite3
import hashlib
import secrets
import os
from src.config import DATABASE_PATH


def get_connection():
    """Get SQLite database connection."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize database tables and create default admin if none exists."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            response TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            retrieval_count INTEGER DEFAULT 0,
            top_source TEXT,
            response_time REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    # Safe migration: add top_source column if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE query_logs ADD COLUMN top_source TEXT")
        conn.commit()
    except Exception:
        pass  # Column already exists, ignore

    # Safe migration: add response_time column if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE query_logs ADD COLUMN response_time REAL")
        conn.commit()
    except Exception:
        pass  # Column already exists, ignore

    # Safe migration: add resolved column if it doesn't exist yet
    try:
        cursor.execute("ALTER TABLE query_logs ADD COLUMN resolved INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass  # Column already exists, ignore
    
    # Create default admin if no users exist
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    
    if count == 0:
        create_user("admin", "admin123")
        print("📝 Default admin account created (username: admin, password: admin123)")
        print("⚠️  Please change the default password after first login!")
    
    conn.close()


def _hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    password_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return password_hash, salt


def create_user(username: str, password: str) -> bool:
    """Create a new user account."""
    try:
        conn = get_connection()
        password_hash, salt = _hash_password(password)
        
        conn.execute(
            "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
            (username, password_hash, salt)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False


def verify_user(username: str, password: str) -> bool:
    """Verify user credentials."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT password_hash, salt FROM users WHERE username = ?",
        (username,)
    )
    row = cursor.fetchone()
    conn.close()
    
    if row is None:
        return False
    
    password_hash, _ = _hash_password(password, row["salt"])
    return password_hash == row["password_hash"]


def change_password(username: str, new_password: str) -> dict:
    """Change user password. Returns dict with success status and message."""
    if len(new_password) < 6:
        return {"success": False, "message": "Password baru minimal 6 karakter"}
    
    conn = get_connection()
    password_hash, salt = _hash_password(new_password)
    
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ?, updated_at = CURRENT_TIMESTAMP WHERE username = ?",
        (password_hash, salt, username)
    )
    conn.commit()
    conn.close()
    
    return {"success": True, "message": "Password berhasil diubah"}


# ============================================================
# Query Logging
# ============================================================

def log_query(query: str, response: str = None, status: str = "success",
              error_message: str = None, retrieval_count: int = 0,
              top_source: str = None, response_time: float = None):
    """Log a chatbot query and response to the database."""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO query_logs (query, response, status, error_message, retrieval_count, top_source, response_time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (query, response, status, error_message, retrieval_count, top_source, response_time)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Failed to log query: {e}")


def get_query_logs(limit: int = 50, offset: int = 0) -> dict:
    """Get query logs with pagination."""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Get total count
    cursor.execute("SELECT COUNT(*) FROM query_logs")
    total = cursor.fetchone()[0]
    
    # Get logs (newest first)
    cursor.execute(
        "SELECT * FROM query_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )
    rows = cursor.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append({
            "id": row["id"],
            "query": row["query"],
            "response": row["response"],
            "status": row["status"],
            "error_message": row["error_message"],
            "retrieval_count": row["retrieval_count"],
            "top_source": row["top_source"],
            "response_time": row["response_time"],
            "resolved": row["resolved"] if "resolved" in row.keys() else 0,
            "created_at": row["created_at"],
        })
    
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


def get_query_stats() -> dict:
    """Get query statistics for chart display."""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM query_logs
        GROUP BY status
    """)
    rows = cursor.fetchall()
    
    cursor.execute("SELECT COUNT(*) FROM query_logs")
    total = cursor.fetchone()[0]
    
    stats = {"success": 0, "no_result": 0, "error": 0}
    for row in rows:
        stats[row["status"]] = row["count"]

    # Average response time (all queries)
    cursor.execute("""
        SELECT ROUND(AVG(response_time), 2) as avg_rt
        FROM query_logs
        WHERE response_time IS NOT NULL
    """)
    avg_row = cursor.fetchone()
    avg_response_time = avg_row["avg_rt"] if avg_row and avg_row["avg_rt"] is not None else None

    conn.close()
    return {"stats": stats, "total": total, "avg_response_time": avg_response_time}


def resolve_query_log(log_id: int) -> dict:
    """Mark a query log as resolved (knowledge has been added)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE query_logs SET resolved = 1 WHERE id = ?", (log_id,))
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    if updated == 0:
        return {"success": False, "message": "Log tidak ditemukan"}
    return {"success": True, "message": "Log ditandai sebagai resolved", "log_id": log_id}


def clear_query_logs() -> dict:
    """Delete all query logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM query_logs")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "deleted_count": deleted}


def get_daily_stats(days: int = 7) -> dict:
    """Get query count per day for the last N days."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM query_logs
        WHERE created_at >= DATE('now', ? || ' days')
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """, (f"-{days}",))
    rows = cursor.fetchall()
    conn.close()

    # Build a complete 7-day series (fill missing days with 0)
    from datetime import date, timedelta
    result = {}
    for i in range(days):
        d = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        result[d] = 0
    for row in rows:
        if row["day"] in result:
            result[row["day"]] = row["count"]

    return {
        "days": list(result.keys()),
        "counts": list(result.values()),
        "total": sum(result.values()),
    }


def get_topic_stats() -> dict:
    """Get query frequency grouped by top_source document."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT top_source, COUNT(*) as count
        FROM query_logs
        WHERE status = 'success' AND top_source IS NOT NULL AND top_source != ''
        GROUP BY top_source
        ORDER BY count DESC
        LIMIT 8
    """)
    rows = cursor.fetchall()
    conn.close()
    return {
        "topics": [{"source": row["top_source"], "count": row["count"]} for row in rows]
    }
