import asyncpg
import asyncio
import aiohttp
import csv
import secrets

from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from io import BytesIO, StringIO
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
    FSInputFile,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
import qrcode
import os


API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set in Railway Variables")

RUN_LOCAL = os.getenv("RUN_LOCAL", "0") == "1"
IS_RAILWAY = os.getenv("RAILWAY_ENVIRONMENT") is not None


GOOGLE_FORM_URL = (
    "https://docs.google.com/forms/d/e/"
    "1FAIpQLScIlQHkjAVnb1L6-Nmpsoc8vUSKXjBUK24BKQIV3phAXVJy_g/"
    "viewform?usp=dialog"
)

CHAT_URL = "https://t.me/+dmJ15VfkRCc3YjUy"
BOT_URL = "https://t.me/Recreator_info_bot"
INIT_GROUP_CHAT_URL = "https://t.me/+ssdkgwxAIfZiMjUy"

GOOGLE_SHEET_ID = "1lB6_E7lGqh-DiIx-x4Jy-B_z0pNWdkCvaJEftCKAjXg"
GOOGLE_SHEET_GID = "1620808508"

bot_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="🤖 Открыть бота", url=BOT_URL)]
    ]
)
chat_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💬 Открыть чат", url=CHAT_URL)]
    ]
)
init_group_chat_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="💬 Открыть чат инициативной группы", url=INIT_GROUP_CHAT_URL)]
    ]
)
broadcast_confirm_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🧪 Тест себе", callback_data="broadcast_test"),
        ],
        [
            InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_send"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="broadcast_cancel"),
        ]
    ]
)

# ===== АДМИНЫ =====
ADMIN_IDS = {852852917, 1506477293, 954799948}
BROADCAST_PIN = os.getenv("BROADCAST_PIN", "1938")

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

dp = Dispatcher(storage=MemoryStorage())

# ===== ДИАГНОСТИКА =====
async def debug_bot(bot: Bot):
    me = await bot.get_me()
    print("БОТ ЗАПУЩЕН КАК:", me.username)
async def generate_qr() -> BufferedInputFile:
    qr = qrcode.make("https://t.me/Recreator_info_bot")

    bio = BytesIO()
    qr.save(bio, format="PNG")
    bio.seek(0)

    return BufferedInputFile(
        file=bio.read(),
        filename="recreator_bot_qr.png"
    )

# ===== КЛАВИАТУРА =====
keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🏡 О проекте")],
        [KeyboardButton(text="❓ Вопросы и ответы (FAQ)")],
        [KeyboardButton(text="📜 История деревни Захожье"), KeyboardButton(text="🗺 Карты")],
        [KeyboardButton(text="🗺 Дорожная карта"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="🗳 ОПРОС")],
        [KeyboardButton(text="📁 Документы по проекту"),KeyboardButton(text="💬 Чат жителей")],
        [KeyboardButton(text="🤝 Как помочь")]
    ],
    resize_keyboard=True
)
admin_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📊 Админ: статистика")],
        [KeyboardButton(text="🗺 Открыть админ-карту")],  # 👈 НОВАЯ КНОПКА
        [KeyboardButton(text="📣 Админ: рассылка"), KeyboardButton(text="📜 История рассылок")],
        [KeyboardButton(text="📁 Документы инициативной группы"), KeyboardButton(text="💬 Чат инициативной группы")],
        [KeyboardButton(text="⬅ Главное меню")]
    ],
    resize_keyboard=True
)

# ===== ДОКУМЕНТЫ ИНИЦИАТИВНОЙ ГРУППЫ (ПАПКИ) =====
init_docs_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📣 Агитационные материалы")],
        [KeyboardButton(text="📄 Протоколы / решения")],
        [KeyboardButton(text="✉️ Шаблоны писем / обращения")],
        [KeyboardButton(text="📎 Прочее")],
        [KeyboardButton(text="⬅ Назад в админ-меню")]
    ],
    resize_keyboard=True
)

# ===== ПАПКИ ИНИЦИАТИВНОЙ ГРУППЫ =====
INIT_DOCS_FOLDERS = {
    "📣 Агитационные материалы": "docs/docs/initiative/agit",
    "📄 Протоколы / решения": "docs/docs/initiative/protocols",
    "✉️ Шаблоны писем / обращения": "docs/docs/initiative/templates",
    "📎 Прочее": "docs/docs/initiative/other",
}

class AdminBroadcastState(StatesGroup):
    waiting_text = State()
    waiting_confirm = State()
    waiting_pin = State()

class InitDocsState(StatesGroup):
    choosing_file = State()

MAPS = {
    "🗺 Карта 1792 год": {
        "file": "maps/map_1792.jpg",
        "caption": (
            "🗺 **Выкопировка из карты Санкт-Петербургской губернии, 1792 г.**\n\n"
            "На карте деревня обозначена как **«М. Захонье»** "
            "(Малое Захонье).\n\n"
            "Первое картографическое подтверждение существования деревни "
            "в составе Российской империи."
        ),
    },
    "🗺 План деревни 1885 г.": {
        "file": "maps/map_1885.jpg",
        "caption": (
            "🗺 **План деревни Захожье, 1885 год**\n\n"
            "Отражает структуру застройки, "
            "расположение дворов и дорог.\n\n"
            "Период устойчивого развития XIX века."
        ),
    },
    "🗺 План деревни 1941 г.": {
        "file": "maps/map_1941.jpg",
        "caption": (
            "🗺 **Карта местности, 1941 год**\n\n"
            "Положение деревни Захожье "
            "накануне и в период Великой Отечественной войны."
        ),
    },
    "🗺 Карта - Настоящее время (выкопировка карты Росреестра)": {
        "file": "maps/map_now.jpg",
        "caption": (
            "🗺 **Территория Захожья — современное состояние**\n\n"
            "Границы СНТ, застройка и дорожная сеть.\n\n"
            "Используется для сравнения с историческими картами."
        ),
    },
}
maps_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=key)] for key in MAPS.keys()] +
             [[KeyboardButton(text="⬅ Назад")]],
    resize_keyboard=True
)

