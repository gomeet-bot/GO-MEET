import asyncio
import sqlite3
from datetime import datetime
import random
from math import radians, sin, cos, sqrt, atan2

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor

# ========== КОНФИГ ==========
BOT_TOKEN = "8702573547:AAHhizvH3s83zcVN9_8uLAPUlt8aogHdStQ"
# ПРОКСИ (рабочий)
PROXY = "http://ivan:ProxyLondon2443@100.69.177.71:3128"

# Создаём бота с прокси
bot = Bot(token=BOT_TOKEN, proxy=PROXY)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ========== БАЗА ДАННЫХ ==========
conn = sqlite3.connect('go_meet.db')
cursor = conn.cursor()

cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        nickname TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
        rating REAL DEFAULT 5,
        points INTEGER DEFAULT 0
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS rooms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        city TEXT,
        latitude REAL,
        longitude REAL,
        meeting_time TEXT,
        max_people INTEGER,
        creator_id INTEGER,
        active INTEGER DEFAULT 1
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS room_members (
        room_id INTEGER,
        user_id INTEGER
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS room_tags (
        room_id INTEGER,
        tag TEXT
    )
''')

conn.commit()

# ========== FSM СОСТОЯНИЯ ==========
class CreateRoom(StatesGroup):
    title = State()
    city = State()
    time = State()
    max_people = State()
    tags = State()

class SetCity(StatesGroup):
    city = State()

class Register(StatesGroup):
    nickname = State()

# ========== КЛАВИАТУРЫ ==========
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="😫 Мне скучно")],
            [KeyboardButton(text="➕ Создать комнату")],
            [KeyboardButton(text="👤 Профиль")]
        ],
        resize_keyboard=True
    )

def room_keyboard(room_id, user_id, creator_id, is_member=False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if not is_member:
        keyboard.add(InlineKeyboardButton(text="☑️ Записаться", callback_data=f"join_{room_id}"))
    if is_member:
        keyboard.add(InlineKeyboardButton(text="🔻 Выйти", callback_data=f"leave_{room_id}"))
    keyboard.add(InlineKeyboardButton(text="📋 Подробнее", callback_data=f"detail_{room_id}"))
    if user_id == creator_id:
        keyboard.add(InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_{room_id}"))
    return keyboard

# ========== ФУНКЦИИ ==========
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def get_user(telegram_id):
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    return cursor.fetchone()

# ========== ОБРАБОТЧИКИ ==========
@dp.message_handler(commands=['start'])
async def start(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if user:
        await message.answer(f"С возвращением, {user[2]}!", reply_markup=main_keyboard())
    else:
        await message.answer("Привет! Давай создадим профиль. Введи свой никнейм:")
        await state.set_state(Register.nickname)

@dp.message_handler(state=Register.nickname)
async def register_nickname(message: types.Message, state: FSMContext):
    nickname = message.text.strip()
    cursor.execute("INSERT INTO users (telegram_id, nickname) VALUES (?, ?)", (message.from_user.id, nickname))
    conn.commit()
    await message.answer(f"Отлично, {nickname}! Теперь введи свой город:")
    await state.set_state(SetCity.city)

@dp.message_handler(state=SetCity.city)
async def set_city(message: types.Message, state: FSMContext):
    city = message.text.strip()
    lat, lon = 55.7558, 37.6173  # заглушка Москва
    cursor.execute("UPDATE users SET city = ?, latitude = ?, longitude = ? WHERE telegram_id = ?",
                   (city, lat, lon, message.from_user.id))
    conn.commit()
    await message.answer(f"✅ Город {city} сохранён!", reply_markup=main_keyboard())
    await state.finish()

@dp.message_handler()
async def handle_main_menu(message: types.Message, state: FSMContext):
    user = get_user(message.from_user.id)
    if not user:
        await start(message, state)
        return

    if message.text == "😫 Мне скучно":
        await find_rooms(message)
    elif message.text == "➕ Создать комнату":
        await message.answer("Введи название комнаты:")
        await state.set_state(CreateRoom.title)
    elif message.text == "👤 Профиль":
        await show_profile(message)
    else:
        await message.answer("Используй кнопки", reply_markup=main_keyboard())

@dp.message_handler(state=CreateRoom.title)
async def room_title(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['title'] = message.text
    await message.answer("Введи город встречи:")
    await state.set_state(CreateRoom.city)

@dp.message_handler(state=CreateRoom.city)
async def room_city(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['city'] = message.text
    await message.answer("Введи дату и время (ДД.ММ.ГГГГ ЧЧ:ММ) например: 25.12.2025 19:00")
    await state.set_state(CreateRoom.time)

@dp.message_handler(state=CreateRoom.time)
async def room_time(message: types.Message, state: FSMContext):
    try:
        meeting_time = datetime.strptime(message.text, "%d.%m.%Y %H:%M")
        async with state.proxy() as data:
            data['meeting_time'] = meeting_time.strftime("%Y-%m-%d %H:%M:%S")
        await message.answer("Максимум участников (до 20):")
        await state.set_state(CreateRoom.max_people)
    except:
        await message.answer("Неверный формат. Попробуй ещё раз (ДД.ММ.ГГГГ ЧЧ:ММ)")

@dp.message_handler(state=CreateRoom.max_people)
async def room_max_people(message: types.Message, state: FSMContext):
    try:
        max_people = int(message.text)
        if max_people > 20:
            await message.answer("Максимум 20 участников. Введи число меньше или равно 20")
            return
        async with state.proxy() as data:
            data['max_people'] = max_people
        await message.answer("Введи теги через запятую (например: настолки, кофе, кино):")
        await state.set_state(CreateRoom.tags)
    except:
        await message.answer("Введи число")

@dp.message_handler(state=CreateRoom.tags)
async def room_tags(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = get_user(message.from_user.id)

    lat, lon = 55.7558, 37.6173  # заглушка Москва

    cursor.execute('''
        INSERT INTO rooms (title, city, latitude, longitude, meeting_time, max_people, creator_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (data['title'], data['city'], lat, lon, data['meeting_time'], data['max_people'], user[0]))
    room_id = cursor.lastrowid

    tags = [t.strip() for t in message.text.split(',')]
    for tag in tags[:5]:
        cursor.execute("INSERT INTO room_tags (room_id, tag) VALUES (?, ?)", (room_id, tag))

    cursor.execute("INSERT INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, user[0]))
    conn.commit()

    await message.answer(f"✅ Комната «{data['title']}» создана!", reply_markup=main_keyboard())
    await state.finish()

async def find_rooms(message: types.Message):
    user = get_user(message.from_user.id)
    if not user or not user[4]:
        await message.answer("Сначала укажи город в профиле (напиши /start)")
        return

    cursor.execute("SELECT * FROM rooms WHERE active = 1 AND datetime(meeting_time) > datetime('now')")
    rooms = cursor.fetchall()

    if not rooms:
        await message.answer("Нет активных комнат. Создай свою!")
        return

    nearby = []
    for room in rooms:
        if room[3] and room[4]:
            dist = haversine(user[4], user[5], room[3], room[4])
            if dist <= 10:
                nearby.append((room, dist))
    nearby.sort(key=lambda x: x[1])

    if not nearby:
        await message.answer("В радиусе 10 км нет комнат. Создай свою!")
        return

    for room, dist in nearby[:5]:
        room_id, title, city, _, _, meeting_time, max_people, creator_id, _ = room
        cursor.execute("SELECT COUNT(*) FROM room_members WHERE room_id = ?", (room_id,))
        current = cursor.fetchone()[0]
        cursor.execute("SELECT nickname FROM users WHERE id = ?", (creator_id,))
        creator = cursor.fetchone()
        creator_nick = creator[0] if creator else "Кто-то"

        dt = datetime.strptime(meeting_time, "%Y-%m-%d %H:%M:%S")
        time_str = dt.strftime("%d.%m.%Y %H:%M")

        cursor.execute("SELECT 1 FROM room_members WHERE room_id = ? AND user_id = ?", (room_id, user[0]))
        is_member = cursor.fetchone() is not None

        text = f"🏠 *{title}*\n📍 {city}\n⏰ {time_str}\n👥 {current}/{max_people}\n👑 {creator_nick}\n📏 {dist:.1f} км"
        await message.answer(text, parse_mode="Markdown", reply_markup=room_keyboard(room_id, message.from_user.id, creator_id, is_member))

async def show_profile(message: types.Message):
    user = get_user(message.from_user.id)
    if not user:
        await message.answer("Напиши /start для регистрации")
        return

    cursor.execute("SELECT COUNT(*) FROM rooms WHERE creator_id = ?", (user[0],))
    created = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM room_members WHERE user_id = ?", (user[0],))
    joined = cursor.fetchone()[0]

    text = f"👤 *{user[2]}*\n📍 Город: {user[3] or 'не указан'}\n⭐ Рейтинг: {user[6]:.1f}\n🏆 Очков: {user[7]}\n📊 Создано: {created}\n📊 Участий: {joined}"
    await message.answer(text, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith('join_'))
async def join_room(callback: types.CallbackQuery):
    room_id = int(callback.data.split("_")[1])
    user = get_user(callback.from_user.id)

    cursor.execute("SELECT max_people FROM rooms WHERE id = ? AND active = 1", (room_id,))
    room = cursor.fetchone()
    if not room:
        await callback.answer("Комната не найдена", show_alert=True)
        return

    cursor.execute("SELECT COUNT(*) FROM room_members WHERE room_id = ?", (room_id,))
    current = cursor.fetchone()[0]
    if current >= room[0]:
        await callback.answer("Мест нет", show_alert=True)
        return

    cursor.execute("INSERT INTO room_members (room_id, user_id) VALUES (?, ?)", (room_id, user[0]))
    conn.commit()
    await callback.answer("✅ Записан!", show_alert=True)
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query_handler(lambda c: c.data.startswith('leave_'))
async def leave_room(callback: types.CallbackQuery):
    room_id = int(callback.data.split("_")[1])
    user = get_user(callback.from_user.id)

    cursor.execute("DELETE FROM room_members WHERE room_id = ? AND user_id = ?", (room_id, user[0]))
    conn.commit()
    await callback.answer("Вы вышли из комнаты")
    await callback.message.edit_reply_markup(reply_markup=None)

@dp.callback_query_handler(lambda c: c.data.startswith('cancel_'))
async def cancel_room(callback: types.CallbackQuery):
    room_id = int(callback.data.split("_")[1])
    user = get_user(callback.from_user.id)

    cursor.execute("SELECT creator_id FROM rooms WHERE id = ?", (room_id,))
    creator_id = cursor.fetchone()
    if creator_id and creator_id[0] == user[0]:
        cursor.execute("UPDATE rooms SET active = 0 WHERE id = ?", (room_id,))
        conn.commit()
        await callback.message.edit_text("❌ Комната отменена")
        await callback.answer("Комната отменена")
    else:
        await callback.answer("Только создатель может отменить", show_alert=True)

@dp.callback_query_handler(lambda c: c.data.startswith('detail_'))
async def room_detail(callback: types.CallbackQuery):
    room_id = int(callback.data.split("_")[1])

    cursor.execute('''
        SELECT r.*, u.nickname FROM rooms r
        JOIN users u ON r.creator_id = u.id
        WHERE r.id = ?
    ''', (room_id,))
    room = cursor.fetchone()
    if room:
        _, title, city, _, _, meeting_time, max_people, creator_id, _, creator_nick = room
        cursor.execute("SELECT tag FROM room_tags WHERE room_id = ?", (room_id,))
        tags = cursor.fetchall()
        cursor.execute("SELECT u.nickname FROM room_members rm JOIN users u ON rm.user_id = u.id WHERE rm.room_id = ?", (room_id,))
        members = cursor.fetchall()

        dt = datetime.strptime(meeting_time, "%Y-%m-%d %H:%M:%S")
        time_str = dt.strftime("%d.%m.%Y %H:%M")

        text = f"🏠 *{title}*\n📍 {city}\n⏰ {time_str}\n👥 {len(members)}/{max_people}\n👑 {creator_nick}\n"
        if tags:
            text += f"🏷️ Теги: {', '.join([t[0] for t in tags])}\n"
        text += f"\n👥 Участники: {', '.join([m[0] for m in members[:10]])}"
        await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("✅ Бот GO MEET запущен!")
    executor.start_polling(dp, skip_updates=True)