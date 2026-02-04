from typing import Dict, Tuple


def calculate_bmi(weight: float, height: int) -> float:
    """Расчет индекса массы тела"""
    height_m = height / 100
    return round(weight / (height_m ** 2), 2)


def calculate_risk_score(survey_data: Dict) -> int:
    """Расчет балла риска на основе данных опроса согласно ТЗ"""
    score = 0
    
    # 1. Первое измерение АД - 0 баллов (категория определяется отдельно)
    
    # 2. Пол
    if survey_data.get("gender") == "мужской":
        score += 1  # Мужской - 1 балл
    # Женский - 0 баллов
    
    # 3. ИМТ
    bmi = survey_data.get("bmi", 0)
    if bmi < 25:
        score += 0  # <25 - 0 баллов
    elif 25 <= bmi <= 29.9:
        score += 1  # 25-29.9 - 1 балл
    elif bmi > 30:
        score += 2  # >30 - 2 балла
    
    # 4. Финансовая стабильность
    financial = survey_data.get("financial_stability", "")
    if financial == "низкая":
        score += 1  # Низкая - 1 балл
    # Средняя/высокая - 0 баллов
    
    # 5. Курение
    if survey_data.get("smoking"):
        score += 3  # Курение - 3 балла
    
    # 6. Алкоголь
    alcohol = survey_data.get("alcohol_per_week", 0)
    if alcohol > 0:
        score += 2  # Алкоголь - 2 балла
    
    # 7. Соль > 2 чайных ложек (14г)
    salt = survey_data.get("salt_per_day", 0)
    if salt > 14:
        score += 3  # Соль > 14г - 3 балла
    
    # 8. Энергетики (другие вредные привычки)
    if survey_data.get("other_habits"):
        score += 1  # Энергетики - 1 балл
    
    # 9. Время за экраном
    screen_time = survey_data.get("screen_time", 0)
    if screen_time > 0:
        score += 1  # Время за экраном - 1 балл
    
    # 10. Физическая активность
    if not survey_data.get("physical_activity"):
        score += 1  # Нет физической активности - 1 балл
    # Да - 0 баллов
    
    # 11. Ночные дежурства
    if survey_data.get("night_shifts"):
        night_shifts_rate = survey_data.get("night_shifts_rate", "")
        if night_shifts_rate == "> 1 ставки":
            score += 1  # > 1 ставки - 1 балл
        # < 1 ставки и = 1 ставки - 0 баллов
    
    # 12. Второе измерение АД - 0 баллов (категория определяется отдельно)
    
    # 13. Хронические заболевания
    diseases = survey_data.get("chronic_diseases", "")
    if diseases and diseases != "нет":
        score += 3  # Хронические заболевания - 3 балла
    
    # 14. Лекарства постоянно
    if survey_data.get("medications"):
        score += 1  # Лекарства постоянно - 1 балл
    
    # 15. Семейный анамнез
    if survey_data.get("family_history"):
        score += 3  # Семейный анамнез - 3 балла
    
    # 16. Стресс >7
    stress = survey_data.get("stress_level", 0)
    if stress > 7:
        score += 2  # Стресс >7 - 2 балла
    
    # 17. Сон <5
    sleep = survey_data.get("sleep_quality", 0)
    if sleep < 5:
        score += 2  # Сон <5 - 2 балла
    
    # 18. PHQ-9
    phq9 = survey_data.get("phq9_score", 0)
    if phq9 <= 4:
        score += 0  # <=4 - 0 баллов
    elif 5 <= phq9 <= 14:
        score += 1  # 5-14 - 1 балл
    elif 15 <= phq9 <= 19:
        score += 2  # 15-19 - 2 балла
    elif 20 <= phq9 <= 27:
        score += 3  # 20-27 - 3 балла
    
    # 19. Третье измерение АД - 0 баллов (категория определяется отдельно)
    
    return score


