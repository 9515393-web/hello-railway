import os
import asyncpg
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set")

app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def admin_map(request: Request):
    token = request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=403, detail="Token required")

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
        raise HTTPException(status_code=403, detail="Invalid token")

    if row["expires_at"] < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Token expired")

    # Если всё ок — показываем карту
    with open("map.html", "r", encoding="utf-8") as f:
        html = f.read()

    return HTMLResponse(content=html)
