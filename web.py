from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import os
import asyncpg
import asyncio

from datetime import datetime
#from bot import start_bot

# ===== ПАПКА ДОКУМЕНТОВ (Railway Volume) =====

BASE_DOCS = "/data/docs"

os.makedirs(BASE_DOCS + "/normative", exist_ok=True)
os.makedirs(BASE_DOCS + "/prepared", exist_ok=True)
os.makedirs(BASE_DOCS + "/incoming", exist_ok=True)
os.makedirs(BASE_DOCS + "/outgoing", exist_ok=True)
os.makedirs(BASE_DOCS + "/initiative", exist_ok=True)

app = FastAPI()

# ===== API СПИСОК ДОКУМЕНТОВ =====

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

# ===== СКАЧИВАНИЕ ДОКУМЕНТА =====

@app.get("/docs/{category}/{filename}")
async def download_doc(category: str, filename: str):

    path = os.path.join(BASE_DOCS, category, filename)

    if not os.path.exists(path):
        raise HTTPException(status_code=404)

    return FileResponse(path)

# ===== ЗАПУСК БОТА =====

#@app.on_event("startup")
async def start_services():
    asyncio.create_task(start_bot())

# ===== СТАТИЧЕСКИЕ ФАЙЛЫ =====

app.mount("/portal", StaticFiles(directory="portal"), name="portal")
app.mount("/maps", StaticFiles(directory="maps"), name="maps")
app.mount("/docs", StaticFiles(directory="/data/docs"), name="docs")
app.mount("/admin_static", StaticFiles(directory="admin"), name="admin_static")

DATABASE_URL = os.getenv("DATABASE_URL")

conn = None

async def get_conn():
    global conn

    try:
        if conn is None:
            conn = await asyncpg.connect(DATABASE_URL)
            return conn

        # проверка соединения
        await conn.execute("SELECT 1")
        return conn

    except Exception:
        try:
            conn = await asyncpg.connect(DATABASE_URL)
        except Exception as e:
            print("RECONNECT FAILED:", e)
            raise
        return conn


# ===============================
# ПРОВЕРКА АДМИН ТОКЕНА
# ===============================

async def require_admin(token: str):

    if not token:
        raise HTTPException(status_code=403, detail="token required")

    conn = await get_conn()

    row = await conn.fetchrow(
        """
        SELECT admin_id, expires_at
        FROM admin_sessions
        WHERE token = $1
        """,
        token
    )


    if not row:
        raise HTTPException(status_code=403, detail="invalid token")

    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="token expired")

    return row

async def audit_log(admin_id: int, action: str, target: str, payload: dict):

    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO admin_audit_log (admin_id, action, target, payload)
        VALUES ($1, $2, $3, $4)
        """,
        admin_id,
        action,
        target,
        payload
    )

    await conn.close()


# ===============================
# ПОРТАЛ САЙТА
# ===============================

@app.get("/site")
async def portal_site():
    return RedirectResponse("/portal/index.html")

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

    admin = await require_admin(token)

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

    await audit_log(
        admin["admin_id"],
        "edit_plot",
        plot_key,
        {
            "fio": data.fio,
            "phone": data.phone,
            "note": data.note
        }
    )

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

@app.get("/map.html")
async def admin_map(token: str):

    await require_admin(token)

    return FileResponse("./map.html")

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

DOCS_PATH = BASE_DOCS


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

# ===============================
# СТРАНИЦЫ ПОРТАЛА (чистые URL)
# ===============================

from fastapi import WebSocket, WebSocketDisconnect

connections = []

@app.websocket("/ws/chat")
async def websocket_chat(ws: WebSocket):

    await ws.accept()
    connections.append(ws)

    try:
        while True:

            try:
                data = await ws.receive_json()
            except:
                continue

            action = data.get("action")

            # ===== SEND =====
            if action == "send":

                if not data.get("text"):
                    continue

                conn = await asyncpg.connect(DATABASE_URL)

                row = await conn.fetchrow(
                    """
                    INSERT INTO chat_messages (username, message)
                    VALUES ($1,$2)
                    RETURNING id, username, message, deleted
                    """,
                    data.get("user"),
                    data.get("text")
                )

                await conn.close()

                for c in connections:
                    await c.send_json(dict(row))

            # ===== DELETE =====
            if action == "delete":

                conn = await asyncpg.connect(DATABASE_URL)

                await conn.execute(
                    """
                    UPDATE chat_messages
                    SET deleted = TRUE
                    WHERE id=$1 AND username=$2
                    """,
                    data.get("id"),
                    data.get("user")
                )

                await conn.close()

                for c in connections:
                    await c.send_json({
                        "id": data.get("id"),
                        "deleted": True
                    })

    except Exception as e:
        print("WS ERROR:", e)
        if ws in connections:
            connections.remove(ws)


@app.get("/")
async def portal_index():
    return FileResponse("portal/index.html")


@app.get("/{page}.html")
async def portal_pages(page: str):

    path = f"portal/{page}.html"

    if os.path.exists(path):
        return FileResponse(
            path,
            headers={"Cache-Control": "no-store"}
        )

    raise HTTPException(status_code=404)

# ===============================
# ЗАГРУЗКА ИСТОРИИ ЧАТА
# ===============================

@app.get("/api/chat/history")
async def get_chat_history():

    conn = await asyncpg.connect(DATABASE_URL)

    rows = await conn.fetch(
        """
        SELECT id, username, message, deleted
        FROM chat_messages
        ORDER BY id ASC
        LIMIT 50
        """
    )

    await conn.close()

    return [dict(r) for r in rows]

@app.post("/api/chat/delete")
async def delete_chat_message(data: dict):

    msg_id = data.get("id")
    user = data.get("user")

    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        """
        SELECT username
        FROM chat_messages
        WHERE id=$1
        """,
        msg_id
    )

    if not row:
        await conn.close()
        raise HTTPException(status_code=404)

    # удалить может только автор
    if row["username"] != user:
        await conn.close()
        raise HTTPException(status_code=403)

    await conn.execute(
        """
        UPDATE chat_messages
        SET deleted = TRUE
        WHERE id=$1
        """,
        msg_id
    )

    await conn.close()

    return {"status":"deleted"}
