import aiosqlite
import config

DB_PATH = config.DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS inspectors (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS groups_seen (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                chat_type TEXT
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS users_seen (
                user_id INTEGER PRIMARY KEY,
                username TEXT DEFAULT '',
                full_name TEXT DEFAULT '',
                last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS antispam (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                reason TEXT DEFAULT '',
                added_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS antispam_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                actor_id INTEGER,
                chat_id INTEGER,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                actor_id INTEGER,
                chat_id INTEGER NOT NULL,
                reason TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sticker_sets (
                name TEXT PRIMARY KEY,
                category TEXT DEFAULT '18+',
                added_by INTEGER
            )
        """)

        await db.commit()


async def remember_user(user):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users_seen(user_id, username, full_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name,
                last_seen = CURRENT_TIMESTAMP
        """, (user.id, user.username or "", user.full_name or ""))
        await db.commit()


async def remember_group(chat):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO groups_seen(chat_id, title, chat_type)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = excluded.title,
                chat_type = excluded.chat_type
        """, (chat.id, chat.title or str(chat.id), chat.type))
        await db.commit()


async def get_groups():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            SELECT chat_id FROM groups_seen
            WHERE chat_type IN ('group', 'supergroup')
        """)
        return [row[0] for row in await cur.fetchall()]


async def is_inspector(user_id):
    if user_id in (config.OWNER_ID, config.FIRST_INSPECTOR_ID):
        return True

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT 1 FROM inspectors WHERE user_id = ?",
            (user_id,)
        )
        return await cur.fetchone() is not None


async def add_inspector(user_id, actor_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO inspectors(user_id, added_by) VALUES (?, ?)",
            (user_id, actor_id)
        )
        await db.commit()


async def remove_inspector(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM inspectors WHERE user_id = ?",
            (user_id,)
        )
        await db.commit()


async def add_antispam(user_id, actor_id, reason="", chat_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO antispam(user_id, added_by, reason)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                added_by = excluded.added_by,
                reason = excluded.reason
        """, (user_id, actor_id, reason))

        await db.execute("""
            INSERT INTO antispam_events(user_id, action, actor_id, chat_id, reason)
            VALUES (?, 'add', ?, ?, ?)
        """, (user_id, actor_id, chat_id, reason))
        await db.commit()


async def remove_antispam(user_id, actor_id, chat_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM antispam WHERE user_id = ?",
            (user_id,)
        )
        await db.execute("""
            INSERT INTO antispam_events(user_id, action, actor_id, chat_id)
            VALUES (?, 'remove', ?, ?)
        """, (user_id, actor_id, chat_id))
        await db.commit()


async def get_antispam_user(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, added_by, reason, added_at FROM antispam WHERE user_id = ?",
            (user_id,)
        )
        return await cur.fetchone()


async def add_ban(user_id, actor_id, chat_id, reason=""):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bans(user_id, actor_id, chat_id, reason)
            VALUES (?, ?, ?, ?)
        """, (user_id, actor_id, chat_id, reason))
        await db.commit()


async def add_sticker_set(name, actor_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO sticker_sets(name, category, added_by)
            VALUES (?, '18+', ?)
        """, (name, actor_id))
        await db.commit()


async def remove_sticker_set(name):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM sticker_sets WHERE name = ?",
            (name,)
        )
        await db.commit()


async def get_sticker_sets():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT name FROM sticker_sets WHERE category = '18+' ORDER BY name"
        )
        return [row[0] for row in await cur.fetchall()]


async def find_user_by_username(username):
    username = username.lstrip("@").lower()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id FROM users_seen WHERE lower(username) = ?",
            (username,)
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def get_user_stats(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM antispam_events WHERE user_id = ? AND action = 'add'",
            (user_id,)
        )
        added = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM antispam_events WHERE user_id = ? AND action = 'remove'",
            (user_id,)
        )
        removed = (await cur.fetchone())[0]

        cur = await db.execute(
            "SELECT COUNT(*) FROM bans WHERE user_id = ?",
            (user_id,)
        )
        ban_count = (await cur.fetchone())[0]

        cur = await db.execute("""
            SELECT chat_id, reason, created_at FROM bans
            WHERE user_id = ? ORDER BY id DESC LIMIT 10
        """, (user_id,))
        bans = await cur.fetchall()

        cur = await db.execute(
            "SELECT reason FROM antispam WHERE user_id = ?",
            (user_id,)
        )
        active = await cur.fetchone()

        cur = await db.execute(
            "SELECT username, full_name FROM users_seen WHERE user_id = ?",
            (user_id,)
        )
        user = await cur.fetchone()

        return added, removed, ban_count, bans, active, user
