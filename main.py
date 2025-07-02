from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
import logging
from dotenv import load_dotenv
import os
import openrouteservice

# Завантаження змінних з .env
load_dotenv()

ORS_API_KEY = os.getenv("ORS_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)
user_locations = {}

# Увімкнення логування
logging.basicConfig(level=logging.INFO)

# Обробка команди /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    location_button = KeyboardButton(text="📍 Надіслати локацію", request_location=True)
    keyboard.add(location_button)

    await message.answer(
        "Привіт! Надішли свою локацію, щоб викликати таксі 🚖📍",
        reply_markup=keyboard
    )

# Обробка отриманої локації
@dp.message_handler(content_types=types.ContentType.LOCATION)
async def handle_location(message: types.Message):
    user_id = message.from_user.id
    latitude = message.location.latitude
    longitude = message.location.longitude

    user_locations[user_id] = {"lat": latitude, "lon": longitude}

    await message.answer(
        f"📍Ми отримали твою локацію:\n🔽 Широта: {latitude}\n🔼 Довгота: {longitude}\n\n"
        "Тепер надішли адресу, куди їхати 🏁",
        reply_markup=types.ReplyKeyboardRemove()
    )

# Обробка введеної адреси призначення
@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_destination(message: types.Message):
    user_id = message.from_user.id
    destination = message.text

    if user_id not in user_locations:
        await message.answer("Спочатку надішліть свою локацію 📍")
        return

    start = user_locations[user_id]

    await message.answer(f"📍Пункт призначення: {destination}\n\nОчікуйте авто, скоро приїде! 😊")

    # Побудова маршруту
    def get_route(start_coords, end_coords):
        client = openrouteservice.Client(key=ORS_API_KEY)
        route = client.directions(
            coordinates=[start_coords, end_coords],
            profile='driving-car',
            format='geojson'
        )
        return route

    # Тут буде виклик OpenRouteService API — пізніше додамо геокодування
    # Поки що просто виводимо початкову точку
    await message.answer(
        f"📌 Ваш маршрут:\n🟢 Початкова точка: {start['lat']}, {start['lon']}\n"
        f"🏁 Пункт призначення: {destination}"
    )

# Запуск бота
if name == "main":
    executor.start_polling(dp, skip_updates=True)