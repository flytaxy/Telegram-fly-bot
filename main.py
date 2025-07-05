import os
import json
import logging
import requests
from datetime import datetime, time
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
from aiogram.filters import CommandStart
from aiogram import F
from cd import calculate_price
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


class RideStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_location = State()
    waiting_for_address = State()
    waiting_for_car_class = State()
    waiting_for_confirmation = State()
    waiting_for_rating = State()
    waiting_for_address_change = State()


def is_peak_time():
    now = datetime.now(ZoneInfo("Europe/Kyiv")).time()
    peak_periods = [
        (time(5, 0), time(6, 0)),
        (time(7, 30), time(11, 0)),
        (time(16, 30), time(19, 30)),
        (time(21, 30), time(23, 59, 59)),
    ]
    return any(start <= now <= end for start, end in peak_periods)


def is_restricted_time():
    now = datetime.now(ZoneInfo("Europe/Kyiv")).time()
    return time(0, 0) <= now < time(5, 0)


def load_users():
    if not os.path.exists("users.json"):
        return {}
    with open("users.json", "r") as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)


def save_user(user_id, data):
    users = load_users()
    users[str(user_id)] = data
    with open("users.json", "w") as f:
        json.dump(users, f, indent=4)


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    if is_restricted_time():
        await message.answer(
            "🚫 Сервіс тимчасово недоступний з 00:00 до 05:00 у зв'язку з комендантською годиною."
        )
        return

    await message.answer("👋 Привіт, тебе вітає TaxiFly!")

    users = load_users()
    user_id = str(message.from_user.id)
    if user_id in users:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📍 Надіслати локацію", request_location=True)]
            ],
            resize_keyboard=True,
        )
        await message.answer("Надішліть свою локацію:", reply_markup=kb)
        await state.set_state(RideStates.waiting_for_location)
    else:
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="📱 Надіслати номер телефону", request_contact=True
                    )
                ]
            ],
            resize_keyboard=True,
        )
        await message.answer(
            "Для початку, надішліть свій номер телефону:", reply_markup=kb
        )
        await state.set_state(RideStates.waiting_for_phone)


@dp.message(RideStates.waiting_for_phone, F.contact)
async def handle_phone(message: Message, state: FSMContext):
    contact = message.contact
    user_id = message.from_user.id
    user_data = {
        "id": user_id,
        "name": contact.first_name,
        "username": message.from_user.username or "",
        "phone": contact.phone_number,
    }
    save_user(user_id, user_data)
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Надіслати локацію", request_location=True)]],
        resize_keyboard=True,
    )
    await message.answer("Дякую! Тепер надішліть свою локацію:", reply_markup=kb)
    await state.set_state(RideStates.waiting_for_location)


@dp.message(RideStates.waiting_for_location, F.location)
async def handle_location(message: Message, state: FSMContext):
    if is_restricted_time():
        await message.answer(
            "🚫 Сервіс тимчасово недоступний з 00:00 до 05:00 у зв'язку з комендантською годиною."
        )
        return
    lat = message.location.latitude
    lon = message.location.longitude
    await state.update_data(start_coords=(lat, lon), stops=[])
    await message.answer(
        "Тепер введіть адресу призначення:", reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RideStates.waiting_for_address)


def geocode_address(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK":
            location = data["results"][0]["geometry"]["location"]
            return (location["lat"], location["lng"])
    except requests.RequestException as e:
        logging.error(f"Geocode error: {e}")
    return None


@dp.message(RideStates.waiting_for_address)
async def handle_address(message: Message, state: FSMContext):
    destination_address = message.text
    end_coords = geocode_address(destination_address)
    if not end_coords:
        await message.answer("❌ Не вдалося знайти адресу. Спробуйте ще раз.")
        return
    await state.update_data(end_coords=end_coords)

    data = await state.get_data()
    start_coords = data["start_coords"]
    stops = data.get("stops", [])
    route_coords = [start_coords] + stops + [end_coords]

    origin = f"{route_coords[0][0]},{route_coords[0][1]}"
    destination = f"{route_coords[-1][0]},{route_coords[-1][1]}"
    waypoints = "|".join(f"{lat},{lng}" for lat, lng in route_coords[1:-1])

    directions_url = "https://maps.googleapis.com/maps/api/directions/json"
    directions_params = {
        "origin": origin,
        "destination": destination,
        "waypoints": waypoints if waypoints else None,
        "mode": "driving",
        "key": GOOGLE_MAPS_API_KEY,
    }
    directions_response = requests.get(
        directions_url, params={k: v for k, v in directions_params.items() if v}
    )
    directions_data = directions_response.json()

    if directions_data["status"] != "OK":
        await message.answer("❌ Не вдалося побудувати маршрут.")
        return

    leg = directions_data["routes"][0]["legs"]
    total_distance = sum(leg_part["distance"]["value"] for leg_part in leg) / 1000
    await state.update_data(distance_km=total_distance)

    peak = is_peak_time()
    prices = {}
    for car_class in ["Стандарт", "Комфорт", "Бізнес"]:
        price = calculate_price(car_class, total_distance)
        if peak:
            price = int(price * 1.3)
        prices[car_class] = price

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🚗 Стандарт – {prices['Стандарт']}₴",
                    callback_data="class_Стандарт",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🚘 Комфорт – {prices['Комфорт']}₴",
                    callback_data="class_Комфорт",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🚖 Бізнес – {prices['Бізнес']}₴",
                    callback_data="class_Бізнес",
                )
            ],
        ]
    )
    await message.answer("Оберіть клас авто:", reply_markup=kb)
    await state.set_state(RideStates.waiting_for_car_class)


