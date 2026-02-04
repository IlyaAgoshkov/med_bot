import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

from app.database.db import init_db
from app.handlers import survey_router, admin_router
from config import BOT_TOKEN, ADMIN_IDS

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(survey_router.router)
    dp.include_router(admin_router.router)
    
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Устанавливаем команды меню для всех пользователей
    try:
        commands = [
            BotCommand(command="start", description="Начать работу с ботом")
        ]
        await bot.set_my_commands(commands)
        logging.info("✅ Команды меню успешно установлены")
        
        # Проверяем установленные команды
        installed_commands = await bot.get_my_commands()
        logging.info(f"📋 Установленные команды: {[cmd.command for cmd in installed_commands]}")
        
        # Если есть админы, устанавливаем команды для них отдельно
        if ADMIN_IDS:
            from aiogram.types import BotCommandScopeChat
            admin_commands = commands + [
                BotCommand(command="admin", description="Админ-панель")
            ]
            for admin_id in ADMIN_IDS:
                try:
                    await bot.set_my_commands(
                        admin_commands,
                        scope=BotCommandScopeChat(chat_id=admin_id)
                    )
                    logging.info(f"✅ Команды админа установлены для {admin_id}")
                except Exception as e:
                    logging.warning(f"⚠️ Не удалось установить команды для админа {admin_id}: {e}")
    except Exception as e:
        logging.error(f"❌ Ошибка при установке команд меню: {e}", exc_info=True)
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        logging.basicConfig(level=logging.INFO)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⏹️ Бот остановлен")
