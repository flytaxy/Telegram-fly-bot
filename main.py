import logging
import os
import json
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.enums import ParseMode, ContentType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import Command, StateFilter
from aiogram.fsm.state import StatesGroup, State
from aiogram.types.input_file import FSInputFile
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import requests
import asyncio

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
STATIC_MAPS_URL = "https://maps.googleapis.com/maps/api/staticmap"

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

USERS_DB = "users.json"
DRIVERS_DB = "drivers_rating.json"

class OrderTaxi(StatesGroup):
    waiting_for_location = State()
    waiting_for_address = State()
    waiting_for_tariff = State()
    waiting_for_confirmation = State()
    waiting_for_rating = State()

TARIFFS = {
    "🚗 Стандарт": {"start_price": 100, "per_km": 20},
    "🚙 Комфорт": {"start_price": 130, "per_km": 23},
    "🚘 Бізнес": {"start_price": 170, "per_km": 27},
}

PEAK_HOURS = [(5, 6), (7.5, 11), (16.5, 19.5), (21.5, 24)]

def is_peak_hour():
    now = datetime.now(ZoneInfo("Europe/Kyiv"))
    hour = now.hour + now.minute / 60
    return any(start <= hour < end for start, end in PEAK_HOURS)

def is_curfew():
    return 0 <= datetime.now(ZoneInfo("Europe/Kyiv")).hour < 5

def save_user(user):
    if not os.path.exists(USERS_DB):
        with open(USERS_DB, "w") as f:
            json.dump({}, f)
    with open(USERS_DB) as f:
        users = json.load(f)
    if str(user.id) not in users:
        users[str(user.id)] = {"name": user.full_name, "username": user.username}
        with open(USERS_DB, "w") as f:
            json.dump(users, f)

def update_driver_rating(driver_id: str, score: int):
    if not os.path.exists(DRIVERS_DB):
        with open(DRIVERS_DB, "w") as f:
            json.dump({}, f)
    with open(DRIVERS_DB) as f:
        data = json.load(f)
    if driver_id not in data:
        data[driver_id] = {"score_sum": 0, "trips": 0, "history": []}
    data[driver_id]["score_sum"] += score
    data[driver_id]["trips"] += 1
    data[driver_id]["history"].append(score)
    if len(data[driver_id]["history"]) > 100:
        removed = data[driver_id]["history"].pop(0)
        data[driver_id]["score_sum"] -= removed
    with open(DRIVERS_DB, "w") as f:
        json.dump(data, f)

@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    save_user(message.from_user)
    if is_curfew():
        await message.answer("⛔️ Сервіс тимчасово недоступний через комендантську годину (00:00 – 05:00).")
        return
    await message.answer(
        "👋 Вас вітає таксі Fly!

Надішліть вашу геолокацію для початку замовлення:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="📍 Надіслати локацію", request_location=True)]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(OrderTaxi.waiting_for_location)

@dp.message(F.location, StateFilter(OrderTaxi.waiting_for_location))
async def location_received(message: Message, state: FSMContext):
    await state.update_data(location=message.location)
    await message.answer("📨 Тепер надішліть, будь ласка, адресу призначення:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(OrderTaxi.waiting_for_address)

@dp.message(StateFilter(OrderTaxi.waiting_for_address))
async def address_received(message: Message, state: FSMContext):
    data = await state.get_data()
    origin = data["location"]
    address = message.text
    await state.update_data(address=address)

    geo_url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_MAPS_API_KEY}"
    geo_response = requests.get(geo_url).json()
    if not geo_response["results"]:
        await message.answer("❌ Не вдалося знайти адресу. Спробуйте ще раз.")
        return
    dest_location = geo_response["results"][0]["geometry"]["location"]
    end_coords = (dest_location["lat"], dest_location["lng"])
    await state.update_data(end_coords=end_coords)

    directions_url = (
        f"https://maps.googleapis.com/maps/api/directions/json?"
        f"origin={origin.latitude},{origin.longitude}&destination={end_coords[0]},{end_coords[1]}"
        f"&mode=driving&key={GOOGLE_MAPS_API_KEY}"
    )
    route_response = requests.get(directions_url).json()
    if route_response["status"] != "OK":
        await message.answer("❌ Не вдалося побудувати маршрут.")
        return
    route = route_response["routes"][0]["legs"][0]
    distance_km = round(route["distance"]["value"] / 1000, 1)
    duration_min = int(route["duration"]["value"] / 60)
    await state.update_data(distance_km=distance_km, duration_min=duration_min)

    map_url = (
        f"{STATIC_MAPS_URL}?size=600x400&path=color:0x0000ff|weight:5|"
        f"{origin.latitude},{origin.longitude}|{end_coords[0]},{end_coords[1]}"
        f"&markers=color:green|label:A|{origin.latitude},{origin.longitude}"
        f"&markers=color:red|label:B|{end_coords[0]},{end_coords[1]}"
        f"&key={GOOGLE_MAPS_API_KEY}"
    )
    with open("route_map.png", "wb") as f:
        f.write(requests.get(map_url).content)
    await message.answer_photo(FSInputFile("route_map.png"))

    peak = is_peak_hour()
    markup = ReplyKeyboardBuilder()
    for key, tariff in TARIFFS.items():
        total = tariff["start_price"]
        if distance_km > 2:
            total += (distance_km - 2) * tariff["per_km"]
        if peak:
            total = int(total * 1.3)
        markup.add(KeyboardButton(text=f"{key} – {int(total)}₴"))
    markup.adjust(1)

    await message.answer(
        f"🗺 Маршрут побудовано!

📍 Відстань: {distance_km} км
🕓 Час у дорозі: {duration_min} хв

🚘 Оберіть клас авто:",
        reply_markup=markup.as_markup(resize_keyboard=True),
    )
    await state.set_state(OrderTaxi.waiting_for_tariff)

@dp.message(StateFilter(OrderTaxi.waiting_for_tariff))
async def tariff_chosen(message: Message, state: FSMContext):
    await state.update_data(selected_tariff=message.text)
    await message.answer(
        f"🔔 Ви обрали: {message.text}

Натисніть «✅ Підтвердити замовлення», щоб завершити.",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="✅ Підтвердити замовлення")]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(OrderTaxi.waiting_for_confirmation)

@dp.message(StateFilter(OrderTaxi.waiting_for_confirmation), F.text == "✅ Підтвердити замовлення")
async def confirm_order(message: Message, state: FSMContext):
    await message.answer(
        "✅ Ваше замовлення підтверджено! Очікуйте авто.

Після завершення поїздки, будь ласка, оцініть водія (1–5):",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=str(i)) for i in range(1, 6)]],
            resize_keyboard=True,
        ),
    )
    await state.set_state(OrderTaxi.waiting_for_rating)

@dp.message(StateFilter(OrderTaxi.waiting_for_rating), F.text.in_(["1", "2", "3", "4", "5"]))
async def receive_rating(message: Message, state: FSMContext):
    rating = int(message.text)
    update_driver_rating("driver_1", rating)
    await message.answer("⭐️ Дякуємо за оцінку!", reply_markup=ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔄 Перезапустити")]],
        resize_keyboard=True,
    ))
    await state.clear()

# 🔁 Головний блок запуску бота
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
