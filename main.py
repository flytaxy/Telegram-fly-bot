import os
import logging
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    Message,
    FSInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, StateFilter
from dotenv import load_dotenv
from aiogram import F
from cd import calculate_price  # Імпорт розрахунку ціни

# Завантаження .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Ініціалізація бота
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

logging.basicConfig(level=logging.INFO)


# Стан
class RideStates(StatesGroup):
    waiting_for_location = State()
    waiting_for_address = State()
    waiting_for_car_class = State()


# Команда /start
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Надіслати локацію", request_location=True)]],
        resize_keyboard=True,
    )
    await message.answer(
        "Привіт! Надішли свою локацію для початку замовлення:", reply_markup=kb
    )
    await state.set_state(RideStates.waiting_for_location)


# Отримання локації
@dp.message(RideStates.waiting_for_location, F.location)
async def handle_location(message: Message, state: FSMContext):
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(start_coords=(lat, lon))
    await message.answer(
        "Тепер введи адресу призначення (наприклад: Заболотного 4, Київ):",
        reply_markup=types.ReplyKeyboardRemove(),
    )
    await state.set_state(RideStates.waiting_for_address)


# Функція геокодування
def geocode_address(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(url, params=params)
    data = response.json()
    if data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return (location["lat"], location["lng"])
    return None


# Отримання адреси
@dp.message(RideStates.waiting_for_address)
async def handle_address(message: Message, state: FSMContext):
    destination_address = message.text
    end_coords = geocode_address(destination_address)
    if not end_coords:
        await message.answer("❌ Не вдалося знайти адресу. Спробуй ще раз.")
        return
    await state.update_data(end_coords=end_coords)
    # Вибір класу авто
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚗 Економ", callback_data="class_Економ")],
            [InlineKeyboardButton(text="🚘 Комфорт", callback_data="class_Комфорт")],
            [InlineKeyboardButton(text="🚖 Бізнес", callback_data="class_Бізнес")],
        ]
    )
    await message.answer("Оберіть клас авто:", reply_markup=kb)
    await state.set_state(RideStates.waiting_for_car_class)


# Обробка вибору класу авто
@dp.callback_query(RideStates.waiting_for_car_class)
async def process_car_class(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    car_class = callback.data.split("_")[1]
    user_data = await state.get_data()
    start_coords = user_data.get("start_coords")
    end_coords = user_data.get("end_coords")

    # Directions API
    directions_url = "https://maps.googleapis.com/maps/api/directions/json"
    directions_params = {
        "origin": f"{start_coords[0]},{start_coords[1]}",
        "destination": f"{end_coords[0]},{end_coords[1]}",
        "mode": "driving",
        "key": GOOGLE_MAPS_API_KEY,
    }
    directions_response = requests.get(directions_url, params=directions_params)
    directions_data = directions_response.json()

    if directions_data["status"] != "OK":
        await callback.message.answer("❌ Не вдалося побудувати маршрут.")
        return

    route = directions_data["routes"][0]["legs"][0]
    distance_text = route["distance"]["text"]
    duration_text = route["duration"]["text"]
    distance_km = float(route["distance"]["value"]) / 1000  # метри → км

    price = calculate_price(car_class, distance_km)

    # Static Maps API (з полілайном)
    static_map_url = "https://maps.googleapis.com/maps/api/staticmap"
    static_map_params = {
        "size": "600x400",
        "path": f"enc:{directions_data['routes'][0]['overview_polyline']['points']}",
        "markers": f"color:green|label:A|{start_coords[0]},{start_coords[1]}&markers=color:red|label:B|{end_coords[0]},{end_coords[1]}",
        "key": GOOGLE_MAPS_API_KEY,
    }

    map_response = requests.get(static_map_url, params=static_map_params)

    # Збереження зображення
    with open("route_map.png", "wb") as f:
        f.write(map_response.content)

    # Надсилання зображення та деталей
    if os.path.exists("route_map.png"):
        photo = FSInputFile("route_map.png")
        await callback.message.answer_photo(photo)
        await callback.message.answer(
            f"🟢 Маршрут побудовано!"
            f"📍 Відстань: {distance_text}"
            f"🕒 Тривалість: {duration_text}"
            f"🚗 Клас авто: {car_class}"
            f"💸 Вартість поїздки: {price}₴"
        )
    else:
        await callback.message.answer("❌ Не вдалося зберегти карту.")


# Запуск
if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
