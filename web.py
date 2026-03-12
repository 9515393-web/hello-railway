from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import os
import asyncpg
import asyncio
import secrets

from datetime import datetime
from bot import start_bot


# ===============================
# ПАПКА ДОКУМЕНТОВ (Railway Volume)
# ===============================

BASE_DOCS = "/data/docs"

os.makedirs(BASE_DOCS + "/normative", exist_ok=True)
os.makedirs(BASE_DOCS + "/prepared", exist_ok=True)
os.makedirs(BASE_DOCS + "/incoming", exist_ok=True)
os.makedirs(BASE_DOCS + "/outgoing", exist_ok=True)
os.makedirs(BASE_DOCS + "/initiative", exist_ok=True)

DOCS_PATH = BASE_DOCS

app = FastAPI()


# ===============================
# СТАТИЧЕСКИЕ ФАЙЛЫ
# ===============================

app.mount("/portal", StaticFiles(directory="portal"), name="portal")
app.mount("/maps", StaticFiles(directory="maps"), name="maps")
app.mount("/docs", StaticFiles(directory="/data/docs"), name="docs")
app.mount("/admin_static", StaticFiles(directory="admin"), name="admin_static")


# ===============================
# РЕДИРЕКТ ДОКУМЕНТОВ ПОРТАЛА
# ===============================

@app.get("/documents.html")
async def documents_redirect():
    return RedirectResponse("/portal/documents.html")

@app.get("/documents")
async def documents_redirect_short():
    return RedirectResponse("/portal/documents.html")


# ===============================
# КОРНЕВАЯ СТРАНИЦА
# ===============================

@app.get("/")
async def root():
    return RedirectResponse("/portal")


# ===============================
# ПОРТАЛ САЙТА
# ===============================

@app.get("/site")
async def portal_site():
    return FileResponse("portal/index.html")


# ===============================
# API СПИСОК ДОКУМЕНТОВ
# ===============================

@app.get("/api/docs/{category}")
async def list_docs(category: str):

    folder = os.path.join(BASE_DOCS, category)

    if not os.path.exists(folder):
        return JSONResponse({"files": []})

    files = [
        f for f in os.listdir(folder)
        if os.path.isfile(os.path.join(folder, f))
    ]

    return {"files": files}


# ===============================
# ВСЕ ДОКУМЕНТЫ (ДЛЯ ПОРТАЛА)
# ===============================

@app.get("/api/documents")
async def all_documents():

    categories = ["normative","prepared","incoming","outgoing","initiative"]
    result = {}

    for cat in categories:

        folder = os.path.join(BASE_DOCS, cat)
        files = []

        if os.path.exists(folder):

            for f in os.listdir(folder):

                files.append({
                    "name": f,
                    "url": f"/docs/{cat}/{f}"
                })

        result[cat] = files

    return result


# ===============================
# СКАЧИВАНИЕ ДОКУМЕНТА
# ===============================

@app.get("/docs/{category}/{filename}")
async def download_doc(category: str, filename: str):

    path = os.path.join(BASE_DOCS, category, filename)

    if not os.path.exists(path):
        raise HTTPException(status_code=404)

    return FileResponse(path)


# ===============================
# ЗАПУСК БОТА
# ===============================

@app.on_event("startup")
async def start_services():
    asyncio.create_task(start_bot())


DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


# ===============================
# ПРОВЕРКА АДМИН ТОКЕНА
# ===============================

async def require_admin(token: str):

    if not token:
        raise HTTPException(status_code=403, detail="token required")

    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        """
        SELECT admin_id, expires_at
        FROM admin_sessions
        WHERE token = $1
        """,
        token
    )

    await conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="invalid token")

    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="token expired")

    return row


# ===============================
# GEOJSON КАРТЫ
# ===============================

@app.get("/Zahozhe_final_2026.geojson")
async def get_geojson(token: str):

    await require_admin(token)

    if not os.path.exists("Zahozhe_final_2026.geojson"):
        raise HTTPException(status_code=500)

    return FileResponse(
        "Zahozhe_final_2026.geojson",
        media_type="application/geo+json",
        filename="Zahozhe_final_2026.geojson"
    )


# ===============================
# МОДЕЛЬ ДАННЫХ УЧАСТКА
# ===============================

class PlotDataIn(BaseModel):

    fio: str | None = None
    phone: str | None = None
    note: str | None = None


# ===============================
# ПОЛУЧИТЬ ДАННЫЕ УЧАСТКА
# ===============================

@app.get("/api/plot/{plot_key}")
async def get_plot_data(plot_key: str, token: str):

    await require_admin(token)

    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        """
        SELECT plot_key, fio, phone, note
        FROM plot_cards
        WHERE plot_key = $1
        """,
        plot_key
    )

    await conn.close()

    if not row:
        return {
            "plot_key": plot_key,
            "fio": None,
            "phone": None,
            "note": None
        }

    return dict(row)


# ===============================
# ВСЕ УЧАСТКИ
# ===============================

@app.get("/api/plot/all")
async def get_all_plots(token: str):

    await require_admin(token)

    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
        """
        SELECT plot_key, fio, phone
        FROM plot_cards
        """
    )

    await conn.close()

    return {row["plot_key"]: dict(row) for row in rows}


# ===============================
# СОХРАНЕНИЕ ДАННЫХ УЧАСТКА
# ===============================

