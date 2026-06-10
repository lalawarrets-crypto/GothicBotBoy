"""
Base de datos SQLite para el sistema anti-catfish.
"""
import os
import sqlite3
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "catfish.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            username TEXT,
            join_date TEXT,
            account_created TEXT,
            score INTEGER DEFAULT 0,
            verified INTEGER DEFAULT 0,
            last_updated TEXT
        );
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            message_id TEXT,
            channel_id TEXT,
            url TEXT,
            phash TEXT,
            has_exif INTEGER DEFAULT 0,
            exif_camera TEXT,
            exif_software TEXT,
            ai_score REAL DEFAULT 0,
            ai_type TEXT,
            duplicate_of TEXT,
            timestamp TEXT,
            FOREIGN KEY (user_id) REFERENCES users(discord_id)
        );
        CREATE TABLE IF NOT EXISTS name_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            old_name TEXT,
            new_name TEXT,
            timestamp TEXT
        );
        CREATE TABLE IF NOT EXISTS mod_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            mod_id TEXT,
            action TEXT,
            reason TEXT,
            timestamp TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_images_phash ON images(phash);
        CREATE INDEX IF NOT EXISTS idx_images_user ON images(user_id);
    """)
    conn.commit()
    conn.close()
    print("[DB] Inicializada")


def upsert_user(discord_id, username, join_date=None, account_created=None):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO users (discord_id, username, join_date, account_created, last_updated)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(discord_id) DO UPDATE SET
            username=excluded.username, last_updated=?
    """, (str(discord_id), username, join_date, account_created, now, now))
    conn.commit()
    conn.close()


def get_user(discord_id):
    conn = _conn()
    row = conn.execute("SELECT * FROM users WHERE discord_id=?", (str(discord_id),)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_score(discord_id, score):
    conn = _conn()
    conn.execute("UPDATE users SET score=?, last_updated=? WHERE discord_id=?",
                 (score, datetime.now(timezone.utc).isoformat(), str(discord_id)))
    conn.commit()
    conn.close()


def add_image(user_id, message_id, channel_id, url, phash, has_exif, exif_camera, exif_software, ai_score, ai_type, duplicate_of=None):
    conn = _conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""
        INSERT INTO images (user_id, message_id, channel_id, url, phash, has_exif,
            exif_camera, exif_software, ai_score, ai_type, duplicate_of, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (str(user_id), str(message_id), str(channel_id), url, phash,
          1 if has_exif else 0, exif_camera, exif_software, ai_score, ai_type, duplicate_of, now))
    conn.commit()
    conn.close()


def find_duplicate_hash(phash, exclude_user=None, threshold=5):
    """Busca imágenes con hash similar. threshold = distancia máxima."""
    conn = _conn()
    rows = conn.execute("SELECT * FROM images WHERE phash IS NOT NULL").fetchall()
    conn.close()
    
    if not phash:
        return None
    
    matches = []
    for row in rows:
        row_hash = row["phash"]
        if not row_hash:
            continue
        if exclude_user and row["user_id"] == str(exclude_user):
            continue
        # Calcular distancia hamming
        dist = sum(c1 != c2 for c1, c2 in zip(phash, row_hash))
        if dist <= threshold:
            matches.append(dict(row))
    
    return matches[0] if matches else None


def get_user_images(discord_id, limit=20):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM images WHERE user_id=? ORDER BY timestamp DESC LIMIT ?",
        (str(discord_id), limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_name_changes(discord_id, days=7):
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM name_changes WHERE user_id=? ORDER BY timestamp DESC LIMIT 20",
        (str(discord_id),)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_name_change(user_id, old_name, new_name):
    conn = _conn()
    conn.execute("INSERT INTO name_changes (user_id, old_name, new_name, timestamp) VALUES (?, ?, ?, ?)",
                 (str(user_id), old_name, new_name, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def add_mod_action(user_id, mod_id, action, reason=""):
    conn = _conn()
    conn.execute("INSERT INTO mod_actions (user_id, mod_id, action, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
                 (str(user_id), str(mod_id), action, reason, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    conn.close()


def get_stats():
    conn = _conn()
    total_images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    flagged = conn.execute("SELECT COUNT(*) FROM users WHERE score > 50").fetchone()[0]
    ai_detected = conn.execute("SELECT COUNT(*) FROM images WHERE ai_score > 0.5").fetchone()[0]
    duplicates = conn.execute("SELECT COUNT(*) FROM images WHERE duplicate_of IS NOT NULL").fetchone()[0]
    conn.close()
    return {
        "total_images": total_images,
        "total_users": total_users,
        "flagged": flagged,
        "ai_detected": ai_detected,
        "duplicates": duplicates,
    }
