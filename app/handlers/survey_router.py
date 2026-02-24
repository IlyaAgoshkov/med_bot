import re
import asyncio
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter
import os

from app.states.survey_states import SurveyStates
from app.keyboards.inline_keyboards import (
    get_yes_no_keyboard,
    get_gender_keyboard,
    get_education_keyboard,
    get_financial_stability_keyboard,
    get_night_shifts_rate_keyboard,
    get_chronic_diseases_keyboard,
    get_phq_keyboard,
    get_referral_source_keyboard,
    get_gift_keyboard,
    get_main_menu_keyboard,
    get_invite_friend_keyboard,
    get_start_keyboard,
    get_restart_survey_keyboard
)
from config import ADMIN_IDS
from app.database.db import get_db_path
import aiosqlite
import logging
from app.utils.calculations import calculate_bmi, calculate_risk_score, get_risk_level, categorize_bp, get_recommendations
from app.utils.referral import generate_referral_code

logger = logging.getLogger(__name__)
router = Router()

# Хранилище временных данных опроса
survey_data = {}


async def send_gift_to_referrer(bot, user_id: int):
    """Отправить подарок рефереру, если приглашенный пользователь прошел тест"""
    logger.info(f"🔍 Проверка реферера для пользователя {user_id}")
    
    async with aiosqlite.connect(get_db_path()) as db:
        # Проверяем, был ли пользователь приглашен (проверяем и referred_by, и таблицу referrals)
        referrer_id = None
        
        # Сначала проверяем таблицу referrals (это более надежный способ)
        async with db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ?",
            (user_id,)
        ) as cursor:
            referral_row = await cursor.fetchone()
            if referral_row and referral_row[0]:
                referrer_id = referral_row[0]
                logger.info(f"✅ Найден реферер через referrals: {referrer_id}")
        
        # Если не нашли через referrals, проверяем поле referred_by в таблице users
        if not referrer_id:
            async with db.execute(
                "SELECT referred_by FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                user_row = await cursor.fetchone()
                if user_row and user_row[0]:
                    referrer_id = user_row[0]
                    logger.info(f"✅ Найден реферер через referred_by: {referrer_id}")
                elif user_row:
                    logger.info(f"Пользователь {user_id} найден в БД, но referred_by = None")
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден в таблице users")
        
        if not referrer_id:
            logger.info(f"❌ Пользователь {user_id} не был приглашен, подарок не отправляется")
            return  # Пользователь не был приглашен
        
        # Получаем информацию о реферере и его предпочтении подарка
        async with db.execute(
            "SELECT preferred_gift FROM users WHERE user_id = ?",
            (referrer_id,)
        ) as cursor:
            referrer_row = await cursor.fetchone()
            if not referrer_row or not referrer_row[0]:
                logger.info(f"Реферер {referrer_id} не выбрал подарок, файл не отправляется")
                return
            
            preferred_gift = referrer_row[0]
            logger.info(f"Реферер {referrer_id} выбрал подарок: {preferred_gift}")
        
        # Маппинг подарков на файлы
        gift_file_map = {
            "Питание": "Питание.pdf",
            "Физическая активность": "Физическая активность.pdf",
            "Стресс": "Стресс.pdf"
        }
        
        file_name = gift_file_map.get(preferred_gift)
        if not file_name:
            logger.warning(f"Неизвестный подарок: {preferred_gift}")
            return
        
        # Отправляем файл рефереру
        gift_file_path = os.path.join("file", file_name)
        logger.info(f"Попытка отправить файл: {gift_file_path}")
        
        if os.path.exists(gift_file_path):
            try:
                gift_file = FSInputFile(gift_file_path, filename=file_name)
                gift_text = f"🎁 <b>Поздравляем!</b>\n\nКто-то прошел тест по вашей реферальной ссылке!\n\nВаш подарок: <b>{preferred_gift}</b>"
                
                # Пытаемся отправить файл с увеличенным таймаутом и повторными попытками
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await bot.send_document(
                            chat_id=referrer_id,
                            document=gift_file,
                            caption=gift_text,
                            request_timeout=60  # Увеличиваем таймаут до 60 секунд
                        )
                        logger.info(f"✅ Подарок {preferred_gift} успешно отправлен рефереру {referrer_id}")
                        # Отмечаем подарок как выданный в таблице referrals
                        await db.execute(
                            "UPDATE referrals SET gift_claimed = 1, gift_type = ? WHERE referrer_id = ? AND referred_id = ?",
                            (preferred_gift, referrer_id, user_id)
                        )
                        await db.commit()
                        break  # Успешно отправлено, выходим из цикла
                    except Exception as retry_error:
                        if attempt < max_retries - 1:
                            logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась при отправке подарка рефереру {referrer_id}: {retry_error}. Повторная попытка...")
                            await asyncio.sleep(2)  # Ждем 2 секунды перед повторной попыткой
                        else:
                            raise  # Если все попытки исчерпаны, пробрасываем исключение
            except Exception as e:
                logger.error(f"❌ Ошибка при отправке подарка рефереру {referrer_id} после {max_retries} попыток: {e}", exc_info=True)
        else:
            logger.error(f"❌ Файл подарка не найден: {gift_file_path}")


async def notify_admins_about_survey(bot, user_id: int):
    """Уведомить админов о прохождении теста пользователем"""
    if not ADMIN_IDS:
        logger.warning("ADMIN_IDS пуст, уведомления не отправляются")
        return
    
    logger.info(f"Отправка уведомления админам о прохождении теста пользователем {user_id}")
    
    async with aiosqlite.connect(get_db_path()) as db:
        # Получаем информацию о пользователе
        async with db.execute(
            "SELECT full_name, username FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            user_row = await cursor.fetchone()
            if not user_row:
                logger.error(f"Пользователь {user_id} не найден в БД, уведомление не отправляется")
                # Попробуем создать пользователя с минимальной информацией
                try:
                    await db.execute(
                        "INSERT OR IGNORE INTO users (user_id, username, full_name, referral_code) VALUES (?, ?, ?, ?)",
                        (user_id, "Не указано", "Не указано", generate_referral_code(user_id))
                    )
                    await db.commit()
                    logger.info(f"Создан пользователь {user_id} в БД для уведомления")
                    user_full_name = "Не указано"
                    user_username = "Не указано"
                except Exception as e:
                    logger.error(f"Не удалось создать пользователя {user_id}: {e}", exc_info=True)
                    return
            else:
                user_full_name = user_row[0] or "Не указано"
                user_username = user_row[1] or "Не указано"
                logger.info(f"Найден пользователь: {user_full_name} (@{user_username})")
        
        # Проверяем, был ли пользователь приглашен
        async with db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ?",
            (user_id,)
        ) as cursor:
            referral_row = await cursor.fetchone()
            referrer_id = referral_row[0] if referral_row else None
        
        # Формируем уведомление
        notification_text = f"""🔔 <b>Новое уведомление</b>

<b>Пользователь</b>
Имя: {user_full_name}
Username: @{user_username}
ID: {user_id}

прошел опрос"""
        
        # Если был приглашен, получаем информацию о реферере
        if referrer_id:
            async with db.execute(
                "SELECT full_name, username, preferred_gift FROM users WHERE user_id = ?",
                (referrer_id,)
            ) as cursor:
                referrer_row = await cursor.fetchone()
                referrer_full_name = referrer_row[0] if referrer_row else "Не указано"
                referrer_username = referrer_row[1] if referrer_row else "Не указано"
                preferred_gift = referrer_row[2] if referrer_row and referrer_row[2] else "Не указан"
            
            notification_text += f"""

<b>Его пригласил:</b>
Имя: {referrer_full_name}
Username: @{referrer_username}
ID: {referrer_id}

<b>Ему нужно подарить:</b> {preferred_gift}"""
        else:
            notification_text += f"""

<b>Его пригласил:</b> —"""
    
    # Отправляем уведомление всем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification_text)
            logger.info(f"Уведомление успешно отправлено админу {admin_id}")
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}", exc_info=True)



