import re
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

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
    get_cancel_keyboard,
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


async def notify_admins_about_survey(bot, user_id: int):
    """Уведомить админов о прохождении теста пользователем"""
    if not ADMIN_IDS:
        return
    
    async with aiosqlite.connect(get_db_path()) as db:
        # Получаем информацию о пользователе
        async with db.execute(
            "SELECT full_name, username FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            user_row = await cursor.fetchone()
            if not user_row:
                return
            user_full_name = user_row[0] or "Не указано"
            user_username = user_row[1] or "Не указано"
        
        # Проверяем, был ли пользователь приглашен
        async with db.execute(
            "SELECT referrer_id FROM referrals WHERE referred_id = ?",
            (user_id,)
        ) as cursor:
            referral_row = await cursor.fetchone()
            referrer_id = referral_row[0] if referral_row else None
        
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
            
            notification_text = f"""🔔 <b>Новое уведомление</b>

<b>Пользователь</b>
Имя: {user_full_name}
Username: @{user_username}
ID: {user_id}

прошел опрос

<b>Его пригласил:</b>
Имя: {referrer_full_name}
Username: @{referrer_username}
ID: {referrer_id}

<b>Ему нужно подарить:</b> {preferred_gift}"""
        else:
            notification_text = f"""🔔 <b>Новое уведомление</b>

<b>Пользователь</b>
Имя: {user_full_name}
Username: @{user_username}
ID: {user_id}

прошел опрос

<i>Не был приглашен</i>"""
    
    # Отправляем уведомление всем админам
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, notification_text)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def update_or_send_message(bot, chat_id, message_id, text, reply_markup=None, state=None):
    """Обновить сообщение или отправить новое, если обновление невозможно"""
    try:
        if message_id:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                reply_markup=reply_markup
            )
            return message_id
    except Exception:
        pass
    
    # Если не удалось обновить, отправляем новое
    sent = await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
    if state:
        await state.update_data(current_message_id=sent.message_id)
    return sent.message_id


async def delete_user_message(message: Message):
    """Удалить сообщение пользователя"""
    try:
        await message.delete()
    except Exception:
        pass  # Игнорируем ошибки удаления


async def update_bot_message(message: Message, state: FSMContext, text: str, reply_markup=None):
    """Обновить сообщение бота или отправить новое"""
    data = await state.get_data()
    current_message_id = data.get("current_message_id")
    
    if current_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=current_message_id,
                text=text,
                reply_markup=reply_markup
            )
            return current_message_id
        except Exception:
            pass
    
    # Если не удалось обновить, отправляем новое
    sent = await message.answer(text, reply_markup=reply_markup)
    await state.update_data(current_message_id=sent.message_id)
    return sent.message_id

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
        # Проверяем реферальный код
        referral_code = None
        if len(message.text.split()) > 1:
            referral_code = message.text.split()[1]
        
        # Проверяем существование пользователя
        async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user_exists = await cursor.fetchone()
        
        if not user_exists:
            # Создаем нового пользователя
            ref_code = generate_referral_code(user_id)
            referred_by = None
            
            if referral_code:
                # Ищем того, кто пригласил
                async with db.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,)) as cursor:
                    referrer = await cursor.fetchone()
                    if referrer:
                        referred_by = referrer[0]
            
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
            await db.execute(
                "UPDATE users SET username = ?, full_name = ? WHERE user_id = ?",
                (username, full_name, user_id)
            )
            await db.commit()
    
    welcome_text = """👋 <b>Добро пожаловать!</b>

<b>Бесплатный чек-ап давления и образа жизни за 15 минут</b>

Данный опросник подходит для возрастной категории лиц от 15-45 лет.

<b>Знаете ли Вы, что такое предгипертония?</b> Это пограничное состояние, когда давление еще не требует лекарств, но уже сигнализирует: пора менять привычки. И оно есть у 30-40% взрослых людей, многие из которых об этом даже не догадываются.

Это не диагноз, а повод задуматься о своем здоровье и получить удобный цифровой срез.

Помогите исследованию и проверьте себя! 👇"""
    
    sent_message = await message.answer(welcome_text, reply_markup=get_start_keyboard())
    await state.update_data(main_message_id=sent_message.message_id)
    await state.set_state(SurveyStates.main_menu)


