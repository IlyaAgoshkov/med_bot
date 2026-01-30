from aiogram.filters import BaseFilter
from aiogram.types import Message, CallbackQuery
from config import ADMIN_IDS


class IsAdminFilter(BaseFilter):
    """Фильтр для проверки, является ли пользователь администратором"""
    
    async def __call__(self, obj: Message | CallbackQuery) -> bool:
        user_id = obj.from_user.id if hasattr(obj, 'from_user') else None
        is_admin = user_id in ADMIN_IDS if user_id else False
        if not is_admin and user_id:
            print(f"⚠️ Пользователь {user_id} не является администратором. ADMIN_IDS: {ADMIN_IDS}")
        return is_admin
