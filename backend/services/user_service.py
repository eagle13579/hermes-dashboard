"""User Service — SSO用户体系 + SQLite持久化"""
from __future__ import annotations
import json, os, hashlib, sqlite3, logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "users.db"

USER_ROLES = ("admin", "user", "viewer")

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            last_login TEXT
        )
    """)
    conn.commit()
    # Seed admin if not exists
    cur = conn.execute("SELECT id FROM users WHERE username = ?", ("admin",))
    if not cur.fetchone():
        pwd_hash = _hash_password("admin123")
        conn.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                     ("admin", pwd_hash, "admin", datetime.utcnow().isoformat()))
        conn.commit()
        logger.info("Seeded admin user (admin/admin123)")
    conn.close()

def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _verify_password(password: str, hash_val: str) -> bool:
    return _hash_password(password) == hash_val

def register_user(username: str, password: str, email: str = "", role: str = "user") -> Optional[dict]:
    if role not in USER_ROLES:
        raise ValueError(f"Invalid role: {role}. Must be one of {USER_ROLES}")
    conn = _get_conn()
    try:
        pwd_hash = _hash_password(password)
        now = datetime.utcnow().isoformat()
        conn.execute("INSERT INTO users (username, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                     (username, email, pwd_hash, role, now))
        conn.commit()
        cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
        return dict(cur.fetchone())
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def authenticate_user(username: str, password: str) -> Optional[dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
    row = cur.fetchone()
    conn.close()
    if row and _verify_password(password, row["password_hash"]):
        user = dict(row)
        user.pop("password_hash", None)
        return user
    return None

def get_user_by_id(user_id: int) -> Optional[dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def get_user_by_username(username: str) -> Optional[dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

def list_users() -> list[dict]:
    conn = _get_conn()
    cur = conn.execute("SELECT id, username, email, role, is_active, created_at, last_login FROM users ORDER BY id")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

def update_role(user_id: int, new_role: str) -> bool:
    if new_role not in USER_ROLES:
        raise ValueError(f"Invalid role: {new_role}")
    conn = _get_conn()
    cur = conn.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def deactivate_user(user_id: int) -> bool:
    conn = _get_conn()
    cur = conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected > 0

def update_last_login(user_id: int):
    conn = _get_conn()
    conn.execute("UPDATE users SET last_login = ? WHERE id = ?", (datetime.utcnow().isoformat(), user_id))
    conn.commit()
    conn.close()