# Обработчики главного меню
@router.callback_query(StateFilter(SurveyStates.main_menu), F.data == "start_survey")
async def start_survey(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    consent_text = """<b>1. Информированное согласие</b>

Согласны ли Вы на обработку ваших персональных и медицинских данных для целей исследования?"""
    
    await callback.message.edit_text(consent_text, reply_markup=get_yes_no_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_consent)


@router.callback_query(StateFilter(SurveyStates.main_menu), F.data == "invite_friend")
async def invite_friend(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    user_id = callback.from_user.id
    
    # Получаем реферальный код
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            ref_code = row[0] if row else None
    
    if ref_code:
        bot_username = (await callback.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={ref_code}"
        
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
    else:
        await callback.message.edit_text("❌ Ошибка: не удалось получить реферальную ссылку. Попробуйте позже.", reply_markup=get_main_menu_keyboard())


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    welcome_text = """👋 <b>Добро пожаловать!</b>

<b>Бесплатный чек-ап давления и образа жизни за 15 минут</b>

Данный опросник подходит для возрастной категории лиц от 15-45 лет.

<b>Знаете ли Вы, что такое предгипертония?</b> Это пограничное состояние, когда давление еще не требует лекарств, но уже сигнализирует: пора менять привычки. И оно есть у 30-40% взрослых людей, многие из которых об этом даже не догадываются.

Это не диагноз, а повод задуматься о своем здоровье и получить удобный цифровой срез.

Помогите исследованию и проверьте себя! 👇"""
    
    await callback.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard())
    await state.set_state(SurveyStates.main_menu)


# Информированное согласие
@router.callback_query(StateFilter(SurveyStates.waiting_consent), F.data.in_(["yes", "no"]))
async def process_consent(callback: CallbackQuery, state: FSMContext):
    if callback.data == "no":
        await callback.answer("❌ Для прохождения опроса необходимо дать согласие на обработку данных.", show_alert=True)
        return
    
    await callback.answer()
    await state.update_data(consent=1)
    
    instruction_text = """<b>2. Инструкция по измерению АД и пульса</b>

Пожалуйста, измерьте своё артериальное давление и пульс, используя тонометр. Сидите спокойно не менее 5 минут перед измерением.

<b>Первое измерение АД/пульса</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75

⚠️ <b>Важно:</b> Пульс обязателен!"""
    
    await callback.message.edit_text(instruction_text, reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_bp1_values)


# Обработчик отмены опроса
@router.callback_query(StateFilter("*"), F.data == "cancel_survey")
async def cancel_survey(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    
    welcome_text = """👋 <b>Добро пожаловать!</b>

<b>Бесплатный чек-ап давления и образа жизни за 15 минут</b>

Данный опросник подходит для возрастной категории лиц от 15-45 лет.

<b>Знаете ли Вы, что такое предгипертония?</b> Это пограничное состояние, когда давление еще не требует лекарств, но уже сигнализирует: пора менять привычки. И оно есть у 30-40% взрослых людей, многие из которых об этом даже не догадываются.

Это не диагноз, а повод задуматься о своем здоровье и получить удобный цифровой срез.

Помогите исследованию и проверьте себя! 👇"""
    
    await callback.message.edit_text(welcome_text, reply_markup=get_main_menu_keyboard())
    await state.set_state(SurveyStates.main_menu)


# Первое измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp1_values))
async def process_bp1_values(message: Message, state: FSMContext):
    text = message.text.strip()
    # Парсим формат: 120/80 75 (пульс обязателен)
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b>\n\n<b>Важно:</b> Пульс обязателен!")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse_str = match.group(3)
    
    # Проверяем наличие пульса
    if not pulse_str:
        await message.answer("❌ Пульс обязателен! Введите в формате: <b>120/80 75</b>\n\nПример: 120/80 75")
        return
    
    pulse = int(pulse_str)
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    
    if not (40 <= pulse <= 200):
        await message.answer("❌ Проверьте значение пульса. Должно быть 40-200.")
        return
    
    await state.update_data(
        bp1_systolic=systolic,
        bp1_diastolic=diastolic,
        bp1_pulse=pulse
    )
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    data = await state.get_data()
    current_message_id = data.get("current_message_id")
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    
    if current_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=current_message_id,
                text=time_text,
                reply_markup=get_cancel_keyboard()
            )
        except:
            sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
            await state.update_data(current_message_id=sent.message_id)
    else:
        sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=sent.message_id)
    
    await state.set_state(SurveyStates.waiting_bp1_time)


@router.message(StateFilter(SurveyStates.waiting_bp1_time))
async def process_bp1_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    # Проверяем формат времени
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp1_time=time_text)
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    await update_bot_message(message, state, "<b>3. Демография и антропометрия</b>\n\nСколько вам полных лет? (только цифры)", get_cancel_keyboard())
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
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, "Ваш пол?", get_gender_keyboard())
        await state.set_state(SurveyStates.waiting_gender)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_gender), F.data.startswith("gender_"))
