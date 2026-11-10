"""Users: one row per person per platform ("telegram:12345").

Everything personal (profile, chat progress, later: settings) hangs off users.id,
kept apart from the shared news tables so more users can be added later.
"""
from . import db


def get_or_create(conn, user_key):
    """'telegram:12345' -> users.id (created on first sight)."""
    platform, account_id = user_key.split(":", 1)
    row = conn.execute("SELECT id FROM users WHERE platform = ? AND account_id = ?",
                       (platform, account_id)).fetchone()
    if row:
        return row[0]
    cur = conn.execute("INSERT INTO users (platform, account_id, created_at) VALUES (?, ?, ?)",
                       (platform, account_id, db.utcnow()))
    conn.commit()
    return cur.lastrowid
