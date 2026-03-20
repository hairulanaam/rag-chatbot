"""
Database module for dashboard authentication and query logging.
Uses Turso (libSQL) cloud database to store admin credentials with hashing and chatbot query logs.
"""
import libsql_client
import hashlib
import secrets
import os
from src.timezone_utils import now_wib_str, date_today_wib
from src.config import TURSO_DATABASE_URL, TURSO_AUTH_TOKEN

# Create a persistent sync client
_client = None


def _get_client():
    """Get or create the libsql sync client."""
    global _client
    if _client is None:
        # Convert libsql:// to https:// for HTTP transport
        url = TURSO_DATABASE_URL
        if url.startswith("libsql://"):
            url = url.replace("libsql://", "https://", 1)
        _client = libsql_client.create_client_sync(
            url=url,
            auth_token=TURSO_AUTH_TOKEN
        )
    return _client


def _execute(sql: str, args=None):
    """Execute a SQL statement and return the ResultSet."""
    client = _get_client()
    if args:
        return client.execute(sql, args)
    return client.execute(sql)


def _rows_to_dicts(result_set) -> list:
    """Convert ResultSet rows to list of dicts using column names."""
    if not result_set.rows or not result_set.columns:
        return []
    return [dict(zip(result_set.columns, row)) for row in result_set.rows]


def _migrate_timestamps_to_wib():
    """Migrasi one-time: konversi timestamp UTC ke WIB (+7 jam) untuk data yang sudah ada."""
    MIGRATION_NAME = "timestamps_utc_to_wib"
    
    # Cek apakah migrasi sudah pernah dijalankan
    try:
        rs = _execute(
            "SELECT COUNT(*) FROM _migrations WHERE name = ?",
            [MIGRATION_NAME]
        )
        if rs.rows[0][0] > 0:
            return  # Sudah dimigrasi
    except Exception:
        return  # Tabel belum ada, skip
    
    print("🔄 Migrasi timestamp UTC → WIB (UTC+7)...")
    
    try:
        # Migrasi tabel users
        _execute("""
            UPDATE users 
            SET created_at = DATETIME(created_at, '+7 hours'),
                updated_at = DATETIME(updated_at, '+7 hours')
            WHERE created_at IS NOT NULL
        """)
        
        # Migrasi tabel query_logs
        _execute("""
            UPDATE query_logs 
            SET created_at = DATETIME(created_at, '+7 hours')
            WHERE created_at IS NOT NULL
        """)
        
        # Migrasi tabel documents
        _execute("""
            UPDATE documents 
            SET created_at = DATETIME(created_at, '+7 hours'),
                updated_at = DATETIME(updated_at, '+7 hours')
            WHERE created_at IS NOT NULL
        """)
        
        # Tandai migrasi sudah selesai
        _execute(
            "INSERT INTO _migrations (name, applied_at) VALUES (?, ?)",
            [MIGRATION_NAME, now_wib_str()]
        )
        
        print("✅ Migrasi timestamp selesai — semua data dikonversi ke WIB")
    except Exception as e:
        print(f"⚠️ Migrasi timestamp gagal: {e}")


def init_db():
    """Initialize database tables and create default admin if none exists."""

    # Buat tabel metadata migrasi (jika belum ada)
    _execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    
    _execute("""
        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query TEXT NOT NULL,
            response TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            retrieval_count INTEGER DEFAULT 0,
            top_source TEXT,
            response_time REAL,
            resolved INTEGER DEFAULT 0,
            created_at TEXT
        )
    """)

    _execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT,
            updated_at TEXT
        )
    """)

    # Safe migration: add columns if they don't exist yet
    for col_sql in [
        "ALTER TABLE query_logs ADD COLUMN top_source TEXT",
        "ALTER TABLE query_logs ADD COLUMN response_time REAL",
        "ALTER TABLE query_logs ADD COLUMN resolved INTEGER DEFAULT 0",
    ]:
        try:
            _execute(col_sql)
        except Exception:
            pass  # Column already exists, ignore
    
    # Migrasi timestamp lama (UTC) ke WIB
    _migrate_timestamps_to_wib()

    # Create default admin if no users exist
    rs = _execute("SELECT COUNT(*) FROM users")
    count = rs.rows[0][0]
    
    if count == 0:
        create_user("admin", "admin123")
        print("📝 Default admin account created (username: admin, password: admin123)")
        print("⚠️  Please change the default password after first login!")


def _hash_password(password: str, salt: str = None) -> tuple:
    """Hash password with salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    password_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
    return password_hash, salt