# ===== ДОКУМЕНТЫ ПО ПРОЕКТУ =====
docs_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📌 Нормативные документы")],
        [KeyboardButton(text="📝 Подготовленные документы")],
        [KeyboardButton(text="📤 Исходящие документы")],
        [KeyboardButton(text="📥 Входящие документы")],
        [KeyboardButton(text="📎 Иные документы")],
        [KeyboardButton(text="⬅ Назад")]
    ],
    resize_keyboard=True
)

# ===== БАЗА =====
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set in Railway Variables")
    

async def register_vote(uid: int):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO votes (user_id) VALUES ($1)",
        uid
    )
    await conn.close()
async def create_admin_session(admin_id: int) -> str:
    token = secrets.token_urlsafe(32)  # случайный безопасный токен
    expires_at = datetime.utcnow() + timedelta(minutes=10)

    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        """
        INSERT INTO admin_sessions (token, admin_id, expires_at)
        VALUES ($1, $2, $3)
        """,
        token, admin_id, expires_at
    )
    await conn.close()

    return token

async def init_db():
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            token TEXT PRIMARY KEY,
            admin_id BIGINT NOT NULL,
            expires_at TIMESTAMP NOT NULL
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS votes (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id SERIAL PRIMARY KEY,
            admin_id BIGINT NOT NULL,
            text TEXT NOT NULL,
            sent INT NOT NULL,
            failed INT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)

    await conn.close()


async def get_votes_count() -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval("SELECT COUNT(*) FROM votes")
    await conn.close()
    return count
async def get_unique_users_count() -> int:
    conn = await asyncpg.connect(DATABASE_URL)
    count = await conn.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM votes"
    )
    await conn.close()
    return count

async def get_all_user_ids() -> list[int]:
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch(
        "SELECT DISTINCT user_id FROM votes"
    )
    await conn.close()
    return [r["user_id"] for r in rows]

async def get_last_vote():
    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow("""
        SELECT user_id, created_at
        FROM votes
        ORDER BY created_at DESC
        LIMIT 1
    """)

    await conn.close()
    return row
    
async def get_votes_by_date(days_ago: int) -> int:
    conn = await asyncpg.connect(DATABASE_URL)

    count = await conn.fetchval("""
        SELECT COUNT(*)
        FROM votes
        WHERE created_at >= CURRENT_DATE - make_interval(days => $1)
          AND created_at <  CURRENT_DATE - make_interval(days => $1) + INTERVAL '1 day'
    """, days_ago)

    await conn.close()
    return count

# ===== ЛОГИ РАССЫЛОК =====
async def log_broadcast(admin_id: int, text: str, sent: int, failed: int):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute(
        "INSERT INTO broadcasts (admin_id, text, sent, failed) VALUES ($1, $2, $3, $4)",
        admin_id, text, sent, failed
    )
    await conn.close()


async def get_last_broadcast():
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow("""
        SELECT admin_id, text, sent, failed, created_at
        FROM broadcasts
        ORDER BY created_at DESC
        LIMIT 1
    """)
    await conn.close()
    return row


async def fetch_google_sheet_rows() -> list[dict]:
    url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}/export?format=csv&gid={GOOGLE_SHEET_GID}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=30) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Google Sheets HTTP {resp.status}")
            text = await resp.text()

    reader = csv.DictReader(StringIO(text))
    return list(reader)


def count_checked(rows: list[dict], column_name: str) -> int:
    count = 0
    for r in rows:
        val = (r.get(column_name) or "").strip()
        if val != "":
            count += 1
    return count

PAGE_SIZE = 10