async def process_gender(callback: CallbackQuery, state: FSMContext):
    gender = "мужской" if callback.data == "gender_male" else "женский"
    await state.update_data(gender=gender)
    await callback.answer()
    await callback.message.edit_text("Ваш рост в сантиметрах? (только цифры)", reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_height)


@router.message(StateFilter(SurveyStates.waiting_height))
async def process_height(message: Message, state: FSMContext):
    try:
        height = int(message.text.strip())
        if not (100 <= height <= 250):
            await message.answer("❌ Рост должен быть от 100 до 250 см.")
            return
        await state.update_data(height=height)
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, "Ваш вес в килограммах? (только цифры)", get_cancel_keyboard())
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
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, f"Ваш ИМТ: <b>{bmi}</b>\n\nКакой у Вас уровень образования?", get_education_keyboard())
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
    await callback.message.edit_text("Как Вы оцениваете свою финансовую стабильность?", reply_markup=get_financial_stability_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
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
    
    await callback.message.edit_text("<b>4. Образ жизни и привычки</b>\n\nКурите ли Вы сейчас или курили в последние 12 месяцев?", reply_markup=get_yes_no_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_smoking)


# Образ жизни
@router.callback_query(StateFilter(SurveyStates.waiting_smoking), F.data.in_(["yes", "no"]))
async def process_smoking(callback: CallbackQuery, state: FSMContext):
    smoking = 1 if callback.data == "yes" else 0
    await state.update_data(smoking=smoking)
    await callback.answer()
    await callback.message.edit_text("Сколько раз в неделю Вы употребляете алкоголь? (только цифры)", reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_alcohol)


@router.message(StateFilter(SurveyStates.waiting_alcohol))
async def process_alcohol(message: Message, state: FSMContext):
    try:
        alcohol = int(message.text.strip())
        if alcohol < 0 or alcohol > 7:
            await message.answer("❌ Количество должно быть от 0 до 7 раз в неделю.")
            return
        await state.update_data(alcohol_per_week=alcohol)
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, "Сколько грамм соли в день, по Вашему мнению, Вы потребляете?\n(помните, что в чайной ложке без горки содержится примерно 7 г соли!) (только цифры)", get_cancel_keyboard())
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
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, "Есть ли у Вас другие вредные привычки (энергетики, наркотики)?", get_yes_no_keyboard())
        await state.set_state(SurveyStates.waiting_other_habits)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_other_habits), F.data.in_(["yes", "no"]))
async def process_other_habits(callback: CallbackQuery, state: FSMContext):
    other_habits = 1 if callback.data == "yes" else 0
    await state.update_data(other_habits=other_habits)
    await callback.answer()
    await callback.message.edit_text("Сколько часов в день Вы проводите за экраном? (только цифры)", reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_screen_time)


@router.message(StateFilter(SurveyStates.waiting_screen_time))
async def process_screen_time(message: Message, state: FSMContext):
    try:
        screen_time = int(message.text.strip())
        if screen_time < 0 or screen_time > 24:
            await message.answer("❌ Количество часов должно быть от 0 до 24.")
            return
        await state.update_data(screen_time=screen_time)
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        activity_text = """Занимаетесь ли Вы физической активностью? 

По определению ВОЗ, физическая активность — это какое-либо движение тела, производимое скелетными мышцами, которое требует расхода энергии. Термин «физическая активность» относится к любым видам движений, в том числе ходьба 30 минут 5 раз в неделю, бег, танцы, плавание, садоводство, домашние дела, работа?"""
        await update_bot_message(message, state, activity_text, get_yes_no_keyboard())
        await state.set_state(SurveyStates.waiting_physical_activity)
    except ValueError:
        await message.answer("❌ Введите только цифры.")