def create_user(username: str, password: str) -> bool:
    """Create a new user account."""
    try:
        password_hash, salt = _hash_password(password)
        wib_now = now_wib_str()
        _execute(
            "INSERT INTO users (username, password_hash, salt, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            [username, password_hash, salt, wib_now, wib_now]
        )
        return True
    except Exception as e:
        if "UNIQUE constraint failed" in str(e) or "SQLITE_CONSTRAINT" in str(e):
            return False
        raise


def verify_user(username: str, password: str) -> bool:
    """Verify user credentials."""
    rs = _execute(
        "SELECT password_hash, salt FROM users WHERE username = ?",
        [username]
    )
    
    if not rs.rows:
        return False
    
    row = rs.rows[0]
    stored_hash = row[0]
    stored_salt = row[1]
    
    password_hash, _ = _hash_password(password, stored_salt)
    return password_hash == stored_hash


def change_password(username: str, new_password: str) -> dict:
    """Change user password. Returns dict with success status and message."""
    if len(new_password) < 6:
        return {"success": False, "message": "Password baru minimal 6 karakter"}
    
    password_hash, salt = _hash_password(new_password)
    _execute(
        "UPDATE users SET password_hash = ?, salt = ?, updated_at = ? WHERE username = ?",
        [password_hash, salt, now_wib_str(), username]
    )
    
    return {"success": True, "message": "Password berhasil diubah"}


# ============================================================
# Query Logging
# ============================================================

def log_query(query: str, response: str = None, status: str = "success",
              error_message: str = None, retrieval_count: int = 0,
              top_source: str = None, response_time: float = None):
    """Log a chatbot query and response to the database."""
    try:
        _execute(
            """INSERT INTO query_logs (query, response, status, error_message, retrieval_count, top_source, response_time, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [query, response, status, error_message, retrieval_count, top_source, response_time, now_wib_str()]
        )
    except Exception as e:
        print(f"⚠️ Failed to log query: {e}")


def get_query_logs(limit: int = 50, offset: int = 0) -> dict:
    """Get query logs with pagination."""
    # Get total count
    rs_count = _execute("SELECT COUNT(*) FROM query_logs")
    total = rs_count.rows[0][0]
    
    # Get logs (newest first)
    rs = _execute(
        "SELECT * FROM query_logs ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [limit, offset]
    )
    
    logs = _rows_to_dicts(rs)
    # Ensure 'resolved' key exists with default value
    for log in logs:
        if "resolved" not in log:
            log["resolved"] = 0
    
    return {"logs": logs, "total": total, "limit": limit, "offset": offset}


def get_query_stats() -> dict:
    """Get query statistics for chart display."""
    rs = _execute("""
        SELECT status, COUNT(*) as count
        FROM query_logs
        GROUP BY status
    """)
    
    rs_total = _execute("SELECT COUNT(*) FROM query_logs")
    total = rs_total.rows[0][0]
    
    stats = {"success": 0, "no_result": 0, "error": 0}
    for row in rs.rows:
        stats[row[0]] = row[1]

    # Average response time (all queries)
    rs_avg = _execute("""
        SELECT ROUND(AVG(response_time), 2) as avg_rt
        FROM query_logs
        WHERE response_time IS NOT NULL
    """)
    avg_row = rs_avg.rows[0] if rs_avg.rows else None
    avg_response_time = avg_row[0] if avg_row and avg_row[0] is not None else None

    return {"stats": stats, "total": total, "avg_response_time": avg_response_time}


def resolve_query_log(log_id: int) -> dict:
    """Mark a query log as resolved (knowledge has been added)."""
    rs = _execute("UPDATE query_logs SET resolved = 1 WHERE id = ?", [log_id])
    updated = rs.rows_affected
    if updated == 0:
        return {"success": False, "message": "Log tidak ditemukan"}
    return {"success": True, "message": "Log ditandai sebagai resolved", "log_id": log_id}


def clear_query_logs() -> dict:
    """Delete all query logs."""
    rs = _execute("DELETE FROM query_logs")
    deleted = rs.rows_affected
    return {"success": True, "deleted_count": deleted}


def get_daily_stats(days: int = 7) -> dict:
    """Get query count per day for the last N days (WIB)."""
    from datetime import timedelta
    today_wib = date_today_wib()
    start_date = (today_wib - timedelta(days=days - 1)).isoformat()
    
    rs = _execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM query_logs
        WHERE DATE(created_at) >= ?
        GROUP BY DATE(created_at)
        ORDER BY day ASC
    """, [start_date])

    # Build a complete 7-day series (fill missing days with 0)
    result = {}
    for i in range(days):
        d = (today_wib - timedelta(days=days - 1 - i)).isoformat()
        result[d] = 0
    for row in rs.rows:
        day_key = row[0]
        if day_key in result:
            result[day_key] = row[1]

    return {
        "days": list(result.keys()),
        "counts": list(result.values()),
        "total": sum(result.values()),
    }


