import aiosqlite
import logging
import os

logger = logging.getLogger(__name__)

# Путь к базе данных (в Docker используем /app/data, локально - текущая директория)
DB_DIR = os.getenv("DB_DIR", ".")
# Создаем директорию, если её нет
os.makedirs(DB_DIR, exist_ok=True)
DB_NAME = os.path.join(DB_DIR, "med_bot.db")

async def init_db():
    """Инициализация базы данных"""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                preferred_gift TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Добавляем колонку preferred_gift, если её нет (для существующих БД)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN preferred_gift TEXT")
        except aiosqlite.OperationalError:
            pass  # Колонка уже существует
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                consent INTEGER,
                age INTEGER,
                gender TEXT,
                height INTEGER,
                weight REAL,
                bmi REAL,
                education TEXT,
                financial_stability TEXT,
                smoking INTEGER,
                alcohol_per_week INTEGER,
                salt_per_day REAL,
                other_habits INTEGER,
                screen_time INTEGER,
                physical_activity INTEGER,
                night_shifts INTEGER,
                night_shifts_rate TEXT,
                chronic_diseases TEXT,
                medications INTEGER,
                family_history INTEGER,
                stress_level INTEGER,
                sleep_quality INTEGER,
                phq2_score INTEGER,
                phq9_score INTEGER,
                bp1_systolic INTEGER,
                bp1_diastolic INTEGER,
                bp1_time TEXT,
                bp2_systolic INTEGER,
                bp2_diastolic INTEGER,
                bp2_time TEXT,
                bp3_systolic INTEGER,
                bp3_diastolic INTEGER,
                bp3_time TEXT,
                referral_source TEXT,
                risk_level TEXT,
                risk_score INTEGER,
                completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                gift_claimed INTEGER DEFAULT 0,
                gift_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id)
            )
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON surveys(user_id)
        """)
        
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_referral_code ON users(referral_code)
        """)
        
        await db.commit()
        logger.info("База данных инициализирована")

def get_db_path():
    """Получить путь к базе данных"""
    return DB_NAME
