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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
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


def change_password(username: str, old_password: str, new_password: str) -> dict:
    """Change user password. Returns dict with success status and message."""
    if not verify_user(username, old_password):
        return {"success": False, "message": "Password lama salah"}
    
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
              error_message: str = None, retrieval_count: int = 0):
    """Log a chatbot query and response to the database."""
    try:
        conn = get_connection()
        conn.execute(
            """INSERT INTO query_logs (query, response, status, error_message, retrieval_count)
               VALUES (?, ?, ?, ?, ?)""",
            (query, response, status, error_message, retrieval_count)
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
    conn.close()
    
    stats = {"success": 0, "no_result": 0, "error": 0}
    for row in rows:
        stats[row["status"]] = row["count"]
    
    return {"stats": stats, "total": total}


def clear_query_logs() -> dict:
    """Delete all query logs."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM query_logs")
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"success": True, "deleted_count": deleted}

