import secrets
import string


def generate_referral_code(user_id: int) -> str:
    """Генерация уникального реферального кода"""
    # Используем часть user_id + случайные символы
    alphabet = string.ascii_uppercase + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(6))
    return f"REF{user_id}{random_part}"