# Начало опроса
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # Очищаем предыдущее состояние, если есть
    await state.clear()
    
    # Регистрация пользователя
    async with aiosqlite.connect(get_db_path()) as db:
        # Проверяем реферальный параметр (может быть ID или код для обратной совместимости)
        referral_param = None
        if len(message.text.split()) > 1:
            referral_param = message.text.split()[1]
        
        # Проверяем существование пользователя
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_exists = await cursor.fetchone()
        
        if not user_exists:
            # Создаем нового пользователя
            ref_code = generate_referral_code(user_id)
            referred_by = None
            
            if referral_param:
                # Проверяем, является ли параметр числом (ID реферера)
                try:
                    referrer_id = int(referral_param)
                    # Проверяем, существует ли пользователь с таким ID
                    async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)) as cursor:
                        referrer = await cursor.fetchone()
                        if referrer:
                            referred_by = referrer_id
                            logger.info(f"Найден реферер по ID: {referrer_id}")
                except ValueError:
                    # Если не число, пытаемся найти по старому коду (для обратной совместимости)
                    async with db.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_param,)) as cursor:
                        referrer = await cursor.fetchone()
                        if referrer:
                            referred_by = referrer[0]
                            logger.info(f"Найден реферер по старому коду: {referral_param}")
            
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, referral_code, referred_by) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, full_name, ref_code, referred_by)
            )
            await db.commit()
            
            # Если есть реферер, создаем запись о реферале
            if referred_by:
                await db.execute(
                    "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                    (referred_by, user_id)
                )
                await db.commit()
        else:
            # Обновляем информацию о пользователе (username и full_name могут измениться)
            # Также проверяем, нужно ли обновить referred_by, если пользователь пришел по реферальной ссылке
            referred_by = None
            if referral_param:
                # Проверяем, является ли параметр числом (ID реферера)
                try:
                    referrer_id = int(referral_param)
                    # Проверяем, существует ли пользователь с таким ID
                    async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (referrer_id,)) as cursor:
                        referrer = await cursor.fetchone()
                        if referrer:
                            referred_by = referrer_id
                            logger.info(f"Найден реферер по ID для существующего пользователя: {referrer_id}")
                except ValueError:
                    # Если не число, пытаемся найти по старому коду (для обратной совместимости)
                    async with db.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_param,)) as cursor:
                        referrer = await cursor.fetchone()
                        if referrer:
                            referred_by = referrer[0]
                            logger.info(f"Найден реферер по старому коду для существующего пользователя: {referral_param}")
            
            # Проверяем, есть ли уже referred_by у пользователя
            async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,)) as cursor:
                existing_referred_by = await cursor.fetchone()
                existing_referred_by = existing_referred_by[0] if existing_referred_by else None
            
            # Обновляем referred_by только если его еще нет, но есть новый реферер
            if not existing_referred_by and referred_by:
                await db.execute(
                    "UPDATE users SET username = ?, full_name = ?, referred_by = ? WHERE user_id = ?",
                    (username, full_name, referred_by, user_id)
                )
                await db.commit()
                
                # Создаем запись о реферале, если её еще нет
                async with db.execute(
                    "SELECT id FROM referrals WHERE referrer_id = ? AND referred_id = ?",
                    (referred_by, user_id)
                ) as cursor:
                    referral_exists = await cursor.fetchone()
                
                if not referral_exists:
                    await db.execute(
                        "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referred_by, user_id)
                    )
                    await db.commit()
                    logger.info(f"Обновлен referred_by для пользователя {user_id}: {referred_by}")
            else:
                # Просто обновляем username и full_name
                await db.execute(
                    "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                    (username, full_name, user_id)
                )
                await db.commit()
    
    welcome_text = """👋 <b>Добро пожаловать!</b>

Вы открыли цифровой чек-ап артериального давления, созданный в рамках научного проекта по раннему выявлению высокого нормального давления (предгипертонии).

Это состояние, при котором давление ещё не требует лечения, но уже повышает риск развития гипертонии в будущем.
По данным исследований, оно встречается у 30–40% взрослых, и большинство людей об этом не знают.

🩺 <b>Во время прохождения Вам предстоит:</b>
• ответить на короткие вопросы о здоровье и образе жизни
• 3 раза измерить артериальное давление и пульс
• получить персональную оценку риска и рекомендации

⏱️ Время прохождения: ~5–7 минут.

Опросник предназначен для лиц 15–45 лет и используется в исследовательских целях.

<b>Важно:</b> результат носит скрининговый характер, не является медицинским диагнозом и не заменяет консультацию врача.

Ваше участие помогает развивать цифровые инструменты профилактики сердечно-сосудистых заболеваний ❤️

Готовы проверить себя? Нажмите «Начать» 👇"""
    
    sent_message = await message.answer(welcome_text, reply_markup=get_start_keyboard())
    await state.update_data(main_message_id=sent_message.message_id)
    await state.set_state(SurveyStates.welcome)