@app.post("/api/plot/{plot_key}")
async def save_plot_data(plot_key: str, data: PlotDataIn, token: str):

    await require_admin(token)

    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO plot_cards (plot_key, fio, phone, note, updated_at)
        VALUES ($1, $2, $3, $4, NOW())

        ON CONFLICT (plot_key)
        DO UPDATE SET
            fio = EXCLUDED.fio,
            phone = EXCLUDED.phone,
            note = EXCLUDED.note,
            updated_at = NOW()
        """,
        plot_key,
        data.fio,
        data.phone,
        data.note
    )

    await conn.close()

    return {"status": "ok"}


# ===============================
# DEV ПРОДЛЕНИЕ ТОКЕНА
# ===============================

@app.get("/_dev_extend_token")
async def extend_token(token: str):

    conn = await asyncpg.connect(DATABASE_URL)

    result = await conn.execute(
        """
        UPDATE admin_sessions
        SET expires_at = NOW() + INTERVAL '7 days'
        WHERE token = $1
        """,
        token
    )

    await conn.close()

    return {"status": "ok", "result": result}


# ===============================
# СТРАНИЦА ВХОДА
# ===============================

@app.get("/admin")
async def admin_login_page():
    return FileResponse("admin/login.html")


# ===============================
# АДМИН ПАНЕЛЬ
# ===============================

@app.get("/admin_panel")
async def admin_panel(token: str):

    await require_admin(token)

    return FileResponse("admin/index.html")


# ===============================
# ЛОГИН АДМИНА
# ===============================

@app.post("/api/admin_login")
async def admin_login(data: dict):

    password = data.get("password")

    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403)

    token = secrets.token_hex(32)

    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO admin_sessions (token, admin_id, expires_at)
        VALUES ($1, 1, NOW() + INTERVAL '7 days')
        """,
        token
    )

    await conn.close()

    return {"token": token}


# ===============================
# ЗАГРУЗКА ДОКУМЕНТА
# ===============================

@app.post("/api/admin_upload_doc")
async def upload_document(
    token: str = Form(...),
    category: str = Form(...),
    file: UploadFile = File(...)
):

    await require_admin(token)

    folder = os.path.join(DOCS_PATH, category)

    os.makedirs(folder, exist_ok=True)

    filepath = os.path.join(folder, file.filename)

    contents = await file.read()

    with open(filepath, "wb") as f:
        f.write(contents)

    return {"status": "ok"}

PPAGES = {
 "about": {
  "title": "О проекте",
  "content": """
<h2>Зачем восстанавливать деревню Захожье?</h2>
<p><b>Кратко и по делу</b></p>

<p>
Сегодня территория СНТ фактически является живым поселением, где многие проживают постоянно.
Однако юридически деревни нет — она была упразднена, а вместе с ней исчезли адреса,
статус и возможность полноценного развития.
</p>

<p>
Создание (восстановление) деревни позволит привести документы и инфраструктуру
в порядок и решить многие проблемы, с которыми жители сталкиваются из года в год.
</p>

<hr>

<h3>Что даст создание деревни жителям?</h3>

<p><b>✔ 1. Официальные адреса для всех домов и участков</b></p>
<ul>
<li>корректная работа Почты и курьеров;</li>
<li>отсутствие путаницы в документах;</li>
<li>упрощение сделок с недвижимостью;</li>
<li>удобство в получении госуслуг.</li>
</ul>

<p><b>✔ 2. Возможность регистрации (прописки) в доме</b></p>
<ul>
<li>возможность зарегистрироваться в жилом доме;</li>
<li>доступ к прикреплению к школе, поликлинике, детскому саду;</li>
<li>оформление льгот и субсидий по месту проживания.</li>
</ul>

<p><b>✔ 3. Развитие инфраструктуры за счёт бюджета</b></p>
<ul>
<li>содержание и ремонт подъездных дорог;</li>
<li>улучшение внутрипоселковых дорог;</li>
<li>уличное освещение;</li>
<li>участие в региональных программах развития сельских территорий.</li>
</ul>

<p>
Бремя поддержания инфраструктуры перестаёт лежать только на плечах жителей.
</p>

<p><b>✔ 4. Рост стоимости и привлекательности недвижимости</b></p>
<ul>
<li>дома и участки с официальными адресами стоят дороже;</li>
<li>исчезают проблемы с ипотекой, маткапиталом и регистрацией прав.</li>
</ul>

<p><b>✔ 5. Удобство для служб 112, МЧС, скорой помощи и полиции</b></p>
<ul>
<li>экстренные службы легко находят адреса;</li>
<li>снижаются риски задержек при вызовах;</li>
<li>повышается безопасность поселения.</li>
</ul>

<p><b>✔ 6. Сохранение исторического названия «Захожье»</b></p>
<p>
Создание деревни закрепляет исторический топоним,
существующий много десятилетий, и сохраняет идентичность территории.
</p>

<hr>

<h3>Что для этого делается сейчас?</h3>

<p>Инициативная группа жителей:</p>

<ul>
<li>собирает данные о застройке и проживающих;</li>
<li>готовит схемы и карты территории;</li>
<li>ведёт работу с администрацией Никольского и Тосненского района;</li>
<li>готовит пакет документов на включение деревни в перечень населённых пунктов.</li>
</ul>

<p>
При необходимости будут проведены публичные обсуждения и сход жителей.
</p>

<hr>

<h3>Что требуется от жителей?</h3>

<p><b>✔ Поддержка инициативы</b> — участие в обсуждениях и сборе подписей.</p>

<p><b>✔ Предоставление информации о фактически проживающих</b>,
чтобы обосновать существование поселения.</p>

<p><b>✔ Конструктивное участие в работе инициативной группы.</b></p>

<hr>

<h3>Контакты инициативной группы</h3>

<p><b>recreator2026@mail.ru</b></p>

<p>
<b>Деревня Захожье — это наши дома, наша история и наше будущее.
Её восстановление даст реальные преимущества каждому жителю.</b>
</p>
"""
 }
}

@app.get("/api/page/{name}")
async def get_page(name: str):

    page = PAGES.get(name)

    if not page:
        return {"title": "", "content": ""}

    return page
