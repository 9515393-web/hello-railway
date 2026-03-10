from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File, Form

import os
import asyncpg
import asyncio
from bot import start_bot
from datetime import datetime
from pydantic import BaseModel


# ===============================
# СОЗДАНИЕ ПРИЛОЖЕНИЯ
# ===============================

app = FastAPI()

@app.on_event("startup")
async def start_services():
    asyncio.create_task(start_bot())

app.mount("/portal", StaticFiles(directory="portal"), name="portal")
app.mount("/maps", StaticFiles(directory="maps"), name="maps")
app.mount("/docs", StaticFiles(directory="docs"), name="docs")
app.mount("/admin_static", StaticFiles(directory="admin"), name="admin_static")

DATABASE_URL = os.getenv("DATABASE_URL")


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
# ПОРТАЛ САЙТА
# ===============================

@app.get("/site")
async def portal_site():
    return FileResponse("portal/index.html")


# ===============================
# АДМИН КАРТА
# ===============================

@app.get("/")
async def index(request: Request, token: str | None = None):

    if not token:
        raise HTTPException(status_code=403, detail="Token required")

    await require_admin(token)

    return FileResponse("map.html", media_type="text/html")


# ===============================
# GEOJSON КАРТЫ
# ===============================

@app.get("/Zahozhe_final_2026.geojson")
async def get_geojson(token: str):

    await require_admin(token)

    if not os.path.exists("Zahozhe_final_2026.geojson"):
        raise HTTPException(status_code=500, detail="GeoJSON file not found")

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
# ВСЕ УЧАСТКИ (ДЛЯ КАРТЫ)
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

    return {
        "status": "ok",
        "plot_key": plot_key
    }


# ===============================
# DEV ФУНКЦИЯ (ПРОДЛЕНИЕ ТОКЕНА)
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

    return {
        "status": "ok",
        "result": result
    }


# ===== СТРАНИЦА ВХОДА =====

@app.get("/admin")
async def admin_login_page():
    return FileResponse("admin/login.html")


# ===== АДМИН ПАНЕЛЬ =====

@app.get("/admin_panel")
async def admin_panel(token: str):

    await require_admin(token)

    return FileResponse("admin/index.html")


import secrets

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


@app.post("/api/admin_login")
async def admin_login(data: dict):

    password = data.get("password")

    if password != ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="wrong password")

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
# СТРАНИЦЫ ПОРТАЛА
# ===============================

@app.get("/api/page/{slug}")
async def get_page(slug: str):

    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        """
        SELECT title, content
        FROM pages
        WHERE slug = $1
        """,
        slug
    )

    await conn.close()

    if not row:
        raise HTTPException(status_code=404)

    return dict(row)

# ===============================
# СТАТИСТИКА ДЛЯ ПОРТАЛА
# ===============================

@app.get("/api/stats")
async def get_stats():

    conn = await asyncpg.connect(DATABASE_URL)

    total_votes = await conn.fetchval(
        "SELECT COUNT(*) FROM votes"
    )

    unique_users = await conn.fetchval(
        "SELECT COUNT(DISTINCT user_id) FROM votes"
    )

    await conn.close()

    return {
        "votes": total_votes,
        "people": unique_users,
        "target": 1600
    }

DOCS_PATH = "docs"


@app.get("/api/documents")
async def get_documents():

    result = {}

    folders = [
        "normative",
        "prepared",
        "incoming",
        "outgoing",
        "initiative"
    ]

    for folder in folders:

        path = os.path.join(DOCS_PATH, folder)

        if not os.path.exists(path):
            continue

        files = []

        for f in os.listdir(path):

            files.append({
                "name": f,
                "url": f"/docs/{folder}/{f}"
            })

        result[folder] = files

    return result

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