# Чек-лист перед каждым измерением АД
BP_CHECKLIST = """
📋 <b>Перед измерением проверьте:</b>
• Поза: сидя, спина и рука с опорой, манжета по размеру
• Без кофе, курения и нагрузки за 30 минут
• Покой не менее 5 минут перед измерением
• Одна и та же рука при всех трёх измерениях
• По возможности — автоматический тонометр (модель можно указать после ввода времени)
"""

# Второй экран приветствия (после «Начать»)
PRE_SURVEY_TEXT = """Спасибо за готовность принять участие! 🙌

Перед началом — несколько важных моментов:

🩺 <b>Что Вас ждёт:</b>
• короткий опрос о здоровье и образе жизни
• трёхкратное измерение артериального давления и пульса
• автоматический расчёт уровня риска

⏱️ Время прохождения: ~5–7 минут.

📌 <b>Важно:</b>
• измерения выполняются самостоятельно
• используйте автоматический тонометр (если есть)
• результаты носят скрининговый характер и не являются диагнозом

Все данные используются в обезличенном виде в научных целях.

Если Вы готовы — нажмите «Начать опрос» 👇"""


@router.callback_query(StateFilter(SurveyStates.welcome), F.data == "welcome_start")
async def welcome_start(callback: CallbackQuery, state: FSMContext):
    """Переход с первого экрана на второй (кнопка «Начать»)."""
    await callback.answer()
    await callback.message.answer(PRE_SURVEY_TEXT, reply_markup=get_main_menu_keyboard())
    await state.set_state(SurveyStates.main_menu)


# Обработчики главного меню
@router.callback_query(StateFilter(SurveyStates.main_menu), F.data == "start_survey")
async def start_survey(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    consent_text = """<b>1. Информированное согласие</b>

Согласны ли Вы на обработку ваших персональных и медицинских данных для целей исследования?"""
    
    await callback.message.answer(consent_text, reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_consent)


@router.callback_query(StateFilter(SurveyStates.main_menu), F.data == "invite_friend")
async def invite_friend(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Генерируем реферальную ссылку с ID пользователя
    bot_username = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={user_id}"
    
    invite_text = f"""👥 <b>Пригласите друга!</b>

🔗 Ваша реферальная ссылка:
<code>{ref_link}</code>

📋 <b>Как это работает:</b>
1. Поделитесь ссылкой с другом
2. Когда друг пройдет опрос по вашей ссылке
3. Вы получите подарок на выбор!

🎁 <b>Подарки на выбор:</b>
• 🎯 Питание
• 🏃 Физическая активность  
• 🧘 Стресс

Поделитесь ссылкой и получите подарок!"""
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться ссылкой", url=f"https://t.me/share/url?url={ref_link}&text=Пройди%20бесплатный%20чек-ап%20давления%20и%20образа%20жизни!")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(invite_text, reply_markup=keyboard)


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(PRE_SURVEY_TEXT, reply_markup=get_main_menu_keyboard())
    await state.set_state(SurveyStates.main_menu)


# Информированное согласие
@router.callback_query(StateFilter(SurveyStates.waiting_consent), F.data.in_(["yes", "no"]))
async def process_consent(callback: CallbackQuery, state: FSMContext):
    if callback.data == "no":
        await callback.answer("❌ Для прохождения опроса необходимо дать согласие на обработку данных.", show_alert=True)
        return
    
    await callback.answer()
    await state.update_data(consent=1)
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    instruction_text = """<b>2. Инструкция по измерению АД</b>
""" + BP_CHECKLIST + """
<b>Первое измерение АД</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75"""
    
    await callback.message.answer(instruction_text)
    await state.set_state(SurveyStates.waiting_bp1_values)




# Первое измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp1_values))
async def process_bp1_values(message: Message, state: FSMContext):
    text = message.text.strip()
    # Парсим формат: 120/80 или 120/80 75 (АД и пульс)
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b> (АД и пульс) или <b>120/80</b>")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse = int(match.group(3)) if match.group(3) else None
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    if pulse is not None and not (30 <= pulse <= 200):
        await message.answer("❌ Пульс должен быть в диапазоне 30–200. Введите снова или только АД (120/80).")
        return
    
    await state.update_data(
        bp1_systolic=systolic,
        bp1_diastolic=diastolic,
        bp1_pulse=pulse
    )
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    await message.answer(time_text)
    
    await state.set_state(SurveyStates.waiting_bp1_time)


@router.message(StateFilter(SurveyStates.waiting_bp1_time))
async def process_bp1_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    # Проверяем формат времени
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp1_time=time_text)
    
    await message.answer(
        "По возможности укажите модель тонометра (например: Omron M2). Если не хотите — напишите «нет» или «-»."
    )
    await state.set_state(SurveyStates.waiting_tonometer_model)


@router.message(StateFilter(SurveyStates.waiting_tonometer_model))
async def process_tonometer_model(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if text.lower() in ("нет", "-", "—", "."):
        text = ""
    await state.update_data(tonometer_model=text or None)
    await message.answer("<b>3. Демография и антропометрия</b>\n\nСколько вам полных лет? (только цифры)")
    await state.set_state(SurveyStates.waiting_age)


# Демография
@router.message(StateFilter(SurveyStates.waiting_age))
async def process_age(message: Message, state: FSMContext):
    try:
        age = int(message.text.strip())
        if not (15 <= age <= 45):
            await message.answer("❌ Возраст должен быть от 15 до 45 лет.")
            return
        await state.update_data(age=age)
        await message.answer("Ваш пол?", reply_markup=get_gender_keyboard())
        await state.set_state(SurveyStates.waiting_gender)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_gender), F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = "мужской" if callback.data == "gender_male" else "женский"
    gender_text = "👨 Мужской" if callback.data == "gender_male" else "👩 Женский"
    await state.update_data(gender=gender)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {gender_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("Ваш рост в сантиметрах? (только цифры)")
    await state.set_state(SurveyStates.waiting_height)


@router.message(StateFilter(SurveyStates.waiting_height))
async def process_height(message: Message, state: FSMContext):
    try:
        height = int(message.text.strip())
        if not (100 <= height <= 250):
            await message.answer("❌ Рост должен быть от 100 до 250 см.")
            return
        await state.update_data(height=height)
        await message.answer("Ваш вес в килограммах? (только цифры)")
        await state.set_state(SurveyStates.waiting_weight)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.message(StateFilter(SurveyStates.waiting_weight))
async def process_weight(message: Message, state: FSMContext):
    try:
        weight = float(message.text.strip().replace(",", "."))
        if not (30 <= weight <= 300):
            await message.answer("❌ Вес должен быть от 30 до 300 кг.")
            return
        
        data = await state.get_data()
        height = data.get("height")
        bmi = calculate_bmi(weight, height)
        
        await state.update_data(weight=weight, bmi=bmi)
        
        # Отправляем ИМТ отдельно
        await message.answer(f"Ваш ИМТ: <b>{bmi}</b>")
        
        # Затем отправляем вопрос об образовании
        await message.answer("Какой у Вас уровень образования?", reply_markup=get_education_keyboard())
        await state.set_state(SurveyStates.waiting_education)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_education), F.data.startswith("edu_"))
