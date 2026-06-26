from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routes import router
from src.services.scheduler import start_daily_scheduler, stop_daily_scheduler
from src.services.telegram_bot import start_telegram_bot, stop_telegram_bot

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = ROOT / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_daily_scheduler()
    start_telegram_bot()
    yield
    stop_telegram_bot()
    stop_daily_scheduler()


app = FastAPI(title="Meeting Video Ideas Dashboard", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix="/api")

if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
