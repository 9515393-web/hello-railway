import asyncpg
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()

# ---------- Проверка токена ----------
async def check_token(token: str):
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
        return False

    expires_at = row["expires_at"]
    if expires_at < datetime.utcnow():
        return False

    return True


# ---------- Главная страница карты ----------
@app.get("/admin/map", response_class=HTMLResponse)
async def admin_map(token: str = Query(...)):
    ok = await check_token(token)
    if not ok:
        return PlainTextResponse("⛔ Доступ запрещён или ссылка устарела", status_code=403)

    # Отдаём HTML карты
    return FileResponse("map.html")


# ---------- Отдаём GeoJSON ----------
@app.get("/data/zahozhe.geojson")
async def geojson(token: str = Query(...)):
    ok = await check_token(token)
    if not ok:
        raise HTTPException(status_code=403, detail="Forbidden")

    return FileResponse("Zahozhe_final_2026.geojson")