async def process_education(callback: CallbackQuery, state: FSMContext):
    education_map = {
        "edu_secondary": "среднее общее",
        "edu_professional": "среднее профессиональное",
        "edu_incomplete_higher": "неполное высшее",
        "edu_higher": "высшее"
    }
    education = education_map[callback.data]
    await state.update_data(education=education)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {education}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("Как Вы оцениваете свою финансовую стабильность?", reply_markup=get_financial_stability_keyboard())
    await state.set_state(SurveyStates.waiting_financial_stability)


@router.callback_query(StateFilter(SurveyStates.waiting_financial_stability), F.data.startswith("finance_"))
async def process_financial_stability(callback: CallbackQuery, state: FSMContext):
    finance_map = {
        "finance_low": "низкая",
        "finance_medium": "средняя",
        "finance_high": "высокая"
    }
    finance = finance_map[callback.data]
    await state.update_data(financial_stability=finance)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {finance}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("<b>4. Образ жизни и привычки</b>\n\n<b>Курение</b>\n\nКурите ли Вы сейчас или курили в последние 12 месяцев?", reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_smoking)


# Образ жизни
@router.callback_query(StateFilter(SurveyStates.waiting_smoking), F.data.in_(["yes", "no"]))
async def process_smoking(callback: CallbackQuery, state: FSMContext):
    smoking = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(smoking=smoking)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("<b>Алкоголь</b>\n\nСколько раз в неделю Вы употребляете алкоголь? (только цифры)")
    await state.set_state(SurveyStates.waiting_alcohol)


@router.message(StateFilter(SurveyStates.waiting_alcohol))
async def process_alcohol(message: Message, state: FSMContext):
    try:
        alcohol = int(message.text.strip())
        if alcohol < 0 or alcohol > 7:
            await message.answer("❌ Количество должно быть от 0 до 7 раз в неделю.")
            return
        await state.update_data(alcohol_per_week=alcohol)
        await message.answer("Сколько грамм соли в день, по Вашему мнению, Вы потребляете?\n(помните, что в чайной ложке без горки содержится примерно 7 г соли!) (только цифры)")
        await state.set_state(SurveyStates.waiting_salt)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.message(StateFilter(SurveyStates.waiting_salt))
async def process_salt(message: Message, state: FSMContext):
    try:
        salt = float(message.text.strip().replace(",", "."))
        if salt < 0 or salt > 50:
            await message.answer("❌ Количество соли должно быть от 0 до 50 г.")
            return
        await state.update_data(salt_per_day=salt)
        await message.answer("<b>Другие вредные привычки</b>\n\nЕсть ли у Вас другие вредные привычки?\n\nНапример:\n• Энергетики\n• Более 3 чашек кофе в день\n• Другие стимуляторы", reply_markup=get_yes_no_keyboard())
        await state.set_state(SurveyStates.waiting_other_habits)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_other_habits), F.data.in_(["yes", "no"]))
async def process_other_habits(callback: CallbackQuery, state: FSMContext):
    other_habits = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(other_habits=other_habits)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("Сколько часов в день Вы проводите за экраном? (только цифры)")
    await state.set_state(SurveyStates.waiting_screen_time)


@router.message(StateFilter(SurveyStates.waiting_screen_time))
async def process_screen_time(message: Message, state: FSMContext):
    try:
        screen_time = int(message.text.strip())
        if screen_time < 0 or screen_time > 24:
            await message.answer("❌ Количество часов должно быть от 0 до 24.")
            return
        await state.update_data(screen_time=screen_time)
        
        activity_text = """Занимаетесь ли Вы физической активностью? 

По определению ВОЗ, физическая активность — это какое-либо движение тела, производимое скелетными мышцами, которое требует расхода энергии. Термин «физическая активность» относится к любым видам движений, в том числе ходьба 30 минут 5 раз в неделю, бег, танцы, плавание, садоводство, домашние дела, работа?"""
        await message.answer(activity_text, reply_markup=get_yes_no_keyboard())
        await state.set_state(SurveyStates.waiting_physical_activity)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_physical_activity), F.data.in_(["yes", "no"]))
async def process_physical_activity(callback: CallbackQuery, state: FSMContext):
    physical_activity = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(physical_activity=physical_activity)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("Предполагает ли Ваша работа ночные дежурства?", reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_night_shifts)


