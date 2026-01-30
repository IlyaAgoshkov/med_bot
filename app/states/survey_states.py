from aiogram.fsm.state import State, StatesGroup


class SurveyStates(StatesGroup):
    # Главное меню
    main_menu = State()
    # Начало опроса
    waiting_consent = State()
    
    # Первое измерение АД
    waiting_bp1_instruction = State()
    waiting_bp1_values = State()
    waiting_bp1_time = State()
    
    # Демография
    waiting_age = State()
    waiting_gender = State()
    waiting_height = State()
    waiting_weight = State()
    waiting_education = State()
    waiting_financial_stability = State()
    
    # Образ жизни
    waiting_smoking = State()
    waiting_alcohol = State()
    waiting_salt = State()
    waiting_other_habits = State()
    waiting_screen_time = State()
    waiting_physical_activity = State()
    waiting_night_shifts = State()
    waiting_night_shifts_rate = State()
    
    # Второе измерение АД
    waiting_bp2_instruction = State()
    waiting_bp2_values = State()
    waiting_bp2_time = State()
    
    # Медицинская история
    waiting_chronic_diseases = State()
    waiting_medications = State()
    
    # Семейный анамнез
    waiting_family_history = State()
    
    # Психическое здоровье
    waiting_stress_level = State()
    waiting_sleep_quality = State()
    waiting_phq2_q1 = State()
    waiting_phq2_q2 = State()
    waiting_phq9 = State()
    
    # Третье измерение АД
    waiting_bp3_instruction = State()
    waiting_bp3_values = State()
    waiting_bp3_time = State()
    
    # Источник информации
    waiting_referral_source = State()
    
    # Выбор подарка
    waiting_gift_choice = State()