@router.callback_query(StateFilter(SurveyStates.waiting_physical_activity), F.data.in_(["yes", "no"]))
async def process_physical_activity(callback: CallbackQuery, state: FSMContext):
    physical_activity = 1 if callback.data == "yes" else 0
    await state.update_data(physical_activity=physical_activity)
    await callback.answer()
    await callback.message.edit_text("Предполагает ли Ваша работа ночные дежурства?", reply_markup=get_yes_no_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_night_shifts)


@router.callback_query(StateFilter(SurveyStates.waiting_night_shifts), F.data.in_(["yes", "no"]))
async def process_night_shifts(callback: CallbackQuery, state: FSMContext):
    night_shifts = 1 if callback.data == "yes" else 0
    await state.update_data(night_shifts=night_shifts)
    await callback.answer()
    
    if night_shifts:
        await callback.message.edit_text("На какую ставку Вы работаете?", reply_markup=get_night_shifts_rate_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
        await state.set_state(SurveyStates.waiting_night_shifts_rate)
    else:
        await state.update_data(night_shifts_rate="")
        # Переходим ко второму измерению АД
        instruction_text = """<b>5. Инструкция по измерению АД и пульса</b>

Пожалуйста, измерьте своё артериальное давление и пульс, используя тонометр. Сидите спокойно не менее 5 минут перед измерением.

<b>Второе измерение АД/пульса</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75

⚠️ <b>Важно:</b> Пульс обязателен!"""
        await callback.message.edit_text(instruction_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
        await state.set_state(SurveyStates.waiting_bp2_values)


@router.callback_query(StateFilter(SurveyStates.waiting_night_shifts_rate), F.data.startswith("shift_"))
async def process_night_shifts_rate(callback: CallbackQuery, state: FSMContext):
    rate = "> 1 ставки" if callback.data == "shift_more" else "< 1 ставки"
    await state.update_data(night_shifts_rate=rate)
    await callback.answer()
    
    instruction_text = """<b>5. Инструкция по измерению АД и пульса</b>

Пожалуйста, измерьте своё артериальное давление и пульс, используя тонометр. Сидите спокойно не менее 5 минут перед измерением.

<b>Второе измерение АД/пульса</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75

⚠️ <b>Важно:</b> Пульс обязателен!"""
    await callback.message.edit_text(instruction_text, reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_bp2_values)


# Второе измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp2_values))
async def process_bp2_values(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b>\n\n<b>Важно:</b> Пульс обязателен!")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse_str = match.group(3)
    
    # Проверяем наличие пульса
    if not pulse_str:
        await message.answer("❌ Пульс обязателен! Введите в формате: <b>120/80 75</b>\n\nПример: 120/80 75")
        return
    
    pulse = int(pulse_str)
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    
    if not (40 <= pulse <= 200):
        await message.answer("❌ Проверьте значение пульса. Должно быть 40-200.")
        return
    
    await state.update_data(
        bp2_systolic=systolic,
        bp2_diastolic=diastolic,
        bp2_pulse=pulse
    )
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    data = await state.get_data()
    current_message_id = data.get("current_message_id")
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    
    if current_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=current_message_id,
                text=time_text,
                reply_markup=get_cancel_keyboard()
            )
        except:
            sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
            await state.update_data(current_message_id=sent.message_id)
    else:
        sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=sent.message_id)
    
    await state.set_state(SurveyStates.waiting_bp2_time)


@router.message(StateFilter(SurveyStates.waiting_bp2_time))
async def process_bp2_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp2_time=time_text)
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    await update_bot_message(message, state, "<b>6. Медицинская история</b>\n\nЕсть ли у Вас какие-то хронические заболевания?", get_chronic_diseases_keyboard())
    await state.set_state(SurveyStates.waiting_chronic_diseases)


# Медицинская история
@router.callback_query(StateFilter(SurveyStates.waiting_chronic_diseases), F.data.startswith("disease_"))
async def process_chronic_diseases(callback: CallbackQuery, state: FSMContext):
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
    await callback.message.edit_text("Принимаете ли Вы какие-либо лекарственные средства на постоянной основе?", reply_markup=get_yes_no_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_medications)


