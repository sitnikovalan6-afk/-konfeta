import aiosqlite
from config import DATABASE_PATH, OWNER_ID, FIRST_INSPECTOR_ID

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS inspectors (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS groups_seen (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            chat_type TEXT,
            seen_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS users_seen (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS antispam (
            user_id INTEGER PRIMARY KEY,
            reason TEXT NOT NULL DEFAULT 'Причина не указана',
            added_by INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS antispam_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL CHECK(action IN ('add','remove')),
            actor_id INTEGER NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            chat_title TEXT,
            actor_id INTEGER NOT NULL,
            reason TEXT NOT NULL DEFAULT 'Причина не указана',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sticker_sets (
            name TEXT PRIMARY KEY,
            added_by INTEGER NOT NULL,
            added_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        await db.execute(
            "INSERT OR IGNORE INTO inspectors(user_id, added_by) VALUES(?, ?)",
            (FIRST_INSPECTOR_ID, OWNER_ID)
        )
        await db.commit()

async def is_inspector(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT 1 FROM inspectors WHERE user_id=?", (user_id,))
        return await cur.fetchone() is not None

async def add_inspector(user_id: int, actor_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO inspectors(user_id, added_by) VALUES(?, ?)",
            (user_id, actor_id)
        )
        await db.commit()

async def remove_inspector(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM inspectors WHERE user_id=?", (user_id,))
        await db.commit()

async def save_user(user_id: int, username, full_name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO users_seen(user_id, username, full_name, last_seen_at)
            VALUES(?, ?, ?, datetime('now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                full_name=excluded.full_name,
                last_seen_at=datetime('now')
        """, (user_id, username.lower() if username else None, full_name))
        await db.commit()

async def find_user_by_username(username: str):
    username = username.lstrip("@").lower()
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, username, full_name FROM users_seen WHERE username=?",
            (username,)
        )
        return await cur.fetchone()

async def get_user(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, username, full_name FROM users_seen WHERE user_id=?",
            (user_id,)
        )
        return await cur.fetchone()

async def save_group(chat_id: int, title: str, chat_type: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO groups_seen(chat_id, title, chat_type, seen_at)
            VALUES(?, ?, ?, datetime('now'))
            ON CONFLICT(chat_id) DO UPDATE SET
                title=excluded.title, chat_type=excluded.chat_type,
                seen_at=datetime('now')
        """, (chat_id, title, chat_type))
        await db.commit()

async def get_groups():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT chat_id, title FROM groups_seen")
        return await cur.fetchall()

async def add_to_antispam(user_id: int, actor_id: int, reason: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO antispam(user_id, reason, added_by) VALUES(?, ?, ?)",
            (user_id, reason or "Причина не указана", actor_id)
        )
        await db.execute(
            "INSERT INTO antispam_events(user_id, action, actor_id, reason) VALUES(?, 'add', ?, ?)",
            (user_id, actor_id, reason or "Причина не указана")
        )
        await db.commit()

async def remove_from_antispam(user_id: int, actor_id: int, reason: str = ""):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM antispam WHERE user_id=?", (user_id,))
        await db.execute(
            "INSERT INTO antispam_events(user_id, action, actor_id, reason) VALUES(?, 'remove', ?, ?)",
            (user_id, actor_id, reason)
        )
        await db.commit()

async def get_antispam_entry(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute(
            "SELECT reason, added_by, added_at FROM antispam WHERE user_id=?",
            (user_id,)
        )
        return await cur.fetchone()

async def get_antispam_counts(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            SELECT SUM(CASE WHEN action='add' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN action='remove' THEN 1 ELSE 0 END)
            FROM antispam_events WHERE user_id=?
        """, (user_id,))
        row = await cur.fetchone()
        return row[0] or 0, row[1] or 0

async def add_ban(user_id: int, chat_id: int, chat_title: str, actor_id: int, reason: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO bans(user_id, chat_id, chat_title, actor_id, reason)
            VALUES(?, ?, ?, ?, ?)
        """, (user_id, chat_id, chat_title, actor_id, reason or "Причина не указана"))
        await db.commit()

async def get_ban_history(user_id: int, limit: int = 10):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("""
            SELECT chat_title, chat_id, reason, actor_id, created_at
            FROM bans WHERE user_id=? ORDER BY id DESC LIMIT ?
        """, (user_id, limit))
        return await cur.fetchall()

async def get_ban_count(user_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM bans WHERE user_id=?", (user_id,))
        return (await cur.fetchone())[0]

async def add_sticker_set(name: str, actor_id: int):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO sticker_sets(name, added_by) VALUES(?, ?)",
            (name, actor_id)
        )
        await db.commit()

async def remove_sticker_set(name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM sticker_sets WHERE name=?", (name,))
        await db.commit()

async def list_sticker_sets():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT name FROM sticker_sets ORDER BY name")
        return await cur.fetchall()

async def is_banned_sticker_set(name: str):
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cur = await db.execute("SELECT 1 FROM sticker_sets WHERE name=?", (name,))
        return await cur.fetchone() is not None
