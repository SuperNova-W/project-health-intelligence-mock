from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .admin import router as admin_router
from .api import router
from .config import get_settings
from .db import close_db, init_db
from .seed import seed_demo_data


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    await init_db(settings)
    # The bundled fixtures are for local/demo runs only. A production
    # deployment ingests real projects through /boundaries and the
    # /admin/sync/* jobs, so seeding mock data there would just leave it
    # sitting alongside (or after a reset, reappearing next to) real data.
    if settings.environment != "production":
        await seed_demo_data()
    yield
    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:4173",
            "http://localhost:4173",
            "https://project-health-intelligence-mock.vercel.app",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    app.include_router(admin_router)
    return app


app = create_app()