def get_topic_stats() -> dict:
    """Get query frequency grouped by top_source document."""
    rs = _execute("""
        SELECT top_source, COUNT(*) as count
        FROM query_logs
        WHERE status = 'success' AND top_source IS NOT NULL AND top_source != ''
        GROUP BY top_source
        ORDER BY count DESC
        LIMIT 8
    """)
    return {
        "topics": [{"source": row[0], "count": row[1]} for row in rs.rows]
    }


# ============================================================
# Document Storage (Turso as single source of truth)
# ============================================================

def save_document(filename: str, content: str):
    """Save or update a document in Turso."""
    try:
        wib_now = now_wib_str()
        rs = _execute(
            "UPDATE documents SET content = ?, updated_at = ? WHERE filename = ?",
            [content, wib_now, filename]
        )
        if rs.rows_affected == 0:
            _execute(
                "INSERT INTO documents (filename, content, created_at, updated_at) VALUES (?, ?, ?, ?)",
                [filename, content, wib_now, wib_now]
            )
    except Exception as e:
        print(f"⚠️ Failed to save document: {e}")


def delete_document_record(filename: str):
    """Delete a document from Turso."""
    try:
        _execute("DELETE FROM documents WHERE filename = ?", [filename])
    except Exception as e:
        print(f"⚠️ Failed to delete document: {e}")


def list_documents_db() -> list:
    """List all documents stored in Turso.
    Returns list of dicts with filename, size_bytes, updated_at.
    """
    rs = _execute("""
        SELECT filename, LENGTH(content) as size_bytes, updated_at
        FROM documents
        ORDER BY filename ASC
    """)
    docs = []
    for row in rs.rows:
        docs.append({
            "filename": row[0],
            "size_bytes": row[1] or 0,
            "updated_at": row[2] or "",
        })
    return docs


def get_document_db(filename: str) -> dict | None:
    """Get a single document's content and metadata from Turso.
    Returns dict with filename, content, size_bytes, updated_at or None.
    """
    rs = _execute(
        "SELECT filename, content, LENGTH(content) as size_bytes, updated_at FROM documents WHERE filename = ?",
        [filename]
    )
    if not rs.rows:
        return None
    row = rs.rows[0]
    return {
        "filename": row[0],
        "content": row[1],
        "size_bytes": row[2] or 0,
        "updated_at": row[3] or "",
    }


def document_exists(filename: str) -> bool:
    """Check if a document exists in Turso."""
    rs = _execute("SELECT COUNT(*) FROM documents WHERE filename = ?", [filename])
    return rs.rows[0][0] > 0


def get_all_documents_content() -> list:
    """Get all documents with their content from Turso.
    Returns list of dicts with filename and content.
    """
    rs = _execute("SELECT filename, content FROM documents")
    return [{"filename": row[0], "content": row[1]} for row in rs.rows]


def get_document_count() -> int:
    """Get total number of documents in Turso."""
    rs = _execute("SELECT COUNT(*) FROM documents")
    return rs.rows[0][0]


def sync_local_to_cloud(data_dir: str):
    """One-time sync: upload existing local markdown files to Turso.
    Only uploads files that don't already exist in the cloud.
    """
    from pathlib import Path
    data_path = Path(data_dir)
    if not data_path.exists():
        return 0

    synced = 0
    for f in data_path.glob("*.md"):
        if not document_exists(f.name):
            content = f.read_text(encoding="utf-8")
            save_document(f.name, content)
            synced += 1

    if synced > 0:
        print(f"☁️ Synced {synced} local document(s) to cloud database")
    return synced

