import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("8947880080:AAFvJUjGDuDK9CxhZNwWyvnX6BCZfGE9ha4", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "konfeta.db")

# Владелец бота «Конфета»
OWNER_ID = 8875523628

# Первый инспектор
FIRST_INSPECTOR_ID = 1863646015

SUPPORT_LINK = "https://t.me/candy_cm_chat"
