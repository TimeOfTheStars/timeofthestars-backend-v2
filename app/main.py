import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.admin.router import router as admin_router
from app.api.v1 import api_router
from app.core.config import settings
from app.db.session import engine
from app.services.media_service import media_root

logger = logging.getLogger("tots")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Проверка соединения с БД и создание директории для медиа
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))
    media_root()
    yield
    await engine.dispose()


app = FastAPI(
    title="Time Of The Stars",
    description="Хоккейная лига «TIME OF THE STARS» — API v2",
    version="2.0.0",
    lifespan=lifespan,
)

# Сессии нужны для логина в админ-панель (cookie)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Единый формат ошибок ---
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500, content={"detail": "Внутренняя ошибка сервера", "code": "internal_error"}
    )


# Статика для загруженных файлов
app.mount("/media", StaticFiles(directory=media_root()), name="media")

app.include_router(api_router)
app.include_router(admin_router)


@app.get("/", tags=["Root"])
async def root():
    return {"service": "Time Of The Stars API", "version": app.version, "docs": "/docs"}


@app.get("/health", tags=["Root"])
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
