import os
import logging
import openrouteservice
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
import asyncio

# Завантаження змінних середовища
load_dotenv()
ORS_API_KEY = os.getenv("ORS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
user_locations = {}

# Хендлер /start
@dp.message(Command("start"))
async def send_welcome(message: Message):
    location_button = KeyboardButton(
        text="📍 Надіслати локацію",
        request_location=True
    )
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[location_button]],
        resize_keyboard=True
    )
    await message.answer(
        "Привіт! Надішли свою локацію, щоб викликати таксі 🚕",
        reply_markup=keyboard
    )

# Хендлер локації
@dp.message(lambda message: message.location is not None)
async def handle_location(message: Message):
    lat = message.location.latitude
    lon = message.location.longitude
    user_locations[message.from_user.id] = (lat, lon)
    await message.answer("Локацію отримано ✅\nТепер введи адресу призначення 🏁")

# Хендлер адреси
@dp.message()
async def handle_destination(message: Message):
    user_id = message.from_user.id
    if user_id not in user_locations:
        await message.answer("Спочатку надішліть свою локацію 📍")
        return

    client = openrouteservice.Client(key=ORS_API_KEY)

    try:
        # Геокодуємо адресу
        geocode = client.pelias_search(text=message.text)

        if not geocode['features']:
            await message.answer("Не вдалося знайти адресу. Спробуй ще раз 🧐")
            return

        dest_coords = geocode['features'][0]['geometry']['coordinates']  # [lon, lat]

        if not isinstance(dest_coords, list) or len(dest_coords) != 2:
            await message.answer("Координати адреси некоректні 😕")
            return

        start_coords = [user_locations[user_id][1], user_locations[user_id][0]]  # [lon, lat]
        coords = [start_coords, dest_coords]

        # Побудова маршруту
        route = client.directions(coords, profile='driving-car', format='geojson')
        distance = route['features'][0]['properties']['summary']['distance'] / 1000

        await message.answer(f"Довжина маршруту: {distance:.2f} км 🚗")

    except Exception as e:
        await message.answer(f"Помилка побудови маршруту 😓:\n{e}")

# Запуск бота
async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())