def get_risk_level(bp_category: str, risk_score: int) -> str:
    """Определение уровня риска на основе категории АД и балла риска согласно ТЗ"""
    if bp_category == "Оптимальное давление":
        if risk_score <= 9:
            return "низкий"
        elif 10 <= risk_score <= 18:
            return "низкий"
        else:  # 19-27
            return "умеренный"
    
    elif bp_category == "Нормальное давление":
        if risk_score <= 9:
            return "низкий"
        elif 10 <= risk_score <= 18:
            return "низкий"
        else:  # 19-27
            return "умеренный"
    
    elif bp_category == "Высокое нормальное давление":
        # Согласно ТЗ: 0-9 и 10-18 - низкий риск, 19-27 - умеренный риск
        if risk_score <= 9:
            return "низкий"
        elif 10 <= risk_score <= 18:
            return "низкий"
        else:  # 19-27
            return "умеренный"
    
    elif bp_category == "Высокое давление":
        # Согласно ТЗ: 0-9 и 10-18 - умеренный риск, 19-27 - высокий риск
        if risk_score <= 9:
            return "умеренный"
        elif 10 <= risk_score <= 18:
            return "умеренный"
        else:  # 19-27
            return "высокий"
    
    elif bp_category == "АГ":
        return "высокий"  # Всегда высокий риск
    
    return "низкий"


def categorize_bp(systolic: int, diastolic: int) -> str:
    """Категоризация артериального давления согласно ТЗ"""
    # Оптимальное: <120/<80
    if systolic < 120 and diastolic < 80:
        return "Оптимальное давление"
    
    # Нормальное: 120-129/80-84
    if 120 <= systolic <= 129 and 80 <= diastolic <= 84:
        return "Нормальное давление"
    
    # Высокое нормальное: 130-139/85-89
    if 130 <= systolic <= 139 and 85 <= diastolic <= 89:
        return "Высокое нормальное давление"
    
    # Высокое давление (АГ по измерениям): ≥140/≥90
    if systolic >= 140 or diastolic >= 90:
        return "Высокое давление"
    
    # Граничные случаи
    # Если систолическое в норме, но диастолическое выше
    if systolic < 120:
        if diastolic < 80:
            return "Оптимальное давление"
        elif diastolic <= 84:
            return "Нормальное давление"
        elif diastolic <= 89:
            return "Высокое нормальное давление"
        else:
            return "АГ"
    
    # Если диастолическое в норме, но систолическое выше
    if diastolic < 80:
        if systolic < 120:
            return "Оптимальное давление"
        elif systolic <= 129:
            return "Нормальное давление"
        elif systolic <= 139:
            return "Высокое нормальное давление"
        else:
            return "АГ"
    
    # По умолчанию
    return "Нормальное давление"


def get_bp_recommendation(bp_category: str) -> str:
    """Рекомендация на основе категории АД"""
    if bp_category == "Оптимальное давление":
        return "Продолжайте поддерживать здоровый образ жизни."
    elif bp_category == "Нормальное давление":
        return "Продолжайте поддерживать здоровый образ жизни."
    elif bp_category == "Высокое нормальное давление":
        return "Вам следует скорректировать свой образ жизни. Измеряйте АД 1-2 раза в неделю. Рекомендуем проконсультироваться с терапевтом для оценки общего риска."
    elif bp_category == "Высокое давление":
        return "Обратитесь к терапевту или кардиологу в ближайшее время для подтверждения диагноза и выявления причин."
    elif bp_category == "АГ":
        return "Обратитесь к терапевту или кардиологу в ближайшее время для подтверждения диагноза и выявления причин."
    return ""


def get_risk_level_recommendation(risk_level: str) -> str:
    """Базовая рекомендация на основе уровня риска"""
    if risk_level == "низкий":
        return "Отличный результат, вы ответственно подходите к своему здоровью! Практически отсутствуют факторы, ведущие к повышению давления. Следите за питанием и стремитесь оставаться физически активными - это вклад в ваше здоровое будущее. Будьте мотиватором и примером для друзей и близких."
    elif risk_level == "умеренный":
        return "Выявлены факторы риска, но поводов для переживаний нет. Необходимо уже сейчас начать действовать и скорректировать образ жизни."
    elif risk_level == "высокий":
        return "Комбинация ваших факторов создает высокую вероятность развития артериальной гипертензии в ближайшие годы. Это серьезный повод не откладывать визит к врачу и скорректировать образ жизни."
    return ""


def get_phq_recommendation(phq9_score: int) -> str:
    """Рекомендация на основе PHQ-9"""
    if phq9_score <= 4:
        return "Отсутствие или минимальный уровень депрессии"
    elif 5 <= phq9_score <= 9:
        return "Легкая депрессия, рекомендована консультация психолога"
    elif 10 <= phq9_score <= 14:
        return "Умеренная депрессия, рекомендована консультация психолога, психотерапевта"
    elif 15 <= phq9_score <= 19:
        return "Тяжелая депрессия, необходима консультация психотерапевта, психиатра"
    elif 20 <= phq9_score <= 27:
        return "Крайне тяжелая депрессия, необходима срочная консультация психиатра"
    return ""


