import asyncio
from groq import Groq

# === Настройки ===
GROQ_API_KEY = "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"
MODEL = "llama3-8b-8192"

# === Глобальное состояние ===
current_theme = None
last_theme_timestamp = None  # время последней генерации (в секундах)

client = Groq(api_key=GROQ_API_KEY)

async def generate_weekly_theme():
    """Генерирует одно слово-тему через Groq"""
    global current_theme, last_theme_timestamp

    prompt = """
Ты — художественный директор. Твоя задача — сгенерировать **одно слово**, которое может вдохновить на создание визуального контента (картинки, фото, арт).

Слово должно быть:
- Абстрактным или метафоричным
- Нейтральным по смыслу
- Подходящим для визуализации
- Не слишком банальным

Примеры: лезвие, простор, платформа, сеть, путь, система, рябь, полёт, увядание

Сгенерируй только одно слово. Без объяснений. Без пунктов. Без кавычек.
"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL,
            temperature=0.7,
            max_tokens=10,
            stream=False
        )
        word = response.choices[0].message.content.strip()
        # Очистка от лишних символов
        word = word.replace('"', '').replace("'", "").replace('.', '').replace(',', '').strip()
        current_theme = word.upper()
        last_theme_timestamp = asyncio.get_event_loop().time()
        return current_theme
    except Exception as e:
        print(f"[Theme] Ошибка Groq: {e}")
        return "ТЕМА"

def get_current_theme():
    return current_theme

def should_generate_new_theme():
    """Проверяет, прошло ли 7 дней с последней генерации"""
    if last_theme_timestamp is None:
        return True
    now = asyncio.get_event_loop().time()
    return (now - last_theme_timestamp) >= 7 * 24 * 3600  # 7 дней в секундах