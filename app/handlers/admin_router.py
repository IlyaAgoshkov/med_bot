from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from app.database.db import get_db_path
from app.filters.admin_filter import IsAdminFilter
from app.keyboards.inline_keyboards import get_admin_keyboard
import aiosqlite

router = Router()


@router.message(Command("admin"), IsAdminFilter())
async def cmd_admin(message: Message):
    """Админ-панель"""
    admin_text = """<b>🔐 Админ-панель</b>

Выберите действие:"""
    
    await message.answer(admin_text, reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_stats", IsAdminFilter())
async def admin_stats(callback: CallbackQuery):
    """Статистика по опросам"""
    async with aiosqlite.connect(get_db_path()) as db:
        # Общая статистика
        async with db.execute("SELECT COUNT(*) FROM surveys") as cursor:
            total_surveys = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            total_users = (await cursor.fetchone())[0]
        
        async with db.execute("SELECT COUNT(*) FROM referrals WHERE gift_claimed = 1") as cursor:
            gifts_claimed = (await cursor.fetchone())[0]
        
        # Пользователи, прошедшие тестирование
        async with db.execute("SELECT COUNT(DISTINCT user_id) FROM surveys") as cursor:
            users_completed = (await cursor.fetchone())[0]
        
        # Пользователи, которые были приглашены
        async with db.execute("SELECT COUNT(DISTINCT referred_id) FROM referrals") as cursor:
            users_referred = (await cursor.fetchone())[0]
        
        # Пользователи, которые пригласили других
        async with db.execute("SELECT COUNT(DISTINCT referrer_id) FROM referrals") as cursor:
            users_referrers = (await cursor.fetchone())[0]
    
    stats_text = f"""<b>📊 Статистика бота</b>

👥 Всего пользователей: {total_users}
✅ Прошли тестирование: {users_completed}
📝 Всего опросов: {total_surveys}
🎁 Подарков выдано: {gifts_claimed}
👥 Были приглашены: {users_referred}
👥 Пригласили других: {users_referrers}"""
    
    await callback.message.edit_text(stats_text, reply_markup=get_admin_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_users", IsAdminFilter())
async def admin_users(callback: CallbackQuery):
    """Список пользователей"""
    async with aiosqlite.connect(get_db_path()) as db:
        # Получаем всех пользователей с информацией о прохождении теста и приглашениях
        async with db.execute("""
            SELECT 
                u.user_id,
                u.full_name,
                u.username,
                CASE WHEN s.user_id IS NOT NULL THEN 1 ELSE 0 END as has_survey,
                CASE WHEN r1.referred_id IS NOT NULL THEN 1 ELSE 0 END as was_referred,
                CASE WHEN r2.referrer_id IS NOT NULL THEN 1 ELSE 0 END as has_referrals,
                r1.referrer_id,
                ref.full_name as referrer_name,
                ref.username as referrer_username
            FROM users u
            LEFT JOIN surveys s ON u.user_id = s.user_id
            LEFT JOIN referrals r1 ON u.user_id = r1.referred_id
            LEFT JOIN users ref ON r1.referrer_id = ref.user_id
            LEFT JOIN referrals r2 ON u.user_id = r2.referrer_id
            GROUP BY u.user_id
            ORDER BY u.created_at DESC
            LIMIT 50
        """) as cursor:
            users = await cursor.fetchall()
    
    if not users:
        await callback.message.edit_text(
            "<b>👥 Пользователи</b>\n\nПользователей пока нет.",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
        return
    
    users_text = "<b>👥 Пользователи</b>\n\n"
    for user in users:
        user_id, full_name, username, has_survey, was_referred, has_referrals, referrer_id, referrer_name, referrer_username = user
        
        full_name = full_name or "Не указано"
        username = f"@{username}" if username else "Не указано"
        
        status_icons = []
        if has_survey:
            status_icons.append("✅ Тест")
        if was_referred:
            status_icons.append("👥 Приглашен")
        if has_referrals:
            status_icons.append("🎁 Пригласил")
        
        status = " ".join(status_icons) if status_icons else "❌ Нет активности"
        
        users_text += f"<b>{full_name}</b>\n"
        users_text += f"Username: {username}\n"
        users_text += f"ID: {user_id}\n"
        users_text += f"Статус: {status}\n"
        
        # Добавляем информацию о реферере, если пользователь был приглашен
        if was_referred and referrer_id:
            referrer_name = referrer_name or "Не указано"
            referrer_username = f"@{referrer_username}" if referrer_username else "Не указано"
            users_text += f"Пригласил: {referrer_name} ({referrer_username}, ID: {referrer_id})\n"
        
        users_text += "\n"
    
    if len(users) == 50:
        users_text += "\n<i>Показаны последние 50 пользователей</i>"
    
    await callback.message.edit_text(users_text, reply_markup=get_admin_keyboard())
    await callback.answer()