def get_recommendations(bp_category: str, risk_level: str, survey_data: Dict) -> str:
    """Генерация персонализированных рекомендаций согласно ТЗ"""
    recommendations = []
    
    # Начинаем с рекомендации по уровню риска
    risk_rec = get_risk_level_recommendation(risk_level)
    if risk_rec:
        recommendations.append(f"<b>Уровень риска: {risk_level.upper()}</b>")
        recommendations.append(risk_rec)
    
    # Рекомендация по АД
    bp_rec = get_bp_recommendation(bp_category)
    if bp_rec:
        recommendations.append(f"\n<b>По результатам измерения АД:</b>\n{bp_rec}")
    
    # Рекомендации по факторам риска
    factor_recommendations = []
    
    # ИМТ
    bmi = survey_data.get("bmi", 0)
    if bmi >= 25:
        factor_recommendations.append("📊 <b>ИМТ:</b> Следите за питанием: упор на овощи, фрукты, цельнозерновые, рыбу, бобовые, нежирные молочные продукты, рекомендуем ограничить потребление сахара. Не переедайте, лишний вес нужно постепенно скинуть.")
    
    # Курение и алкоголь
    if survey_data.get("smoking") or survey_data.get("alcohol_per_week", 0) > 0:
        factor_recommendations.append("🚭🍷 <b>Вредные привычки:</b> Откажитесь от вредных привычек, они не стоят Вашего здоровья!")
    
    # Соль
    salt = survey_data.get("salt_per_day", 0)
    if salt > 14:
        factor_recommendations.append("🧂 <b>Соль:</b> Необходимо снизить количество употребляемой соли, в день не более 5 г (учитывайте, что в чайной ложке без горки содержится примерно 7 г соли!).")
    
    # Энергетики
    if survey_data.get("other_habits"):
        factor_recommendations.append("⚡ <b>Энергетики:</b> Откажитесь от энергетиков. Они не дают энергию, а вынуждают организм работать в экстренном режиме, выжимая последние силы, что ведёт к ещё большей усталости, истощению нервной системы и рискам для сердечно-сосудистой системы.")
    
    # Время за экраном (показываем рекомендацию только если это фактор риска)
    screen_time = survey_data.get("screen_time", 0)
    if screen_time > 0:
        factor_recommendations.append("📱 <b>Время за экраном:</b> Старайтесь меньше времени проводить за экраном.")
    
    # Физическая активность
    if not survey_data.get("physical_activity"):
        factor_recommendations.append("🏃 <b>Физическая активность:</b> Физическая активность – залог здоровья! Больше двигайтесь, гуляйте каждый день 30-60 мин, катайтесь на велосипеде, занимайтесь гимнастикой, выберите физически активное хобби (например, танцы).")
    
    # Стресс
    stress = survey_data.get("stress_level", 0)
    if stress > 7:
        factor_recommendations.append("🧘 <b>Стресс:</b> Для снижения уровня стресса попробуйте планировать свои дни, правильно расставлять приоритеты и говорить «нет» второстепенному. Не забывайте про отдых, ограничьте времяпрепровождения в соцсетях, медитируйте, ходите на массаж, займитесь плаванием или придумайте свои вечерние ритуалы для расслабления.")
    
    # Сон
    sleep = survey_data.get("sleep_quality", 0)
    if sleep < 5:
        factor_recommendations.append("😴 <b>Сон:</b> Постарайтесь наладить режим сна, спите по 7-9 ч регулярно в полной темноте и тишине.")
    
    # PHQ-9
    phq9 = survey_data.get("phq9_score", 0)
    if phq9 > 4:
        phq_rec = get_phq_recommendation(phq9)
        if phq_rec:
            factor_recommendations.append(f"💭 <b>Психическое здоровье (PHQ-9):</b> {phq_rec}")
    
    # Добавляем рекомендации по факторам
    if factor_recommendations:
        recommendations.append("\n<b>Рекомендации по выявленным факторам риска:</b>")
        recommendations.extend(factor_recommendations)
    
    # Завершающая фраза
    recommendations.append("\n💪 У вас все получится, позаботьтесь о себе!")
    
    return "\n".join(recommendations)
