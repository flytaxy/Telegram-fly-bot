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
from aiogram.filters import CommandStart, StateFilter
from aiogram import F
from cd import calculate_price
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)


class RideStates(StatesGroup):
    waiting_for_waypoints = State()
    waiting_for_phone = State()
    waiting_for_location = State()
    waiting_for_address = State()
    waiting_for_car_class = State()
    waiting_for_confirmation = State()


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

        return {}
    with open("users.json", "r") as f:
        return json.load(f)


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
        "username": message.from_user.username,
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
    await state.update_data(start_coords=(lat, lon))
    await message.answer(
        "Тепер введіть адресу призначення:", reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(RideStates.waiting_for_address)


def geocode_address(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_MAPS_API_KEY}
    response = requests.get(url, params=params)
    data = response.json()
    if data["status"] == "OK":
        location = data["results"][0]["geometry"]["location"]
        return (location["lat"], location["lng"])
    return None


@dp.message(RideStates.waiting_for_address)
async def handle_address(message: Message, state: FSMContext):
    destination_address = message.text
    end_coords = geocode_address(destination_address)
    if not end_coords:
        await message.answer("❌ Не вдалося знайти адресу. Спробуйте ще раз.")
        return
    await state.update_data(end_coords=end_coords)

    user_data = await state.get_data()
    start_coords = user_data["start_coords"]

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
        await message.answer("❌ Не вдалося побудувати маршрут.")
        return

    route = directions_data["routes"][0]["legs"][0]
    distance_text = route["distance"]["text"]
    duration_text = route["duration"]["text"]
    distance_km = float(route["distance"]["value"]) / 1000

    await state.update_data(distance_km=distance_km)

    peak = is_peak_time()
    prices = {}
    for car_class in ["Стандарт", "Комфорт", "Бізнес"]:
        price = calculate_price(car_class, distance_km)
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


@dp.callback_query(RideStates.waiting_for_car_class)
async def process_car_class(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    car_class = callback.data.split("_")[1]
    user_data = await state.get_data()
    start_coords = user_data.get("start_coords")
    end_coords = user_data.get("end_coords")

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
    distance_km = float(route["distance"]["value"]) / 1000

    price = calculate_price(car_class, distance_km)
    if is_peak_time():
        price = int(price * 1.3)

    static_map_url = "https://maps.googleapis.com/maps/api/staticmap"
    static_map_params = {
        "size": "600x400",
        "path": f"enc:{directions_data['routes'][0]['overview_polyline']['points']}",
        "markers": f"color:green|label:A|{start_coords[0]},{start_coords[1]}&markers=color:red|label:B|{end_coords[0]},{end_coords[1]}",
        "key": GOOGLE_MAPS_API_KEY,
    }

    map_response = requests.get(static_map_url, params=static_map_params)
    with open("route_map.png", "wb") as f:
        f.write(map_response.content)

    if os.path.exists("route_map.png"):
        photo = FSInputFile("route_map.png")
        text = (
            f"🟢 Маршрут побудовано!"
            f"📍 Відстань: {distance_text}"
            f"🕒 Тривалість: {duration_text}"
            f"🚗 Клас авто: {car_class}"
            f"💸 Вартість поїздки: {price}₴"
        )
        if is_peak_time():
            text += "⚠️ Застосовано піковий тариф: +30%"

        await callback.message.answer_photo(photo)
        confirm_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Підтвердити замовлення", callback_data="confirm_ride"
                    )
                ]
            ]
        )
        await callback.message.answer(text, reply_markup=confirm_kb)
        await state.set_state(RideStates.waiting_for_confirmation)
    else:
        await callback.message.answer("❌ Не вдалося зберегти карту.")

    import asyncio

    import asyncio

    asyncio.run(dp.start_polling(bot))


@dp.message(F.text == "✏️ Змінити адресу")
async def change_address(message: Message, state: FSMContext):
    await message.answer("✏️ Введіть нову адресу призначення:")
    await state.set_state(RideStates.waiting_for_address)


@dp.message(RideStates.waiting_for_address)
async def handle_address(message: Message, state: FSMContext):
    await state.update_data(destinations=[message.text])
    await message.answer(
        "🔁 Хочеш додати зупинки? Введіть до 5 адрес або напишіть «Готово»."
    )
    await state.set_state(RideStates.waiting_for_waypoints)


@dp.message(RideStates.waiting_for_waypoints)
async def handle_waypoints(message: Message, state: FSMContext):
    user_data = await state.get_data()
    destinations = user_data.get("destinations", [])
    if message.text.lower() == "готово" or len(destinations) >= 6:
        start_coords = user_data.get("start_coords")
        coords = []
        for address in destinations:
            coord = geocode_address(address)
            if coord:
                coords.append(coord)

        if len(coords) < 1:
            await message.answer("❌ Не вдалося знайти жодної валідної адреси.")
            return

        await state.update_data(
            end_coords=coords[-1], waypoints=coords[1:-1] if len(coords) > 2 else []
        )
        await build_route_with_waypoints(message, state)
        return
    else:
        destinations.append(message.text)
        await state.update_data(destinations=destinations)
        await message.answer(
            f"✅ Зупинка {len(destinations)} додана. Введіть ще або «Готово»."
        )


async def build_route_with_waypoints(message: Message, state: FSMContext):
    user_data = await state.get_data()
    start = user_data["start_coords"]
    waypoints = user_data.get("waypoints", [])
    end = user_data["end_coords"]
    all_points = [f"{coord[0]},{coord[1]}" for coord in waypoints]

    directions_url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{start[0]},{start[1]}",
        "destination": f"{end[0]},{end[1]}",
        "waypoints": "|".join(all_points),
        "mode": "driving",
        "key": GOOGLE_MAPS_API_KEY,
    }

    response = requests.get(directions_url, params=params)
    data = response.json()

    if data["status"] != "OK":
        await message.answer("❌ Не вдалося побудувати маршрут.")
        return

    leg = data["routes"][0]["legs"]
    total_distance_m = sum(leg[i]["distance"]["value"] for i in range(len(leg)))
    total_duration = sum(leg[i]["duration"]["value"] for i in range(len(leg)))
    distance_km = total_distance_m / 1000
    duration_min = int(total_duration / 60)

    await state.update_data(distance_km=distance_km, duration_min=duration_min)

    peak = is_peak_time()
    prices = {}
    for car_class in ["Стандарт", "Комфорт", "Бізнес"]:
        price = calculate_price(car_class, distance_km)
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
    await message.answer(
        f"📍 Відстань: {distance_km:.1f} км🕓 Час у дорозі: {duration_min} хв",
        reply_markup=kb,
    )
    await state.set_state(RideStates.waiting_for_car_class)


@dp.message(F.text == "🔄 Перезапустити")
async def restart(message: Message, state: FSMContext):
    await state.clear()
    await start(message, state)
