import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.database import engine, Base
from backend.scheduler import start_scheduler, shutdown_scheduler
from backend.routers import accounts, packages, sync, route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified.")
    start_scheduler()
    yield
    # Shutdown
    shutdown_scheduler()


app = FastAPI(
    title="Zylmus Package Tracker",
    description="Self-hosted email-based package tracking with map",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(packages.router, prefix="/api/packages", tags=["packages"])
app.include_router(sync.router, prefix="/api/sync", tags=["sync"])
app.include_router(route.router, prefix="/api/route", tags=["route"])

# Serve frontend static files — must be mounted last
_frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.isdir(_frontend_path):
    app.mount("/", StaticFiles(directory=_frontend_path, html=True), name="static")
    logger.info("Serving frontend from: %s", os.path.abspath(_frontend_path))
else:
    logger.warning("Frontend directory not found at %s — API-only mode", _frontend_path)
