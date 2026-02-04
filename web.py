import os
import asyncpg
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app = FastAPI()

# Статика (если будут css/js)
# app.mount("/static", StaticFiles(directory="static"), name="static")

MAP_FILE = "map.html"


async def check_token(token: str) -> bool:
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        row = await conn.fetchrow(
            """
            SELECT admin_id, expires_at
            FROM admin_sessions
            WHERE token = $1
            """,
            token
        )
    finally:
        await conn.close()

    if not row:
        return False

    expires_at = row["expires_at"]

    # сравниваем с текущим временем
    now = datetime.now(timezone.utc)

    # если expires_at без таймзоны — приводим
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at < now:
        return False

    return True


@app.get("/", response_class=HTMLResponse)
async def root(request: Request, token: str | None = None):
    if not token:
        return PlainTextResponse("⛔ Нет токена доступа", status_code=403)

    ok = await check_token(token)
    if not ok:
        return PlainTextResponse("⛔ Недействительный или просроченный токен", status_code=403)

    if not os.path.exists(MAP_FILE):
        return PlainTextResponse("⚠️ Файл карты не найден на сервере", status_code=500)

    with open(MAP_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(content=html)
