from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_yes_no_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура Да/Нет"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data="yes")],
        [InlineKeyboardButton(text="❌ Нет", callback_data="no")]
    ])
    return keyboard


def get_gender_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора пола"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨 Мужской", callback_data="gender_male")],
        [InlineKeyboardButton(text="👩 Женский", callback_data="gender_female")]
    ])
    return keyboard


def get_education_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора образования"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Среднее общее", callback_data="edu_secondary")],
        [InlineKeyboardButton(text="Среднее профессиональное", callback_data="edu_professional")],
        [InlineKeyboardButton(text="Неполное высшее", callback_data="edu_incomplete_higher")],
        [InlineKeyboardButton(text="Высшее", callback_data="edu_higher")]
    ])
    return keyboard


def get_financial_stability_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура финансовой стабильности"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Низкая", callback_data="finance_low")],
        [InlineKeyboardButton(text="Средняя", callback_data="finance_medium")],
        [InlineKeyboardButton(text="Высокая", callback_data="finance_high")]
    ])
    return keyboard


def get_night_shifts_rate_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура ставки ночных дежурств"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=">= 1 ставки", callback_data="shift_more")],
        [InlineKeyboardButton(text="= 1 ставки", callback_data="shift_equal")],
        [InlineKeyboardButton(text="<= 1 ставки", callback_data="shift_less")]
    ])
    return keyboard


def get_chronic_diseases_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура хронических заболеваний"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Нет", callback_data="disease_none")],
        [InlineKeyboardButton(text="Артериальная гипертензия", callback_data="disease_hypertension")],
        [InlineKeyboardButton(text="Сахарный диабет", callback_data="disease_diabetes")],
        [InlineKeyboardButton(text="Инфаркт/Инсульт", callback_data="disease_heart")],
        [InlineKeyboardButton(text="Гипертиреоз/Гипотиреоз", callback_data="disease_thyroid")],
        [InlineKeyboardButton(text="Хроническая болезнь почек", callback_data="disease_kidney")],
        [InlineKeyboardButton(text="Другое (напишу сам/а)", callback_data="disease_other")]
    ])
    return keyboard


def get_phq_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для PHQ опросника"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Ни разу", callback_data="phq_0")],
        [InlineKeyboardButton(text="Несколько дней", callback_data="phq_1")],
        [InlineKeyboardButton(text="Более половины времени", callback_data="phq_2")],
        [InlineKeyboardButton(text="Почти каждый день", callback_data="phq_3")]
    ])
    return keyboard


def get_referral_source_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура источника информации"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="На кафедре госпитальной терапии", callback_data="source_department")],
        [InlineKeyboardButton(text="Посоветовали друзья", callback_data="source_friends")],
        [InlineKeyboardButton(text="Посоветовали родственники", callback_data="source_family")],
        [InlineKeyboardButton(text="Свой вариант", callback_data="source_other")]
    ])
    return keyboard


def get_gift_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора подарка"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Питание", callback_data="gift_nutrition")],
        [InlineKeyboardButton(text="🏃 Физическая активность", callback_data="gift_activity")],
        [InlineKeyboardButton(text="🧘 Стресс", callback_data="gift_stress")]
    ])
    return keyboard


def get_invite_friend_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой пригласить друга"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Пригласить друга", callback_data="invite_friend_after_survey")]
    ])
    return keyboard


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главное меню бота (второй экран — перед опросом)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Начать опрос", callback_data="start_survey")]
    ])
    return keyboard


def get_start_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура для стартового сообщения (кнопка «Начать»)"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Начать", callback_data="welcome_start")]
    ])
    return keyboard


def get_restart_survey_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой пройти тестирование ещё раз"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Пройти тестирование ещё раз", callback_data="start_survey")]
    ])
    return keyboard


def get_cancel_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой отмены"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_survey")]
    ])
    return keyboard


def get_back_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопкой назад"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back")]
    ])
    return keyboard


def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура админ-панели"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="📥 Выгрузить результаты", callback_data="admin_export")]
    ])
    return keyboard
