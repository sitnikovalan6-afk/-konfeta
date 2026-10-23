import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("8947880080:AAFvJUjGDuDK9CxhZNwWyvnX6BCZfGE9ha4", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8875523628"))
FIRST_INSPECTOR_ID = int(os.getenv("FIRST_INSPECTOR_ID", "1863646015"))
SUPPORT_CHAT_URL = os.getenv(
    "SUPPORT_CHAT_URL",
    "https://t.me/candy_cm_chat"
)
DB_PATH = os.getenv("DB_PATH", "konfeta.sqlite3")