async def show_files_page(message: types.Message, folder: str, title: str, page: int = 0):
    if not os.path.exists(folder):
        await message.answer(f"⚠️ Папка не найдена:\n<code>{folder}</code>")
        return

    files = sorted([
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
        and f != ".gitkeep"
    ])

    if not files:
        await message.answer("⚠️ В этой папке пока нет файлов.")
        return

    total_pages = (len(files) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    chunk = files[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    inline_rows = []

    # ✅ кнопки файлов
    for i, f in enumerate(chunk):
        inline_rows.append([
            InlineKeyboardButton(
                text=f"📄 {f}",
                callback_data=f"initdoc_file:{page}:{i}"
            )
        ])

    # ✅ навигация страниц (только если страниц больше 1)
    if total_pages > 1:
        nav_row = []

        if page > 0:
            nav_row.append(
                InlineKeyboardButton(text="⬅ Назад", callback_data=f"initdoc_page:{page-1}")
            )

        nav_row.append(
            InlineKeyboardButton(text=f"{page+1}/{total_pages}", callback_data="noop")
        )

        if page < total_pages - 1:
            nav_row.append(
                InlineKeyboardButton(text="Вперёд ➡", callback_data=f"initdoc_page:{page+1}")
            )

        inline_rows.append(nav_row)

    # ✅ назад к папкам (всегда)
    inline_rows.append([
        InlineKeyboardButton(text="⬅ Назад к папкам", callback_data="initdoc_back")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)

    text = f"{title}\n\nВыберите файл 👇"

    # ✅ пытаемся редактировать текущее сообщение
    try:
        await message.edit_text(text, reply_markup=kb)
    except Exception:
        await message.answer(text, reply_markup=kb)

# ======================================================
# ✅ CALLBACK: листание страниц (⬅➡) — СРАЗУ ПОД show_files_page()
# ======================================================
@dp.callback_query(F.data.startswith("initdoc_page:"))
async def init_docs_page(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    data = await state.get_data()
    folder = data.get("init_docs_folder")
    title = data.get("init_docs_title", "Документы")

    if not folder:
        await callback.message.answer("⚠️ Папка не выбрана. Откройте раздел заново.")
        await callback.answer()
        return

    try:
        page = int(callback.data.split(":")[1])
    except Exception:
        await callback.answer("⚠️ Ошибка страницы", show_alert=True)
        return

    await show_files_page(
        message=callback.message,
        folder=folder,
        title=f"📁 <b>{title}</b>",
        page=page
    )
    await callback.answer()

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "Здравствуйте! 👋\n\n"
        "Информационный бот инициативы восстановления деревни Захожье.\n\n"
        "Выберите раздел ниже 👇",
        reply_markup=keyboard
    )

@dp.message(Command("version"))
async def version_cmd(message: types.Message):
    await message.answer(
        "🟢 BOT VERSION 3.2\n"
        "Диагностика активна\n"
    )

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "🔐 Админ-панель",
        reply_markup=admin_keyboard
    )
ADMIN_MAP_BASE_URL = "https://admin-map-web-production.up.railway.app"

@dp.message(F.text == "🗺 Открыть админ-карту")
async def open_admin_map(message: types.Message):
    print("OPEN ADMIN MAP HANDLER TRIGGERED")
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ запрещён")
        return

    token = await create_admin_session(message.from_user.id)

    url = f"{ADMIN_MAP_BASE_URL}/?token={token}"

    await message.answer(
        "🗺 <b>Админ-карта</b>\n\n"
        "🔐 Ссылка действует 10 минут:\n"
        f"{url}"
    )
# ===== DEBUG: что реально приходит от кнопки =====
@dp.message()
async def _debug_text(message: types.Message):
    if is_admin(message.from_user.id):
        print("DEBUG TEXT =", repr(message.text))

@dp.message(Command("whoami"))
async def whoami(message: types.Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")
    
@dp.message(Command("bot"))
async def bot_link(message: types.Message):
    await message.answer(
        "🤖 Официальный бот проекта восстановления деревни Захожье:",
        reply_markup=bot_kb
    )
   
@dp.message(F.text == "📊 Админ: статистика")
async def admin_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администратора")
        return

    try:
        # ==== СТАРАЯ СТАТИСТИКА (клики по кнопке опроса) ====
        total = await get_votes_count()
        unique = await get_unique_users_count()
        today = await get_votes_by_date(0)
        yesterday = await get_votes_by_date(1)
        last = await get_last_vote()

        if last and last["created_at"]:
            last_user = last["user_id"]
            last_time = last["created_at"].strftime("%d.%m.%Y %H:%M")
        else:
            last_user = "—"
            last_time = "—"

        # ==== НОВАЯ СТАТИСТИКА (реальные ответы формы) ====
        try:
            rows = await fetch_google_sheet_rows()
        except Exception as e:
            rows = []
            await message.answer(f"❌ Ошибка чтения Google Sheets: {repr(e)}")

        # Считаем только заполненные строки (по времени)
        total_forms = sum(
            1 for r in rows
            if (r.get("Отметка времени") or "").strip() != ""
        )

        # Колонки формы
        col_disagree = "Несогласие с инициативой (при наличии)"
        col_ready = "Готовность участвовать в инициативе"
        col_live = "Сведения о проживании на территории (по желанию)"

        # Несогласие (если поле заполнено — значит есть несогласие)
        support_no = sum(
            1 for r in rows
            if (r.get("Отметка времени") or "").strip() != ""
            and (r.get(col_disagree) or "").strip() != ""
        )

        # Поддерживают = остальные ответы формы
        support_yes = total_forms - support_no

        # Нейтрально пока не считаем (нет отдельного поля)
        support_neutral = 0

        # Готовность участвовать (любое заполненное значение)
        sign_ready = sum(
            1 for r in rows
            if (r.get("Отметка времени") or "").strip() != ""
            and (r.get(col_ready) or "").strip() != ""
        )

        # Проживание (по желанию)
        live_const = sum(
            1 for r in rows
            if (r.get("Отметка времени") or "").strip() != ""
            and "постоян" in (r.get(col_live) or "").lower()
        )

        live_season = sum(
            1 for r in rows
            if (r.get("Отметка времени") or "").strip() != ""
            and "сезон" in (r.get(col_live) or "").lower()
        )

        def pct(x: int, total: int) -> str:
            if total == 0:
                return "0%"
            return f"{round(x * 100 / total)}%"

        # ==== ОТЧЁТ ====
        report = (
            "📊 <b>Админ-статистика</b>\n\n"
            "📌 <b>Переходы по кнопке опроса</b>\n"
            f"🔘 Переходов (клики): <b>{total}</b>\n"
            f"👥 Уникальных пользователей: <b>{unique}</b>\n"
            f"📅 Сегодня: <b>{today}</b>\n"
            f"📅 Вчера: <b>{yesterday}</b>\n"
            f"🆔 Последний переход: <code>{last_user}</code>\n"
            f"🕒 Время: <b>{last_time}</b>\n\n"
            "📌 <b>Реальные ответы в Google Form</b>\n"
            f"📝 Ответов в форме: <b>{total_forms}</b>\n\n"
            f"👍 Поддерживают: <b>{support_yes}</b> ({pct(support_yes, total_forms)})\n"
            f"👎 Не поддерживают: <b>{support_no}</b> ({pct(support_no, total_forms)})\n"
            f"✍️ Готовы участвовать: <b>{sign_ready}</b> ({pct(sign_ready, total_forms)})\n\n"
            f"🏠 Постоянно живут: <b>{live_const}</b> ({pct(live_const, total_forms)})\n"
            f"🌿 Сезонно: <b>{live_season}</b> ({pct(live_season, total_forms)})"
        )

        await message.answer(report, reply_markup=admin_keyboard)
        await message.answer("⬇️ Админ-меню", reply_markup=admin_keyboard)

    except Exception as e:
        print("АДМИН-СТАТИСТИКА ОШИБКА:", repr(e))
        await message.answer("⚠️ Ошибка получения статистики.")


# ======================================================
# ✅ ВОТ СЮДА ВСТАВЬ ОБРАБОТЧИК "📜 История рассылок"
# ======================================================
@dp.message(F.text == "📜 История рассылок")
async def admin_broadcast_history(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администратора")
        return

    last = await get_last_broadcast()

    if not last:
        await message.answer("📜 История пуста — рассылок ещё не было.", reply_markup=admin_keyboard)
        return

    dt = last["created_at"].strftime("%d.%m.%Y %H:%M") if last["created_at"] else "—"

    text = last["text"] or ""
    if len(text) > 800:
        text = text[:800] + "...\n\n(текст обрезан)"

    await message.answer(
        "📜 <b>Последняя рассылка</b>\n\n"
        f"👤 Админ ID: <code>{last['admin_id']}</code>\n"
        f"🕒 Время: <b>{dt}</b>\n"
        f"✅ Отправлено: <b>{last['sent']}</b>\n"
        f"⚠️ Ошибок: <b>{last['failed']}</b>\n\n"
        "📝 <b>Текст:</b>\n"
        f"{text}",
        reply_markup=admin_keyboard
    )
    await message.answer("⬇️ Админ-меню", reply_markup=admin_keyboard)

@dp.message(F.text == "📣 Админ: рассылка")
async def admin_broadcast_start(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await message.answer(
        "✏️ Отправьте текст рассылки.\n\n"
        "Сообщение будет отправлено всем участникам опроса."
    )
    await state.set_state(AdminBroadcastState.waiting_text)


@dp.message(AdminBroadcastState.waiting_text)
async def admin_broadcast_preview(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    text = message.text

    # сохраняем текст для подтверждения
    await state.update_data(broadcast_text=text)

    await message.answer(
        "📣 <b>Подтверждение рассылки</b>\n\n"
        "Будет отправлено сообщение:\n\n"
        f"{text}\n\n"
        "Подтвердить отправку?",
        reply_markup=broadcast_confirm_kb
    )

    await state.set_state(AdminBroadcastState.waiting_confirm)


# ===== CALLBACK: ПОДТВЕРЖДЕНИЕ РАССЫЛКИ =====
@dp.callback_query(F.data == "broadcast_cancel")
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text("❌ Рассылка отменена.")
    await callback.message.answer("⬇️ Админ-меню", reply_markup=admin_keyboard)
    await callback.answer()


@dp.callback_query(F.data == "broadcast_send")
async def broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != AdminBroadcastState.waiting_confirm.state:
        await callback.answer("⚠️ Рассылка уже завершена или не активна", show_alert=True)
        return

    # вместо отправки просим PIN
    await callback.message.answer("🔐 Введите PIN-код для подтверждения рассылки:\n\n(или напишите «Отмена»)")
    await state.set_state(AdminBroadcastState.waiting_pin)
    await callback.answer()


@dp.callback_query(F.data == "broadcast_test")
async def broadcast_test(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    current_state = await state.get_state()
    if current_state != AdminBroadcastState.waiting_confirm.state:
        await callback.answer("⚠️ Рассылка уже завершена или не активна", show_alert=True)
        return

    data = await state.get_data()
    text = data.get("broadcast_text")

    if not text:
        await callback.answer("⚠️ Текст рассылки не найден", show_alert=True)
        await state.clear()
        return

    try:
        await callback.bot.send_message(callback.from_user.id, f"🧪 <b>Тест рассылки</b>\n\n{text}")
        await callback.answer("✅ Тест отправлен тебе в личку", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {repr(e)}", show_alert=True)

@dp.message(AdminBroadcastState.waiting_pin)
async def broadcast_pin_check(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    pin = (message.text or "").strip()

    if pin.lower() in ("отмена", "/cancel"):
        await state.clear()
        await message.answer("❌ Рассылка отменена.", reply_markup=admin_keyboard)
        return

    if pin != BROADCAST_PIN:
        await message.answer("❌ Неверный PIN. Попробуйте ещё раз.\n\nНапишите «Отмена» чтобы выйти.")
        return

    data = await state.get_data()
    text = data.get("broadcast_text")

    if not text:
        await message.answer("⚠️ Текст рассылки не найден. Начните заново.")
        await state.clear()
        return

    user_ids = await get_all_user_ids()

    sent = 0
    failed = 0

    await message.answer("⏳ Рассылка отправляется...")

    for uid in user_ids:
        try:
            await message.bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1

    # ✅ ЛОГИРУЕМ РАССЫЛКУ В БД (после цикла)
    await log_broadcast(message.from_user.id, text, sent, failed)

    await state.clear()

    await message.answer(
        "📣 <b>Рассылка завершена</b>\n\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"⚠️ Ошибок: <b>{failed}</b>"
    )


# ===== О ПРОЕКТЕ =====
@dp.message(F.text == "🏡 О проекте")
async def about_cmd(message: types.Message):
   
    parts = [
        "🏡 <b>Зачем восстанавливать деревню Захожье?</b>\n"
        "<i>Кратко и по делу</i>\n\n"
        "Сегодня территория СНТ фактически является живым поселением, "
        "где многие проживают постоянно. Однако юридически деревни нет — "
        "она была упразднена, а вместе с ней исчезли адреса, статус и "
        "возможность полноценного развития.",

        "Создание (восстановление) деревни позволит привести документы "
        "и инфраструктуру в порядок и решить многие проблемы, "
        "с которыми жители сталкиваются из года в год.",

        "📌 **Что даст создание деревни жителям?**",

        "✔ **1. Официальные адреса для всех домов и участков**\n"
        "После восстановления деревни каждому дому и участку "
        "присваивается полноценный адрес:\n"
        "• корректная работа Почты и курьеров;\n"
        "• отсутствие путаницы в документах;\n"
        "• упрощение сделок с недвижимостью;\n"
        "• удобство в получении госуслуг.",

        "✔ **2. Возможность регистрации (прописки) в доме**\n"
        "Статус деревни означает:\n"
        "• возможность зарегистрироваться в жилом доме;\n"
        "• доступ к школе, поликлинике, детскому саду;\n"
        "• оформление льгот и субсидий по месту проживания.",

        "✔ **3. Развитие инфраструктуры за счёт бюджета**\n"
        "В отличие от СНТ, деревня входит в программы "
        "местного самоуправления:\n"
        "• содержание и ремонт подъездных дорог;\n"
        "• улучшение внутрипоселковых дорог;\n"
        "• уличное освещение;\n"
        "• участие в региональных программах развития.",

        "✔ **4. Рост стоимости и привлекательности недвижимости**\n"
        "Восстановление деревни повышает ценность территории:\n"
        "• дома и участки с адресами стоят дороже;\n"
        "• исчезают проблемы с ипотекой и регистрацией.",

        "✔ **5. Удобство для служб 112, МЧС, скорой, полиции**\n"
        "После включения деревни в официальные реестры:\n"
        "• экстренные службы легко находят адреса;\n"
        "• снижаются риски задержек при вызовах;\n"
        "• повышается общая безопасность поселения.",

        "✔ **6. Сохранение исторического названия «Захожье»**\n"
        "Создание деревни закрепляет исторический топоним, "
        "существующий много десятилетий, и сохраняет "
        "идентичность территории.",

        "📌 **Что для этого делается сейчас?**\n"
        "Инициативная группа жителей:\n"
        "• собирает данные о застройке и проживающих;\n"
        "• готовит схемы и карты территории;\n"
        "• ведёт работу с администрацией Никольского "
        "и Тосненского района;\n"
        "• готовит пакет документов на включение деревни "
        "в перечень населённых пунктов.\n\n"
        "При необходимости будут проведены публичные "
        "обсуждения и сход жителей.",

        "📌 **Что требуется от жителей?**\n"
        "✔ Поддержка инициативы (подписи, участие в обсуждениях);\n"
        "✔ Предоставление информации о фактически проживающих;\n"
        "✔ Конструктивное участие в работе инициативной группы.",


        "📧 **Контакты инициативной группы**\n"
        "recreator2026@mail.ru\n\n"
        
        "**Деревня Захожье — это наши дома, наша история и наше будущее.\n"
        "Её восстановление даст реальные преимущества каждому жителю.**"
    ]
    for p in parts:
        await message.answer(p)
    await message.answer(
    "🔝 **Конец раздела**\n\n"
    "Прокрутите чат вверх, чтобы читать с начала."
    )

@dp.message(F.text == "❓ Вопросы и ответы (FAQ)")
async def faq_cmd(message: types.Message):

    parts = [
        "❓ <b>ЧТО ЭТО ЗА БОТ?</b>\n\n"
        "Это информационно-опросный бот инициативной группы массива СНТ «Захожье». "
        "Он создан для информирования жителей и сбора обобщённых данных.",

        "❓ <b>ЭТО ОФИЦИАЛЬНЫЙ ГОСУДАРСТВЕННЫЙ БОТ?</b>\n\n"
        "Нет. Бот не является сервисом органов власти и не принимает решений.",

        "❓ <b>ОБЯЗАТЕЛЬНО ЛИ УЧАСТВОВАТЬ?</b>\n\n"
        "Нет. Участие полностью добровольное. "
        "Отказ не влечёт никаких последствий.",

        "❓ <b>ЧТО ИМЕННО СОБИРАЕТСЯ В ОПРОСЕ?</b>\n\n"
        "• наличие проживания (постоянно / сезонно);\n"
        "• отношение к инициативе;\n"
        "• готовность получать информацию.\n\n"
        "Персональные данные указываются по желанию.",

        "❓ <b>ЭТО ГОЛОСОВАНИЕ ИЛИ РЕШЕНИЕ?</b>\n\n"
        "Нет. Опрос не является голосованием "
        "и не создаёт юридических обязательств.",

        "❓ <b>ПЕРЕДАЮТСЯ ЛИ МОИ ДАННЫЕ В АДМИНИСТРАЦИЮ?</b>\n\n"
        "Нет. В органы власти могут направляться "
        "только обезличенные сводные данные.",

        "❓ <b>БУДУТ ЛИ НАЛОГИ ИЛИ ОБЯЗАТЕЛЬНЫЕ ПЛАТЕЖИ?</b>\n\n"
        "Нет. Инициативная группа не вводит "
        "никаких сборов или обязательств.",

        "❓ <b>ЧТО БУДЕТ ДАЛЬШЕ?</b>\n\n"
        "1️⃣ Сбор данных\n"
        "2️⃣ Публикация результатов\n"
        "3️⃣ Обсуждение с жителями\n"
        "4️⃣ Возможные обращения в администрацию",

        "📌 <b>КЛЮЧЕВОЙ ПРИНЦИП</b>\n\n"
        "Никаких решений без жителей.\n"
        "Никаких обязательств без согласия.\n"
        "Только официальный и поэтапный процесс.",
        
        "ℹ️ <i>Персональные данные обрабатываются в соответствии с ФЗ-152 "
        "и используются только для целей информирования и анализа.</i>"

    ]

    for p in parts:
        await message.answer(p)

    await message.answer(
        "🔝 <b>Конец раздела FAQ</b>\n\n"
        "Прокрутите чат вверх, чтобы читать с начала."
    )

# ===== КАРТЫ =====
@dp.message(F.text == "🗺 Карты")
async def maps_menu(message: types.Message):
    await message.answer(
        "🗺 <b>Карты деревни Захожье</b>\n\nВыберите период:",
        reply_markup=maps_keyboard
    )
@dp.message(F.text.in_(MAPS.keys()))
async def maps_handler(message: types.Message):
    data = MAPS[message.text]
    await message.answer_photo(
        FSInputFile(data["file"]),
        caption=data["caption"]
    )


# ===== ДОКУМЕНТЫ ПО ПРОЕКТУ =====
@dp.message(F.text == "📁 Документы по проекту")
async def docs_menu(message: types.Message):
    await message.answer(
        "📁 <b>Документы по проекту</b>\n\nВыберите категорию:",
        reply_markup=docs_keyboard
    )
    
@dp.message(F.text == "📁 Документы инициативной группы")
async def admin_docs_init_group(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администратора")
        return

    # сбрасываем прошлое состояние (если было)
    await state.clear()

    # показываем меню папок
    await message.answer(
        "📁 <b>Документы инициативной группы</b>\n\nВыберите раздел:",
        reply_markup=init_docs_keyboard
    )

@dp.message(F.text == "⬅ Назад в админ-меню")
async def back_to_admin_menu(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await message.answer("⬇️ Админ-меню", reply_markup=admin_keyboard)
    
@dp.message(F.text == "⬅ Главное меню")
async def admin_back_to_main(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await message.answer("⬅ Главное меню", reply_markup=keyboard)

@dp.message(F.text == "⬅ Назад")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("⬅ Главное меню", reply_markup=keyboard)

@dp.message(F.text.in_(INIT_DOCS_FOLDERS.keys()))
async def init_docs_open_folder(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администратора")
        return

    folder = INIT_DOCS_FOLDERS[message.text]

    # сохраним выбранную папку
    await state.update_data(init_docs_folder=folder, init_docs_title=message.text)

    # показываем список файлов (страница 0)
    await show_files_page(
        message=message,
        folder=folder,
        title=f"📁 <b>{message.text}</b>",
        page=0
    )

    # включаем режим выбора файла
    await state.set_state(InitDocsState.choosing_file)

# ===== ИНИЦИАТИВНАЯ ГРУППА: ОТПРАВКА ФАЙЛА =====
@dp.callback_query(F.data.startswith("initdoc_file:"))
async def init_docs_send_file(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("⚠️ Ошибка выбора файла", show_alert=True)
        return

    try:
        page = int(parts[1])
        idx = int(parts[2])
    except Exception:
        await callback.answer("⚠️ Ошибка данных кнопки", show_alert=True)
        return

    data = await state.get_data()
    folder = data.get("init_docs_folder")
    title = data.get("init_docs_title", "Документы")

    if not folder:
        await callback.answer("⚠️ Папка не выбрана. Открой раздел заново.", show_alert=True)
        return

    if not os.path.exists(folder):
        await callback.answer("⚠️ Папка не найдена на сервере", show_alert=True)
        return

    files = sorted([
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
        and f != ".gitkeep"
    ])

    total_pages = (len(files) + PAGE_SIZE - 1) // PAGE_SIZE
    page = max(0, min(page, total_pages - 1))

    chunk = files[page * PAGE_SIZE: page * PAGE_SIZE + PAGE_SIZE]

    if idx < 0 or idx >= len(chunk):
        await callback.answer("⚠️ Файл не найден", show_alert=True)
        return

    filename = chunk[idx]
    path = os.path.join(folder, filename)

    if not os.path.exists(path):
        await callback.answer("⚠️ Файл не найден на сервере", show_alert=True)
        return

    try:
        await callback.message.answer_document(
            FSInputFile(path),
            caption=f"📄 {filename}"
        )
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось отправить файл: {repr(e)}")
        await callback.answer("❌ Ошибка", show_alert=True)
        return

    back_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад к списку файлов", callback_data=f"initdoc_page:{page}")],
            [InlineKeyboardButton(text="⬅ Назад к папкам", callback_data="initdoc_back")],
        ]
    )

    await callback.message.answer(f"⬅ Вернуться назад в «{title}»", reply_markup=back_kb)
    await callback.answer("✅ Отправлено")

    
# ===== ИНИЦИАТИВНАЯ ГРУППА: НАЗАД К ПАПКАМ =====
@dp.callback_query(F.data == "initdoc_back")
async def init_docs_back(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    # ❌ НЕ НАДО state.clear()
    # await state.clear()

    await callback.message.answer(
        "📁 <b>Документы инициативной группы</b>\n\nВыберите раздел:",
        reply_markup=init_docs_keyboard
    )
    await callback.answer()


# ===== NOOP (для кнопки 1/3, 2/3 и т.п.) =====
@dp.callback_query(F.data == "noop")
async def noop_callback(callback: types.CallbackQuery):
    await callback.answer()

@dp.message(F.text == "💬 Чат инициативной группы")
async def admin_init_group_chat(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Доступ только для администратора")
        return

    await message.answer(
        "💬 <b>Чат инициативной группы</b>\n\n"
        "Нажмите кнопку ниже 👇",
        reply_markup=init_group_chat_kb
    )

@dp.message(F.text == "📌 Нормативные документы")
async def docs_normative(message: types.Message):
    folder = "docs/normative"

    await message.answer(
        "📌 <b>Нормативные документы</b>\n\n"
        "Отправляю PDF файлы 👇"
    )

    # Проверяем, что папка существует
    if not os.path.exists(folder):
        await message.answer(
            f"⚠️ Папка не найдена:\n<code>{folder}</code>\n\n"
            "Проверь, что папка есть в репозитории GitHub."
        )
        return

    # Берём все PDF файлы из папки
    pdf_files = sorted([
        f for f in os.listdir(folder)
        if f.lower().endswith(".pdf")
    ])

    if not pdf_files:
        await message.answer(
            "⚠️ В папке <code>docs/normative/</code> пока нет PDF файлов."
        )
        return

    # Отправляем каждый PDF
    for filename in pdf_files:
        path = os.path.join(folder, filename)

        await message.answer_document(
            document=FSInputFile(path),
            caption=f"📄 {filename}"
        )

@dp.message(F.text == "📝 Подготовленные документы")
async def docs_prepared(message: types.Message):
    folder = "docs/docs/prepared"

    await message.answer(
        "📝 <b>Подготовленные документы</b>\n\n"
        "Отправляю DOCX файлы 👇"
    )

    # Проверяем, что папка существует
    if not os.path.exists(folder):
        await message.answer(
            f"⚠️ Папка не найдена:\n<code>{folder}</code>\n\n"
            "Проверь, что папка есть в репозитории GitHub."
        )
        return

    # Берём все DOCX файлы из папки
    doc_files = sorted([
        f for f in os.listdir(folder)
        if f.lower().endswith(".docx")
    ])

    if not doc_files:
        await message.answer(
            "⚠️ В папке <code>docs/docs/prepared/</code> пока нет DOCX файлов."
        )
        return

    # Отправляем каждый DOCX
    for filename in doc_files:
        path = os.path.join(folder, filename)

        await message.answer_document(
            document=FSInputFile(path),
            caption=f"📄 {filename}"
        )

@dp.message(F.text == "📤 Исходящие документы")
async def docs_outgoing(message: types.Message):
    await message.answer(
        "📤 <b>Исходящие документы</b>\n\n"
        "Раздел в разработке.\n"
        "Сюда будут добавлены письма и обращения, отправленные в органы власти."
    )


@dp.message(F.text == "📥 Входящие документы")
async def docs_incoming(message: types.Message):
    await message.answer(
        "📥 <b>Входящие документы</b>\n\n"
        "Раздел в разработке.\n"
        "Сюда будут добавлены ответы и письма, полученные от органов власти."
    )


@dp.message(F.text == "📎 Иные документы")
async def docs_other(message: types.Message):
    await message.answer(
        "📎 <b>Иные документы</b>\n\n"
        "Раздел в разработке.\n"
        "Сюда будут добавлены прочие документы, схемы, справки и т.д."
    )

# ===== ИСТОРИЯ =====
@dp.message(F.text == "📜 История деревни Захожье")
async def history_cmd(message: types.Message):
    
    parts = [
        "📜 **Исторический очерк о деревне М. Захонье (Захожье)**\n\n"
        "**Введение**\n\n"
        "Деревня М. Захонье, позднее известная как Захожье, "
        "являлась одним из старинных сельских поселений Ингерманландии, "
        "располагавшимся на территории современной Ленинградской области, "
        "в пределах нынешнего Тосненского района.",

        "На протяжении более чем пяти столетий Захожье существовало "
        "как крестьянская деревня, меняя своё название, "
        "административную принадлежность и хозяйственную роль, "
        "прежде чем исчезнуть с официальных карт в конце XX века.",

        "История Захонья тесно связана с освоением земель "
        "вдоль рек Невы и Тосны, развитием Санкт-Петербургской губернии "
        "и судьбами крестьянских поселений Северо-Запада России.",

        "📌 **Ранние упоминания (XV–XVI века)**\n\n"
        "Самое раннее документальное упоминание поселения относится "
        "к 1500 году. В «Переписной окладной книге Водской пятины» "
        "зафиксированы две смежные деревни — «Захожаи» и «за Хожаи», "
        "входившие в состав Спасского Городенского погоста "
        "Ореховского уезда.",

        "Название поселения, по всей видимости, связано "
        "с топографическими особенностями местности — "
        "расположением «за ходом» или «за изгибом» пути, "
        "что характерно для древних славяно-финских топонимов "
        "Ингерманландии.",

        "📌 **XVII век и шведский период**\n\n"
        "После Столбовского мира 1617 года земли по нижнему течению "
        "Невы и Тосны оказались под властью Швеции. "
        "В этот период многие деревни региона переживали упадок.",

        "Несмотря на неблагоприятные условия и отток населения, "
        "Захонье сохранилось, что подтверждается его появлением "
        "на русских картах XVIII века.",

        "📌 **Возвращение в состав России и XVIII век**\n\n"
        "В ходе Северной войны (1700–1721) Пётр I вернул Ингерманландию "
        "в состав Российского государства. "
        "Основание Санкт-Петербурга сделало регион стратегически важным.",

        "На карте Санкт-Петербургской губернии 1792 года "
        "деревня обозначена как «М. Захонье», "
        "где сокращение «М.» означает «Малое».",

        "📌 **XIX век: формирование Захожья**\n\n"
        "В XIX веке название постепенно трансформируется:\n"
        "• 1810 — «Захонья»;\n"
        "• 1816 — «Захонье»;\n"
        "• 1834 — «Захожье».\n\n"
        "Именно форма «Захожье» становится устойчивой.",

        "К этому времени деревня имела линейную планировку, "
        "характерную для сельских поселений Шлиссельбургского уезда.",

        "📌 **XX век и исчезновение деревни**\n\n"
        "В XX веке Захожье постепенно утрачивало постоянное население. "
        "Во время Великой Отечественной войны территория находилась "
        "в зоне оккупации.",

        "Постановлением Правительства Ленинградской области "
        "от 22 апреля 1996 года № 167 деревня Захожье "
        "была официально упразднена в связи с отсутствием "
        "постоянно проживающего населения.",

        "📌 **Современное положение**\n\n"
        "На месте исторической деревни сформировался "
        "садоводческий массив СНТ «Захожье», "
        "унаследовавший историческое название.",

        "📍 **Заключение**\n\n"
        "История Захожья — это более 500 лет жизни поселения, "
        "отражающие судьбу сельских территорий Северо-Запада России.\n\n"
        "Сегодня восстановление деревни означает "
        "возвращение исторической справедливости и "
        "возрождение территории."
    ]
    for p in parts:
        await message.answer(p)
    await message.answer(
    "🔝 **Конец раздела**\n\n"
    "Прокрутите чат вверх, чтобы читать с начала."
    )


# ===== ДОРОЖНАЯ КАРТА =====
@dp.message(F.text == "🗺 Дорожная карта")
async def roadmap_cmd(message: types.Message):
   
    parts = [
        "🗺 **ДОРОЖНАЯ КАРТА восстановления деревни Захожье**\n"
        "_Тосненский район Ленинградской области_",

        "📍 **ЭТАП 1. Запуск инициативы и легитимация внутри СНТ**\n"
        "⏱ 6–12 недель\n\n"
        "**Цель:** показать, что есть население и поддержка.\n\n"
        "**Что делаем:**\n"
        "• формируем инициативную группу (3–7 человек);\n"
        "• создаём каналы связи (чат, почта);\n"
        "• распространяем информацию среди жителей;\n"
        "• собираем поддержку, данные о проживающих и застройке.\n\n"
        "**Результат:**\n"
        "✔ инициативная группа;\n"
        "✔ подтверждённая поддержка жителей;\n"
        "✔ первичные цифры по населению.",

        "📍 **ЭТАП 2. Подготовка документации**\n"
        "⏱ 1–2 месяца\n\n"
        "**Цель:** сформировать пакет документов для администрации.\n\n"
        "**Готовим:**\n"
        "• концепцию восстановления деревни;\n"
        "• обоснование восстановления;\n"
        "• данные о населении и застройке;\n"
        "• карты и схемы территории;\n"
        "• протокол поддержки жителей.\n\n"
        "**Результат:**\n"
        "✔ готовый пакет документов.",

        "📍 **ЭТАП 3. Работа с местной администрацией**\n"
        "⏱ 1–4 месяца\n\n"
        "**Куда обращаемся:**\n"
        "• администрация Никольского поселения;\n"
        "• администрация Тосненского района.\n\n"
        "**Ключевое действие:**\n"
        "📌 публичные слушания или сход жителей (ФЗ-131).\n\n"
        "**Результат:**\n"
        "✔ решение Совета депутатов;\n"
        "✔ официальная поддержка муниципалитета.",

        "📍 **ЭТАП 4. Региональный уровень (Ленинградская область)**\n"
        "⏱ 6–12 месяцев\n\n"
        "**Что происходит:**\n"
        "• проверка документов профильными комитетами;\n"
        "• подготовка законопроекта;\n"
        "• рассмотрение Законодательным собранием ЛО;\n"
        "• подписание закона губернатором.\n\n"
        "**Результат:**\n"
        "✔ деревня Захожье официально восстановлена.",

        "📍 **ЭТАП 5. Реестры и адреса**\n"
        "⏱ 1–3 месяца\n\n"
        "**Что делается:**\n"
        "• внесение в ФИАС, Росреестр, ОКТМО, ОКАТО;\n"
        "• утверждение адресов и нумерации улиц.\n\n"
        "**Результат:**\n"
        "✔ официальные адреса;\n"
        "✔ возможность прописки.",

        "📍 **ЭТАП 6. Развитие и благоустройство**\n"
        "⏱ постоянно\n\n"
        "**Что становится возможным:**\n"
        "• дороги и освещение;\n"
        "• участие в программах благоустройства;\n"
        "• рост стоимости недвижимости;\n"
        "• устойчивое развитие территории.",

        "🏁 **ИТОГ**\n\n"
        "Восстановление деревни Захожье — это поэтапный, "
        "юридически выверенный процесс, "
        "который даёт реальные преимущества жителям."
    ]
    for p in parts:
        await message.answer(p)

    await message.answer(
    "🔝 **Конец раздела**\n\n"
    "Прокрутите чат вверх, чтобы читать с начала."
    )

# ===== ПРОЧЕЕ =====
@dp.message(F.text == "🗳 ОПРОС")
async def vote_cmd(message: types.Message):
    uid = message.from_user.id

    # логируем каждый клик
    await register_vote(uid)

    await message.answer(
        "🗳 Участие в опросе\n\n"
        "Спасибо за интерес к проекту!\n\n"
        "👉 Перейти к опросу:"
    )
    await message.answer(GOOGLE_FORM_URL)

@dp.message(F.text == "📊 Статистика")
async def stats_cmd(message: types.Message):
    total = await get_votes_count()
    unique = await get_unique_users_count()

    await message.answer(
        f"📊 Статистика опроса\n\n"
        f"🔘 Переходов: {total}\n"
        f"👥 Участников: {unique}"
    )

@dp.message(F.text == "💬 Чат жителей")
async def chat_cmd(message: types.Message):
    await message.answer(
        "💬 <b>Чат жителей</b>\n\n"
        "Нажмите кнопку ниже, чтобы перейти в чат 👇",
        reply_markup=chat_kb
    )

@dp.message(F.text == "🤝 Как помочь")
async def help_cmd(message: types.Message):
    qr_image = await generate_qr()

    await message.answer_photo(
    photo=qr_image,
    caption=(
        "🤝 Как помочь проекту восстановления деревни Захожье\n\n"
        "1️⃣ Пройти опрос\n"
        "2️⃣ Поделитесь этим ботом с соседями\n"
        "3️⃣ Отсканируйте QR-код или перешлите ссылку\n"
        "4️⃣ Примите участие в обсуждении"
    ),
    reply_markup=bot_kb,
    parse_mode=None
)
@dp.message()
async def debug_all(message: types.Message):
    if is_admin(message.from_user.id):
        print("ПРИШЛО СООБЩЕНИЕ:", message.text)

# ===== ЗАПУСК =====
async def main():
    bot = Bot(
        API_TOKEN,
        default=DefaultBotProperties(parse_mode="HTML"),
        timeout=30
    )

    # 🔴 КРИТИЧЕСКИ ВАЖНО
    await bot.delete_webhook(drop_pending_updates=True)

    await init_db()
    await debug_bot(bot)

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