@router.callback_query(StateFilter(SurveyStates.waiting_night_shifts), F.data.in_(["yes", "no"]))
async def process_night_shifts(callback: CallbackQuery, state: FSMContext):
    night_shifts = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(night_shifts=night_shifts)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    if night_shifts:
        await callback.message.answer("На какую ставку Вы работаете?", reply_markup=get_night_shifts_rate_keyboard())
        await state.set_state(SurveyStates.waiting_night_shifts_rate)
    else:
        await state.update_data(night_shifts_rate="")
        # Переходим ко второму измерению АД
        instruction_text = """<b>5. Инструкция по измерению АД</b>
""" + BP_CHECKLIST + """
<b>Второе измерение АД</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75"""
        await callback.message.answer(instruction_text)
        await state.set_state(SurveyStates.waiting_bp2_values)


@router.callback_query(StateFilter(SurveyStates.waiting_night_shifts_rate), F.data.startswith("shift_"))
async def process_night_shifts_rate(callback: CallbackQuery, state: FSMContext):
    if callback.data == "shift_more":
        rate = "> 1 ставки"
    elif callback.data == "shift_equal":
        rate = "= 1 ставки"
    else:
        rate = "< 1 ставки"
    await state.update_data(night_shifts_rate=rate)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {rate}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    instruction_text = """<b>5. Инструкция по измерению АД</b>
""" + BP_CHECKLIST + """
<b>Второе измерение АД</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75"""
    await callback.message.answer(instruction_text)
    await state.set_state(SurveyStates.waiting_bp2_values)


# Второе измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp2_values))
async def process_bp2_values(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b> (АД и пульс) или <b>120/80</b>")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse = int(match.group(3)) if match.group(3) else None
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    if pulse is not None and not (30 <= pulse <= 200):
        await message.answer("❌ Пульс должен быть в диапазоне 30–200. Введите снова или только АД (120/80).")
        return
    
    await state.update_data(
        bp2_systolic=systolic,
        bp2_diastolic=diastolic,
        bp2_pulse=pulse
    )
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    await message.answer(time_text)
    
    await state.set_state(SurveyStates.waiting_bp2_time)


@router.message(StateFilter(SurveyStates.waiting_bp2_time))
async def process_bp2_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp2_time=time_text)
    await message.answer("<b>6. Медицинская история</b>\n\nЕсть ли у Вас какие-то хронические заболевания?", reply_markup=get_chronic_diseases_keyboard())
    await state.set_state(SurveyStates.waiting_chronic_diseases)


# Медицинская история
@router.callback_query(StateFilter(SurveyStates.waiting_chronic_diseases), F.data.startswith("disease_"))
async def process_chronic_diseases(callback: CallbackQuery, state: FSMContext):
    if callback.data == "disease_other":
        await callback.answer()
        try:
            await callback.message.edit_text(
                (callback.message.text or "") + "\n\n<b>Ваш ответ:</b> Другое",
                reply_markup=None
            )
        except Exception:
            pass
        await callback.message.answer("Напишите, какое именно хроническое заболевание у Вас есть:")
        await state.set_state(SurveyStates.waiting_chronic_diseases_other)
        return
    disease_map = {
        "disease_none": "нет",
        "disease_hypertension": "Артериальная гипертензия/гипертоническая болезнь",
        "disease_diabetes": "Сахарный диабет",
        "disease_heart": "Инфаркт/инсульт",
        "disease_thyroid": "Гипертиреоз/гипотиреоз",
        "disease_kidney": "Хроническая болезнь почек"
    }
    disease = disease_map[callback.data]
    await state.update_data(chronic_diseases=disease)
    await callback.answer()
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {disease}"
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except Exception:
        pass
    await callback.message.answer("Принимаете ли Вы какие-либо лекарственные средства на постоянной основе?", reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_medications)


