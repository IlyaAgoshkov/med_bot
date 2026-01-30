import os
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Токен бота (обязательно)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в переменных окружения. Создайте файл .env и укажите BOT_TOKEN")

# ID администраторов (опционально, через запятую)
ADMIN_IDS_STR = os.getenv("ADMIN_IDS", "").strip()
if ADMIN_IDS_STR:
    try:
        ADMIN_IDS = [int(admin_id.strip()) for admin_id in ADMIN_IDS_STR.split(",") if admin_id.strip()]
        print(f"✅ Загружены ID администраторов: {ADMIN_IDS}")
    except ValueError:
        ADMIN_IDS = []
        print("⚠️ Предупреждение: ADMIN_IDS содержит неверные значения. Используется пустой список.")
else:
    ADMIN_IDS = []
    print("⚠️ ADMIN_IDS не указан в .env файле")