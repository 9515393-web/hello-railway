from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
import os
import asyncpg
from datetime import datetime
from pydantic import BaseModel

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


# ====== ВОТ ТУТ НАЧИНАЕТСЯ НОВЫЙ API ДЛЯ УЧАСТКОВ ======

class PlotDataIn(BaseModel):
    fio: str | None = None
    phone: str | None = None
    note: str | None = None


@app.get("/api/plot/{plot_key}")
async def get_plot_data(plot_key: str):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow(
        "SELECT plot_key, fio, phone, note FROM plot_data WHERE plot_key = $1",
        plot_key
    )
    await conn.close()

    if not row:
        return {"plot_key": plot_key, "fio": None, "phone": None, "note": None}

    return dict(row)


@app.post("/api/plot/{plot_key}")
async def save_plot_data(plot_key: str, data: PlotDataIn):
    conn = await asyncpg.connect(DATABASE_URL)

    await conn.execute(
        """
        INSERT INTO plot_data (plot_key, fio, phone, note, updated_at)
        VALUES ($1, $2, $3, $4, NOW())
        ON CONFLICT (plot_key)
        DO UPDATE SET
          fio = EXCLUDED.fio,
          phone = EXCLUDED.phone,
          note = EXCLUDED.note,
          updated_at = NOW()
        """,
        plot_key, data.fio, data.phone, data.note
    )

    await conn.close()

    return {"status": "ok", "plot_key": plot_key}


# ⚠️ ВРЕМЕННО! УДАЛИТЬ после использования!
@app.get("/_dev_extend_token")
async def _dev_extend_token(token: str):
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
