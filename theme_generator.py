import random
import asyncio
from groq import Groq

# === Резервные темы (как на твоих скринах) ===
BACKUP_THEMES = [
    "ЛЕЗВИЕ", "ПРОСТОР", "ПЛАТФОРМА", "СЕТЬ", "ПУТЬ", "СИСТЕМА",
    "РЯБЬ", "ПОЛЁТ", "УВЯДАНИЕ", "ГРАНИЦА", "ЭХО", "ПУЛЬС",
    "ОТРАЖЕНИЕ", "ТЕНЬ", "СВЕТ", "ПОКОЙ", "ДВИЖЕНИЕ", "ПУСТОТА",
    "ЗВУК", "СТЕКЛО", "ВОЛНА", "СЛЕД", "МИР", "РАЗРЫВ"
]

# === АКТУАЛЬНАЯ МОДЕЛЬ ===
GROQ_API_KEY = "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"
MODEL = "llama-3.1-8b-instant"  # ✅ Работает в 2025 году

current_theme = None
last_theme_timestamp = None

client = Groq(api_key=GROQ_API_KEY)

async def generate_weekly_theme():
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
        word = word.replace('"', '').replace("'", "").replace('.', '').replace(',', '').strip().upper()
        if word and len(word) > 1 and len(word) < 20:
            current_theme = word
        else:
            raise ValueError("Некорректный ответ")
    except Exception as e:
        print(f"[Theme] Groq недоступен или ошибка: {e}. Использую резервную тему.")
        current_theme = random.choice(BACKUP_THEMES)

    last_theme_timestamp = asyncio.get_event_loop().time()
    return current_theme

def get_current_theme():
    return current_theme

def should_generate_new_theme():
    if last_theme_timestamp is None:
        return True
    now = asyncio.get_event_loop().time()
    return (now - last_theme_timestamp) >= 7 * 24 * 3600
