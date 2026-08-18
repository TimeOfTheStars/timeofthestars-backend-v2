import logging
from contextlib import asynccontextmanager
from pathlib import Path

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

# Сессии нужны для логина в админ-панель (cookie).
# https_only в проде: cookie с admin_user_id не должна уходить по plain HTTP.
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="tots_session",
    same_site="lax",
    https_only=settings.is_prod,
    max_age=7 * 24 * 3600,
)

# allow_credentials только при явном списке origin'ов: со "*" Starlette отражает
# любой присланный Origin вместе с Access-Control-Allow-Credentials: true.
_allow_any_origin = settings.cors_origins == ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=not _allow_any_origin,
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

# Ассеты админки (htmx). Монтируем в корневой /static, чтобы не пересекаться
# с path-параметрами админского роутера (/admin/{...}).
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "admin" / "static"),
    name="static",
)

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