@router.callback_query(StateFilter(SurveyStates.waiting_medications), F.data.in_(["yes", "no"]))
async def process_medications(callback: CallbackQuery, state: FSMContext):
    medications = 1 if callback.data == "yes" else 0
    await state.update_data(medications=medications)
    await callback.answer()
    await callback.message.edit_text("<b>7. Семейный анамнез</b>\n\nЕсть ли у ваших близких родственников (родители, братья/сестры/бабушки/дедушки) гипертония/инфаркт/инсульт?", reply_markup=get_yes_no_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_family_history)


# Семейный анамнез
@router.callback_query(StateFilter(SurveyStates.waiting_family_history), F.data.in_(["yes", "no"]))
async def process_family_history(callback: CallbackQuery, state: FSMContext):
    family_history = 1 if callback.data == "yes" else 0
    await state.update_data(family_history=family_history)
    await callback.answer()
    await callback.message.edit_text("<b>8. Психическое здоровье и стресс</b>\n\nОцените уровень стресса в Вашей жизни за последний месяц по шкале от 1 до 10\n(1 — совсем нет, 10 — очень сильный).", reply_markup=get_cancel_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
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
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await update_bot_message(message, state, "Оцените качество вашего сна за последний месяц по шкале от 1 до 10\n(1 — очень плохое, 10 — отличное).", get_cancel_keyboard())
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
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        phq_text = """<b>PHQ-2</b>

Как часто Вас беспокоили следующие проблемы за последние 2 недели?

<b>1. У Вас был снижен интерес или удовольствие от выполнения ежедневных дел</b>"""
        await update_bot_message(message, state, phq_text, get_phq_keyboard())
        await state.set_state(SurveyStates.waiting_phq2_q1)
    except ValueError:
        await message.answer("❌ Введите только цифры от 1 до 10.")


@router.callback_query(StateFilter(SurveyStates.waiting_phq2_q1), F.data.startswith("phq_"))
async def process_phq2_q1(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    await state.update_data(phq2_q1=score)
    await callback.answer()
    await callback.message.edit_text("<b>2. У Вас было плохое настроение, Вы были подавлены или испытывали чувство безысходности</b>", reply_markup=get_phq_keyboard())
    await state.update_data(current_message_id=callback.message.message_id)
    await state.set_state(SurveyStates.waiting_phq2_q2)


@router.callback_query(StateFilter(SurveyStates.waiting_phq2_q2), F.data.startswith("phq_"))
async def process_phq2_q2(callback: CallbackQuery, state: FSMContext):
    score = int(callback.data.split("_")[1])
    data = await state.get_data()
    phq2_q1 = data.get("phq2_q1", 0)
    phq2_score = phq2_q1 + score
    await state.update_data(phq2_q2=score, phq2_score=phq2_score)
    await callback.answer()
    
    if phq2_score > 2:
        # Переходим к PHQ-9
        phq9_text = """<b>PHQ-9</b>

Как часто Вас беспокоили следующие проблемы за последние 2 недели?

<b>3. Вам было трудно заснуть или у Вас прерывистый сон, или Вы слишком много спали</b>"""
        await callback.message.edit_text(phq9_text, reply_markup=get_phq_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
        await state.set_state(SurveyStates.waiting_phq9)
        await state.update_data(phq9_answered=0, phq9_scores=[])  # Инициализируем счетчики
    else:
        await state.update_data(phq9_score=0)
        # Переходим к третьему измерению АД
        instruction_text = """<b>9. Инструкция по измерению АД и пульса</b>

Пожалуйста, измерьте своё артериальное давление и пульс, используя тонометр. Сидите спокойно не менее 5 минут перед измерением.

<b>Третье измерение АД/пульса</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75

⚠️ <b>Важно:</b> Пульс обязателен!"""
        await callback.message.edit_text(instruction_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
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
    data = await state.get_data()
    phq9_answered = data.get("phq9_answered", 0)  # Количество отвеченных вопросов PHQ-9
    phq9_scores = data.get("phq9_scores", [])
    
    # Сохраняем балл текущего вопроса
    phq9_scores.append(score)
    phq9_answered += 1
    
    await state.update_data(phq9_answered=phq9_answered, phq9_scores=phq9_scores)
    await callback.answer()
    
    if phq9_answered < len(phq9_questions):
        # Следующий вопрос
        next_q = phq9_questions[phq9_answered]
        await callback.message.edit_text(f"<b>{next_q[0]}. {next_q[1]}</b>", reply_markup=get_phq_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
    else:
        # Все вопросы PHQ-9 отвечены
        phq2_score = data.get("phq2_score", 0)
        # PHQ-9 включает вопросы 1-2 (из PHQ-2) + вопросы 3-10
        total_phq9 = phq2_score + sum(phq9_scores)
        await state.update_data(phq9_score=total_phq9)
        
        instruction_text = """<b>9. Инструкция по измерению АД и пульса</b>

Пожалуйста, измерьте своё артериальное давление и пульс, используя тонометр. Сидите спокойно не менее 5 минут перед измерением.

<b>Третье измерение АД/пульса</b>
Введите значения АД (верхнее/нижнее) и пульс.
<b>Пример:</b> 120/80 75

⚠️ <b>Важно:</b> Пульс обязателен!"""
        await callback.message.edit_text(instruction_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=callback.message.message_id)
        await state.set_state(SurveyStates.waiting_bp3_values)


# Третье измерение АД
@router.message(StateFilter(SurveyStates.waiting_bp3_values))
async def process_bp3_values(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'(\d+)/(\d+)(?:\s+(\d+))?', text)
    
    if not match:
        await message.answer("❌ Неверный формат. Введите в формате: <b>120/80 75</b>\n\n<b>Важно:</b> Пульс обязателен!")
        return
    
    systolic = int(match.group(1))
    diastolic = int(match.group(2))
    pulse_str = match.group(3)
    
    # Проверяем наличие пульса
    if not pulse_str:
        await message.answer("❌ Пульс обязателен! Введите в формате: <b>120/80 75</b>\n\nПример: 120/80 75")
        return
    
    pulse = int(pulse_str)
    
    if not (50 <= systolic <= 250 and 30 <= diastolic <= 150):
        await message.answer("❌ Проверьте значения АД. Верхнее должно быть 50-250, нижнее 30-150.")
        return
    
    if not (40 <= pulse <= 200):
        await message.answer("❌ Проверьте значение пульса. Должно быть 40-200.")
        return
    
    await state.update_data(
        bp3_systolic=systolic,
        bp3_diastolic=diastolic,
        bp3_pulse=pulse
    )
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    data = await state.get_data()
    current_message_id = data.get("current_message_id")
    
    time_text = "⏰ Укажите время измерения.\n<b>Пример:</b> 12:00 или 09:02"
    
    if current_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=current_message_id,
                text=time_text,
                reply_markup=get_cancel_keyboard()
            )
        except:
            sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
            await state.update_data(current_message_id=sent.message_id)
    else:
        sent = await message.answer(time_text, reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=sent.message_id)
    
    await state.set_state(SurveyStates.waiting_bp3_time)


@router.message(StateFilter(SurveyStates.waiting_bp3_time))
async def process_bp3_time(message: Message, state: FSMContext):
    time_text = message.text.strip()
    if not re.match(r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
        await message.answer("❌ Неверный формат времени. Введите в формате: <b>12:00</b> или <b>09:02</b>")
        return
    
    await state.update_data(bp3_time=time_text)
    
    # Удаляем сообщение пользователя
    await delete_user_message(message)
    
    await update_bot_message(message, state, "<b>10. Как Вы узнали об этом чат-боте?</b>", get_referral_source_keyboard())
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
        await callback.message.edit_text("Введите свой вариант:", reply_markup=get_cancel_keyboard())
        await state.update_data(current_message_id=callback.message.message_id, referral_source_custom=True)
        await state.set_state(SurveyStates.waiting_referral_source)
        return
    
    referral_source = source_map[callback.data]
    await state.update_data(referral_source=referral_source, referral_source_custom=False)
    await callback.answer()
    
    # Завершаем опрос и сохраняем данные
    await finish_survey(callback.message, state)


@router.message(StateFilter(SurveyStates.waiting_referral_source))
async def process_referral_source_text(message: Message, state: FSMContext):
    data = await state.get_data()
    if data.get("referral_source_custom"):
        await state.update_data(referral_source=message.text.strip(), referral_source_custom=False)
        
        # Удаляем сообщение пользователя
        await delete_user_message(message)
        
        await finish_survey(message, state)
    else:
        await message.answer("Пожалуйста, выберите вариант из меню.")


async def finish_survey(message: Message, state: FSMContext):
    """Завершение опроса, расчет результатов и сохранение в БД"""
    data = await state.get_data()
    user_id = message.from_user.id
    
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
    async with aiosqlite.connect(get_db_path()) as db:
        await db.execute("""
            INSERT INTO surveys (
                user_id, consent, age, gender, height, weight, bmi, education, financial_stability,
                smoking, alcohol_per_week, salt_per_day, other_habits, screen_time, physical_activity,
                night_shifts, night_shifts_rate, chronic_diseases, medications, family_history,
                stress_level, sleep_quality, phq2_score, phq9_score,
                bp1_systolic, bp1_diastolic, bp1_pulse, bp1_time,
                bp2_systolic, bp2_diastolic, bp2_pulse, bp2_time,
                bp3_systolic, bp3_diastolic, bp3_pulse, bp3_time,
                referral_source, risk_level, risk_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, data.get("consent"), data.get("age"), data.get("gender"),
            data.get("height"), data.get("weight"), data.get("bmi"),
            data.get("education"), data.get("financial_stability"),
            data.get("smoking"), data.get("alcohol_per_week"), data.get("salt_per_day"),
            data.get("other_habits"), data.get("screen_time"), data.get("physical_activity"),
            data.get("night_shifts"), data.get("night_shifts_rate"),
            data.get("chronic_diseases"), data.get("medications"), data.get("family_history"),
            data.get("stress_level"), data.get("sleep_quality"),
            data.get("phq2_score", 0), data.get("phq9_score", 0),
            data.get("bp1_systolic"), data.get("bp1_diastolic"), data.get("bp1_pulse", 0), data.get("bp1_time"),
            data.get("bp2_systolic"), data.get("bp2_diastolic"), data.get("bp2_pulse", 0), data.get("bp2_time"),
            data.get("bp3_systolic"), data.get("bp3_diastolic"), data.get("bp3_pulse", 0), data.get("bp3_time"),
            data.get("referral_source"), risk_level, risk_score
        ))
        await db.commit()
    
    # Формируем результат
    result_text = f"""<b>📊 Результаты</b>

<b>Категория АД:</b> {bp_category}
<b>Среднее АД:</b> {avg_systolic}/{avg_diastolic} мм рт.ст.
<b>Балл риска:</b> {risk_score}
<b>Уровень риска:</b> <b>{risk_level.upper()}</b>

{recommendations}

<b>Ваши данные очень помогли нашему исследованию.</b>

Небольшая просьба: если у вас есть друг или родственник, который тоже заботится о здоровье (или наоборот, вечно откладывает поход к врачу) — скиньте ему ссылку на прохождение чат-бота.

Для него это — быстрая самопроверка, для нас — важные данные. Будем очень благодарны!

<b>«За каждого друга, который пройдет опрос по Вашей рекомендации, мы вышлем Вам приятный и полезный подарок»</b>

Выберите подарок:"""
    
    # Если высокое давление или АГ, добавляем информацию о дневнике
    if bp_category in ["Высокое давление", "АГ"]:
        diary_text = "\n\n📝 <b>Дневник давления</b>\nРекомендуем измерять давление каждые 4 часа и записывать результаты."
        result_text = result_text.replace(recommendations, recommendations + diary_text)
    
    # Проверяем, есть ли у пользователя рефералы (приглашенные друзья)
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ? AND gift_claimed = 0",
            (user_id,)
        ) as cursor:
            has_referrals = (await cursor.fetchone())[0] > 0
        
        # Получаем реферальный код пользователя
        async with db.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            ref_code = row[0] if row else None
    
    # Обновляем последнее сообщение бота с результатами
    data = await state.get_data()
    current_message_id = data.get("current_message_id")
    
    # Всегда показываем выбор подарка после завершения опроса
    if current_message_id:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=current_message_id,
                text=result_text,
                reply_markup=get_gift_keyboard()
            )
        except:
            sent = await message.answer(result_text, reply_markup=get_gift_keyboard())
            await state.update_data(current_message_id=sent.message_id)
    else:
        sent = await message.answer(result_text, reply_markup=get_gift_keyboard())
        await state.update_data(current_message_id=sent.message_id)
    await state.set_state(SurveyStates.waiting_gift_choice)
    
    # Отправляем уведомление админам о прохождении опроса
    await notify_admins_about_survey(message.bot, user_id)


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
        
        # Получаем информацию о последнем опросе пользователя
        async with db.execute(
            """SELECT risk_level, risk_score, 
               (bp1_systolic + bp2_systolic + bp3_systolic) / 3 as avg_sys,
               (bp1_diastolic + bp2_diastolic + bp3_diastolic) / 3 as avg_dia
               FROM surveys WHERE user_id = ? ORDER BY completed_at DESC LIMIT 1""",
            (user_id,)
        ) as cursor:
            survey_row = await cursor.fetchone()
            if survey_row:
                risk_level = survey_row[0] or "не определен"
                risk_score = survey_row[1] or 0
                avg_systolic = int(survey_row[2] or 0)
                avg_diastolic = int(survey_row[3] or 0)
                
                # Определяем категорию АД
                bp_category = categorize_bp(avg_systolic, avg_diastolic)
                
                # Получаем рекомендации (упрощенная версия)
                recommendations = "Рекомендации сохранены в вашем профиле."
            else:
                risk_level = "не определен"
                risk_score = 0
                avg_systolic = 0
                avg_diastolic = 0
                bp_category = "не определено"
                recommendations = ""
        
        # Получаем реферальную ссылку
        async with db.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            ref_code = row[0] if row else None
        
        # После выбора подарка сразу показываем ссылку для приглашения
        result_text = f"""<b>📊 Результаты</b>

<b>Категория АД:</b> {bp_category}
<b>Среднее АД:</b> {avg_systolic}/{avg_diastolic} мм рт.ст.
<b>Балл риска:</b> {risk_score}
<b>Уровень риска:</b> <b>{risk_level.upper()}</b>

{recommendations}

<b>Ваши данные очень помогли нашему исследованию.</b>

Небольшая просьба: если у вас есть друг или родственник, который тоже заботится о здоровье (или наоборот, вечно откладывает поход к врачу) — скиньте ему ссылку на прохождение чат-бота.

Для него это — быстрая самопроверка, для нас — важные данные. Будем очень благодарны!

<b>«За каждого друга, который пройдет опрос по Вашей рекомендации, мы вышлем Вам приятный и полезный подарок»</b>

Вы выбрали подарок: <b>{gift_type}</b>
Мы свяжемся с Вами для отправки подарка."""
        
        if ref_code:
            bot_username = (await callback.message.bot.get_me()).username
            ref_link = f"https://t.me/{bot_username}?start={ref_code}"
            result_text += f"\n\n🔗 <b>Ваша реферальная ссылка:</b>\n{ref_link}\n\nПоделитесь ею с друзьями и получите подарок!"
        
        # Создаем клавиатуру с кнопками "Пригласить друга" и "Пройти тестирование ещё раз"
        final_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="invite_friend_after_survey")],
            [InlineKeyboardButton(text="🔄 Пройти тестирование ещё раз", callback_data="start_survey")]
        ])
        
        await callback.message.edit_text(result_text, reply_markup=final_keyboard)
    
    await state.clear()


# Обработчик кнопки "Пригласить друга" после выбора подарка
@router.callback_query(F.data == "invite_friend_after_survey")
async def invite_friend_after_survey(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    async with aiosqlite.connect(get_db_path()) as db:
        async with db.execute("SELECT referral_code FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            ref_code = row[0] if row else None
    
    if ref_code:
        bot_username = (await callback.message.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={ref_code}"
        # Создаем клавиатуру с кнопкой "Пройти тестирование ещё раз"
        restart_keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Пройти тестирование ещё раз", callback_data="start_survey")]
        ])
        
        await callback.message.edit_text(
            f"👥 <b>Пригласите друга!</b>\n\n"
            f"🔗 Ваша реферальная ссылка:\n{ref_link}\n\n"
            f"Поделитесь ею с друзьями и получите подарок за каждого, кто пройдет опрос!",
            reply_markup=restart_keyboard
        )
    else:
        await callback.answer("❌ Ошибка получения реферальной ссылки", show_alert=True)
