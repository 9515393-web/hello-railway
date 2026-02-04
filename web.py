import asyncpg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI()

async def get_conn():
    return await asyncpg.connect(DATABASE_URL)

@app.get("/admin/map", response_class=HTMLResponse)
async def admin_map(token: str = Query(...)):
    conn = await get_conn()

    row = await conn.fetchrow(
        "SELECT admin_id, expires_at FROM admin_sessions WHERE token=$1",
        token
    )

    if not row:
        await conn.close()
        raise HTTPException(status_code=403, detail="Invalid token")

    if row["expires_at"] < datetime.utcnow():
        await conn.close()
        raise HTTPException(status_code=403, detail="Token expired")

    await conn.close()

    # Отдаём HTML карты
    return FileResponse("index.html")
