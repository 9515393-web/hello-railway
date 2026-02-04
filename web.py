from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
import os
import asyncpg
from datetime import datetime

app = FastAPI()

DATABASE_URL = os.getenv("DATABASE_URL")

@app.get("/Zahozhe_final_2026.geojson")
async def get_geojson(request: Request, token: str):
    conn = await asyncpg.connect(DATABASE_URL)

    row = await conn.fetchrow(
        "SELECT admin_id, expires_at FROM admin_sessions WHERE token = $1",
        token
    )

    await conn.close()

    if not row:
        return {"error": "invalid token"}

    if row["expires_at"] < datetime.utcnow():
        return {"error": "token expired"}

    return FileResponse("Zahozhe_final_2026.geojson", media_type="application/geo+json")