@router.message(StateFilter(SurveyStates.waiting_chronic_diseases_other))
async def process_chronic_diseases_other(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите название заболевания текстом.")
        return
    await state.update_data(chronic_diseases=text)
    await message.answer("Принимаете ли Вы какие-либо лекарственные средства на постоянной основе?", reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_medications)


@router.callback_query(StateFilter(SurveyStates.waiting_medications), F.data.in_(["yes", "no"]))
async def process_medications(callback: CallbackQuery, state: FSMContext):
    medications = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(medications=medications)
    await callback.answer()
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except Exception:
        pass
    if callback.data == "yes":
        await callback.message.answer("Укажите, какие именно препараты Вы принимаете (названия или группы):")
        await state.set_state(SurveyStates.waiting_medications_list)
    else:
        await state.update_data(medications_text=None)
        await _ask_family_history(callback.message, state)


async def _ask_family_history(message_or_callback, state: FSMContext):
    """Отправить вопрос о семейном анамнезе и перевести в состояние waiting_family_history."""
    text = """<b>7. Семейный анамнез</b>

Есть ли у ваших близких родственников (родители, братья/сестры, бабушки/дедушки) гипертония, инфаркт, инсульт или сахарный диабет?"""
    if hasattr(message_or_callback, "answer"):
        await message_or_callback.answer(text, reply_markup=get_yes_no_keyboard())
    await state.set_state(SurveyStates.waiting_family_history)


@router.message(StateFilter(SurveyStates.waiting_medications_list))
async def process_medications_list(message: Message, state: FSMContext):
    text = (message.text or "").strip()
    if not text:
        await message.answer("Введите названия препаратов.")
        return
    await state.update_data(medications_text=text)
    await _ask_family_history(message, state)


# Семейный анамнез
@router.callback_query(StateFilter(SurveyStates.waiting_family_history), F.data.in_(["yes", "no"]))
async def process_family_history(callback: CallbackQuery, state: FSMContext):
    family_history = 1 if callback.data == "yes" else 0
    answer_text = "✅ Да" if callback.data == "yes" else "❌ Нет"
    await state.update_data(family_history=family_history)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("<b>8. Психическое здоровье и стресс</b>\n\nОцените уровень стресса в Вашей жизни за последний месяц по шкале от 1 до 10\n(1 — совсем нет, 10 — очень сильный).")
    await state.set_state(SurveyStates.waiting_stress_level)


# Психическое здоровье
@router.message(StateFilter(SurveyStates.waiting_stress_level))
async def process_stress_level(message: Message, state: FSMContext):
    try:
        stress = int(message.text.strip())
        if not (1 <= stress <= 10):
            await message.answer("❌ Оценка должна быть от 1 до 10.")
            return
        await state.update_data(stress_level=stress)
        await message.answer("Оцените качество вашего сна за последний месяц по шкале от 1 до 10\n(1 — очень плохое, 10 — отличное).")
        await state.set_state(SurveyStates.waiting_sleep_quality)
    except ValueError:
        await message.answer("❌ Введите только цифры от 1 до 10.")


@router.message(StateFilter(SurveyStates.waiting_sleep_quality))
async def process_sleep_quality(message: Message, state: FSMContext):
    try:
        sleep = int(message.text.strip())
        if not (1 <= sleep <= 10):
            await message.answer("❌ Оценка должна быть от 1 до 10.")
            return
        await state.update_data(sleep_quality=sleep)
        
        phq_text = """<b>PHQ-2</b>

Как часто Вас беспокоили следующие проблемы за последние 2 недели?

<b>1. У Вас был снижен интерес или удовольствие от выполнения ежедневных дел</b>"""
        await message.answer(phq_text, reply_markup=get_phq_keyboard())
        await state.set_state(SurveyStates.waiting_phq2_q1)
    except ValueError:
        await message.answer("❌ Введите только цифры от 1 до 10.")


@router.callback_query(StateFilter(SurveyStates.waiting_phq2_q1), F.data.startswith("phq_"))
async def process_phq2_q1(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    phq_text_map = {0: "Ни разу", 1: "Несколько дней", 2: "Более половины времени", 3: "Почти каждый день"}
    answer_text = phq_text_map.get(score, "")
    await state.update_data(phq2_q1=score)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    await callback.message.answer("<b>2. У Вас было плохое настроение, Вы были подавлены или испытывали чувство безысходности</b>", reply_markup=get_phq_keyboard())
    await state.set_state(SurveyStates.waiting_phq2_q2)


@router.callback_query(StateFilter(SurveyStates.waiting_phq2_q2), F.data.startswith("phq_"))
async def process_phq2_q2(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    phq_text_map = {0: "Ни разу", 1: "Несколько дней", 2: "Более половины времени", 3: "Почти каждый день"}
    answer_text = phq_text_map.get(score, "")
    data = await state.get_data()
    phq2_q1 = data.get("phq2_q1", 0)
    phq2_score = phq2_q1 + score
    await state.update_data(phq2_q2=score, phq2_score=phq2_score)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    if phq2_score > 2:
        # Переходим к PHQ-9
        phq9_text = """<b>PHQ-9</b>

Как часто Вас беспокоили следующие проблемы за последние 2 недели?

<b>3. Вам было трудно заснуть или у Вас прерывистый сон, или Вы слишком много спали</b>"""
        await callback.message.answer(phq9_text, reply_markup=get_phq_keyboard())
        await state.set_state(SurveyStates.waiting_phq9)
        await state.update_data(phq9_answered=0, phq9_scores=[])  # Инициализируем счетчики
    else:
        await state.update_data(phq9_score=0)
        # Переходим к третьему измерению АД
        instruction_text = """<b>9. Инструкция по измерению АД</b>
""" + BP_CHECKLIST + """
<b>Третье измерение АД</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75"""
        await callback.message.answer(instruction_text)
        await state.set_state(SurveyStates.waiting_bp3_values)


# PHQ-9 обработчик
phq9_questions = [
    (3, "Вам было трудно заснуть или у Вас прерывистый сон, или Вы слишком много спали"),
    (4, "Вы были утомлены или у Вас было мало сил"),
    (5, "У вас плохой аппетит или Вы переедали"),
    (6, "Вы плохо о себе думали: считали себя неудачником (неудачницей) или были разочарованы, или считали, что подвели семью"),
    (7, "Вам было трудно сосредоточиться на каждодневных делах таких как, чтение газет или просмотр передач"),
    (8, "Вы двигались или говорили так медленно, что другие это отмечали, или наоборот, Вы были настолько суетливы или беспокойны, что двигались гораздо больше обычного"),
    (9, "Вас посещали мысли о том, что Вам лучше было бы умереть, или о том, чтобы причинить себе какой-либо вред"),
    (10, "Если у Вас были какие-нибудь из вышеперечисленных проблем, то оцените, насколько сложно Вам было работать, заниматься домашними делами или общаться из-за этих проблем")
]

@router.callback_query(StateFilter(SurveyStates.waiting_phq9), F.data.startswith("phq_"))
async def process_phq9(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    phq_text_map = {0: "Ни разу", 1: "Несколько дней", 2: "Более половины времени", 3: "Почти каждый день"}
    answer_text = phq_text_map.get(score, "")
    data = await state.get_data()
    phq9_answered = data.get("phq9_answered", 0)  # Количество отвеченных вопросов PHQ-9
    phq9_scores = data.get("phq9_scores", [])
    
    # Сохраняем балл текущего вопроса
    phq9_scores.append(score)
    phq9_answered += 1
    
    await state.update_data(phq9_answered=phq9_answered, phq9_scores=phq9_scores)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {answer_text}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    if phq9_answered < len(phq9_questions):
        # Следующий вопрос
        next_q = phq9_questions[phq9_answered]
        await callback.message.answer(f"<b>{next_q[0]}. {next_q[1]}</b>", reply_markup=get_phq_keyboard())
    else:
        # Все вопросы PHQ-9 отвечены
        phq2_score = data.get("phq2_score", 0)
        # PHQ-9 включает вопросы 1-2 (из PHQ-2) + вопросы 3-10
        total_phq9 = phq2_score + sum(phq9_scores)
        await state.update_data(phq9_score=total_phq9)
        
        instruction_text = """<b>9. Инструкция по измерению АД</b>
""" + BP_CHECKLIST + """
<b>Третье измерение АД</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75"""
        await callback.message.answer(instruction_text)
        await state.set_state(SurveyStates.waiting_bp3_values)


# Третье измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp3_values))
async def process_bp3_values(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b> (АД и пульс) или <b>120/80</b>")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse = int(match.group(3)) if match.group(3) else None
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    if pulse is not None and not (30 <= pulse <= 200):
        await message.answer("❌ Пульс должен быть в диапазоне 30–200. Введите снова или только АД (120/80).")
        return
    
    await state.update_data(
        bp3_systolic=systolic,
        bp3_diastolic=diastolic,
        bp3_pulse=pulse
    )
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    await message.answer(time_text)
    
    await state.set_state(SurveyStates.waiting_bp3_time)


@router.message(StateFilter(SurveyStates.waiting_bp3_time))
async def process_bp3_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp3_time=time_text)
    await message.answer("<b>10. Как Вы узнали об этом чат-боте?</b>", reply_markup=get_referral_source_keyboard())
    await state.set_state(SurveyStates.waiting_referral_source)


# Источник информации
@router.callback_query(StateFilter(SurveyStates.waiting_referral_source), F.data.startswith("source_"))
async def process_referral_source(callback: CallbackQuery, state: FSMContext):
    source_map = {
        "source_department": "На кафедре госпитальной терапии",
        "source_friends": "Посоветовали друзья",
        "source_family": "Посоветовали родственники",
        "source_other": "Свой вариант"
    }
    
    if callback.data == "source_other":
        await callback.answer()
        await callback.message.answer("Введите свой вариант:")
        await state.update_data(referral_source_custom=True)
        await state.set_state(SurveyStates.waiting_referral_source)
        return
    
    referral_source = source_map[callback.data]
    await state.update_data(referral_source=referral_source, referral_source_custom=False)
    await callback.answer()
    
    # Обновляем сообщение, добавляя выбранный ответ
    original_text = callback.message.text or ""
    updated_text = f"{original_text}\n\n<b>Ваш ответ:</b> {referral_source}"
    
    try:
        await callback.message.edit_text(updated_text, reply_markup=None)
    except:
        pass
    
    # Завершаем опрос и сохраняем данные
    # Используем callback.from_user.id напрямую, чтобы гарантировать правильный ID
    # Передаем правильный user_id в finish_survey
    await finish_survey(callback.message, state, user_id_override=callback.from_user.id)


@router.message(StateFilter(SurveyStates.waiting_referral_source))
async def process_referral_source_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("referral_source_custom"):
        await state.update_data(referral_source=message.text.strip(), referral_source_custom=False)
        await finish_survey(message, state)
    else:
        await message.answer("Пожалуйста, выберите вариант из меню.")


async def finish_survey(message: Message, state: FSMContext, user_id_override: int = None):
    """Завершение опроса, расчет результатов и сохранение в БД"""
    data = await state.get_data()
    # Используем переданный user_id, если он указан, иначе берем из message
    user_id = user_id_override if user_id_override is not None else message.from_user.id
    
    # Логируем информацию о пользователе для отладки
    logger.info(f"🔍 finish_survey: user_id = {user_id}, from_user.id = {message.from_user.id}, from_user.username = {message.from_user.username}")
    logger.info(f"🔍 message.chat.id = {message.chat.id}, message.from_user.full_name = {message.from_user.full_name}")
    
    # Убеждаемся, что пользователь существует в БД
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_exists = await cursor.fetchone()
        
        if not user_exists:
            # Создаем пользователя, если его нет
            from app.utils.referral import generate_referral_code
            ref_code = generate_referral_code(user_id)
            username = message.from_user.username or "Не указано"
            full_name = message.from_user.full_name or "Не указано"
            
            # Проверяем, был ли пользователь приглашен (проверяем таблицу referrals)
            referred_by = None
            async with db.execute(
                "SELECT referrer_id FROM referrals WHERE referred_id = ?",
                (user_id,)
            ) as cursor:
                referral_row = await cursor.fetchone()
                if referral_row and referral_row[0]:
                    referred_by = referral_row[0]
                    logger.info(f"Найден реферер для пользователя {user_id}: {referred_by}")
            
            logger.info(f"📝 Создание пользователя: user_id={user_id}, username={username}, full_name={full_name}, referred_by={referred_by}")
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, referral_code, referred_by) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, full_name, ref_code, referred_by)
            )
            await db.commit()
            
            # Проверяем, что пользователь действительно создан
            async with db.execute("SELECT user_id, username, referred_by FROM users WHERE user_id = ?", (user_id,)) as cursor:
                created_user = await cursor.fetchone()
                logger.info(f"✅ Проверка созданного пользователя: {created_user}")
            
            logger.info(f"Создан пользователь {user_id} при завершении опроса, referred_by = {referred_by}")
    
    # Вычисляем среднее АД из трех измерений
    bp1_sys = data.get("bp1_systolic", 0)
    bp1_dia = data.get("bp1_diastolic", 0)
    bp2_sys = data.get("bp2_systolic", 0)
    bp2_dia = data.get("bp2_diastolic", 0)
    bp3_sys = data.get("bp3_systolic", 0)
    bp3_dia = data.get("bp3_diastolic", 0)
    
    avg_systolic = (bp1_sys + bp2_sys + bp3_sys) // 3
    avg_diastolic = (bp1_dia + bp2_dia + bp3_dia) // 3
    
    # Определяем категорию АД
    bp_category = categorize_bp(avg_systolic, avg_diastolic)
    
    # Проверяем наличие АГ в анамнезе
    if "гипертензия" in data.get("chronic_diseases", "").lower() or "гипертония" in data.get("chronic_diseases", "").lower():
        bp_category = "АГ"
    
    # Рассчитываем риск
    risk_score = calculate_risk_score(data)
    risk_level = get_risk_level(bp_category, risk_score)
    
    # Получаем рекомендации
    recommendations = get_recommendations(bp_category, risk_level, data)
    
    # Сохраняем в БД
    logger.info(f"📝 Сохранение опроса: user_id={user_id}")
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            INSERT INTO surveys (
                user_id, consent, age, gender, height, weight, bmi, education, financial_stability,
                smoking, alcohol_per_week, salt_per_day, other_habits, screen_time, physical_activity,
                night_shifts, night_shifts_rate, chronic_diseases, medications, medications_text, family_history,
                stress_level, sleep_quality, phq2_score, phq9_score,
                bp1_systolic, bp1_diastolic, bp1_pulse, bp1_time,
                bp2_systolic, bp2_diastolic, bp2_pulse, bp2_time,
                bp3_systolic, bp3_diastolic, bp3_pulse, bp3_time,
                tonometer_model, referral_source, risk_level, risk_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, data.get("consent"), data.get("age"), data.get("gender"),
            data.get("height"), data.get("weight"), data.get("bmi"),
            data.get("education"), data.get("financial_stability"),
            data.get("smoking"), data.get("alcohol_per_week"), data.get("salt_per_day"),
            data.get("other_habits"), data.get("screen_time"), data.get("physical_activity"),
            data.get("night_shifts"), data.get("night_shifts_rate"),
            data.get("chronic_diseases"), data.get("medications"), data.get("medications_text"),
            data.get("family_history"),
            data.get("stress_level"), data.get("sleep_quality"),
            data.get("phq2_score", 0), data.get("phq9_score", 0),
            data.get("bp1_systolic"), data.get("bp1_diastolic"), data.get("bp1_pulse"), data.get("bp1_time"),
            data.get("bp2_systolic"), data.get("bp2_diastolic"), data.get("bp2_pulse"), data.get("bp2_time"),
            data.get("bp3_systolic"), data.get("bp3_diastolic"), data.get("bp3_pulse"), data.get("bp3_time"),
            data.get("tonometer_model"), data.get("referral_source"), risk_level, risk_score
        ))
        await db.commit()
    
    # Формируем результат
    result_text = f"""<b>📊 Результаты</b>

<b>Категория АД:</b> {bp_category}
<b>Среднее АД:</b> {avg_systolic}/{avg_diastolic} мм рт.ст.
<b>Балл риска:</b> {risk_score}
<b>Уровень риска:</b> <b>{risk_level.upper()}</b>

{recommendations}

<b>Ваши данные очень помогли нашему исследованию. Спасибо!</b>

Небольшая просьба: если у вас есть друг или родственник, который тоже заботится о здоровье (или наоборот, вечно откладывает поход к врачу) — скиньте ему ссылку на прохождение чат-бота.

Для него это — быстрая самопроверка, для нас — важные данные. Будем очень благодарны!

<b>«За каждого друга, который пройдет опрос по Вашей рекомендации, мы вышлем Вам приятный и полезный подарок»</b>

Выберите подарок:"""
    
    # Если высокое давление или АГ, добавляем информацию о дневнике
    if bp_category in ["Высокое давление", "АГ"]:
        diary_text = "\n\n📝 <b>Дневник давления</b>\nРекомендуем измерять давление каждые 4 часа и записывать результаты."
        result_text = result_text.replace(recommendations, recommendations + diary_text)
    
    # Всегда показываем выбор подарка после завершения опроса
    # Используем bot.send_message для гарантии правильной работы
    await message.bot.send_message(chat_id=message.chat.id, text=result_text, reply_markup=get_gift_keyboard())
    await state.set_state(SurveyStates.waiting_gift_choice)
    
    # Отправляем дневник давления пользователям с умеренным или высоким уровнем риска
    if risk_level in ["умеренный", "высокий"]:
        diary_file_path = os.path.join("file", "Дневник давления.pdf")
        if os.path.exists(diary_file_path):
            try:
                diary_file = FSInputFile(diary_file_path, filename="Дневник давления.pdf")
                diary_text = "Распечатайте и ведите дневник давления! Это самый простой и наглядный способ отслеживать динамику и заботиться о себе."
                await message.bot.send_document(
                    chat_id=message.chat.id,
                    document=diary_file,
                    caption=diary_text
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке дневника давления: {e}", exc_info=True)
    
    # Отправляем подарок рефереру, если пользователь был приглашен
    await send_gift_to_referrer(message.bot, user_id)


# Выбор подарка
@router.callback_query(StateFilter(SurveyStates.waiting_gift_choice), F.data.startswith("gift_"))
async def process_gift_choice(callback: CallbackQuery, state: FSMContext):
    gift_map = {
        "gift_nutrition": "Питание",
        "gift_activity": "Физическая активность",
        "gift_stress": "Стресс"
    }
    gift_type = gift_map[callback.data]
    user_id = callback.from_user.id
    
    # Сохраняем предпочтение подарка для будущего реферала
    async with aiosqlite.connect(get_db_path()) as db:
        # Сохраняем предпочтение подарка в профиле пользователя
        await db.execute(
            "UPDATE users SET preferred_gift = ? WHERE user_id = ?",
            (gift_type, user_id)
        )
        await db.commit()
        
        await callback.answer(f"✅ Вы выбрали подарок: {gift_type}")
        
        # Генерируем реферальную ссылку с ID пользователя
        bot_username = (await callback.message.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={user_id}"
        
        # Формируем новое сообщение
        gift_message = f"""✅ <b>Подарок выбран!</b>

Вы выбрали подарок: <b>{gift_type}</b>

🔗 <b>Ваша реферальная ссылка:</b>
{ref_link}

📋 <b>Инструкция:</b>
1. Скопируйте ссылку
2. Отправьте её другу
3. После того, как друг пройдет тест, вы получите подарок!"""
        
        # Создаем клавиатуру с кнопкой "Пройти тест еще раз", которая отправляет команду /start
        restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Пройти тест еще раз", callback_data="restart_survey")]
        ])
        
        # Отправляем новое сообщение
        await callback.message.answer(gift_message, reply_markup=restart_keyboard)
    
    await state.clear()


# Обработчик кнопки "Пройти тест еще раз"
@router.callback_query(F.data == "restart_survey")
async def restart_survey_handler(callback: CallbackQuery, state: FSMContext):
    """Обработчик кнопки 'Пройти тест еще раз' - отправляет команду /start"""
    await state.clear()
    await callback.answer()
    
    # Создаем правильный объект Message для вызова cmd_start
    # Используем model_copy для создания копии с измененными полями
    fake_message = callback.message.model_copy(update={
        "text": "/start",
        "from_user": callback.from_user,
        "message_id": callback.message.message_id + 1000
    })
    
    # Вызываем обработчик команды /start
    await cmd_start(fake_message, state)


# Обработчик кнопки "Пригласить друга" после выбора подарка