async def confirm_ride_end(user_id: str):
    path = Path("ratings.json")
    ratings = {}
    if path.exists():
        with path.open("r") as f:
            try:
                ratings = json.load(f)
            except:
                ratings = {}

    if user_id not in ratings:
        ratings[user_id] = []

    ratings[user_id].append({"rating": 5, "auto": True})

    with path.open("w") as f:
        json.dump(ratings, f, indent=4)


if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))


# === Обробка вибору класу авто ===
@dp.callback_query(F.data.startswith("class_"))
async def handle_car_class(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    car_class = callback.data.split("_")[1]
    distance_km = data["distance_km"]
    price = calculate_price(car_class, distance_km)

    await state.update_data(car_class=car_class, price=price)

    # Показ кнопки підтвердження
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Підтвердити замовлення", callback_data="confirm_ride"
                )
            ]
        ]
    )

    await callback.message.answer(
        f"Вартість поїздки класом '{car_class.title()}': {price}₴",
        reply_markup=keyboard,
    )
    await callback.answer()


# === Підтвердження замовлення ===
@dp.callback_query(F.data == "confirm_ride")
async def confirm_ride(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.message.answer(
        "🚕 Поїздку завершено. Дякуємо, що скористались FlyTaxi!"
    )

    # Надсилаємо кнопки оцінки
    rating_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⭐️1", callback_data="rate_1"),
                InlineKeyboardButton(text="⭐️2", callback_data="rate_2"),
                InlineKeyboardButton(text="⭐️3", callback_data="rate_3"),
                InlineKeyboardButton(text="⭐️4", callback_data="rate_4"),
                InlineKeyboardButton(text="⭐️5", callback_data="rate_5"),
            ]
        ]
    )
    await callback.message.answer("Оцініть поїздку:", reply_markup=rating_kb)
    await state.set_state(RideStates.waiting_for_rating)
    await callback.answer()


# === Обробка оцінок водія ===
@dp.callback_query(F.data.startswith("rate_"))
async def rate_driver(callback: CallbackQuery, state: FSMContext):
    rating_value = int(callback.data.split("_")[1])
    user_id = callback.from_user.id

    try:
        with open("ratings.json", "r", encoding="utf-8") as f:
            ratings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ratings = {}

    user_ratings = ratings.get(str(user_id), {"history": [], "total": 0.0, "count": 0})

    user_ratings["history"].append(rating_value)
    user_ratings["total"] += rating_value
    user_ratings["count"] += 1

    ratings[str(user_id)] = user_ratings

    with open("ratings.json", "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)

    await callback.message.answer("Дякуємо за оцінку!")
    await state.clear()
    await callback.answer()


# === Автоматична оцінка, якщо не натиснуто ===
async def confirm_ride_end(user_id: int):
    try:
        with open("ratings.json", "r", encoding="utf-8") as f:
            ratings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        ratings = {}

    user_ratings = ratings.get(str(user_id), {"history": [], "total": 0.0, "count": 0})
    user_ratings["history"].append(5)
    user_ratings["total"] += 5
    user_ratings["count"] += 1
    ratings[str(user_id)] = user_ratings

    with open("ratings.json", "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)


# === Запуск бота ===
if __name__ == "__main__":
    import asyncio

    asyncio.run(dp.start_polling(bot))
