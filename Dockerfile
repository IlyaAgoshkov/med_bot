FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей системы (если понадобятся)
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Копирование файлов зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директории для базы данных
RUN mkdir -p /app/data && chmod 755 /app/data

# Запуск бота
CMD ["python", "main.py"]
