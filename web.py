from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
import os
import asyncpg
from datetime import datetime

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")

@app.get("/")
async def index(request: Request, token: str):
    # проверяем токен
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow(
        "SELECT admin_id, expires_at FROM admin_sessions WHERE token = $1",
        token
    )
    await conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="invalid token")

    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="token expired")

    # если всё ок — отдаём HTML карты
    return FileResponse("map.html", media_type="text/html")

@app.get("/Zahozhe_final_2026.geojson")
async def get_geojson(token: str):
    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        "SELECT admin_id, expires_at FROM admin_sessions WHERE token = $1",
        token
    )

    await conn.close()

    if not row:
        raise HTTPException(status_code=403, detail="Invalid token")

    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Token expired")

    # Проверим, что файл реально существует
    print("CWD:", os.getcwd())
    print("Files:", os.listdir("."))

    if not os.path.exists("Zahozhe_final_2026.geojson"):
        raise HTTPException(status_code=500, detail="GeoJSON file not found on server")

    return FileResponse(
        "Zahozhe_final_2026.geojson",
        media_type="application/geo+json",
        filename="Zahozhe_final_2026.geojson"
    )
