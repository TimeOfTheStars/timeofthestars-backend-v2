import os
import tempfile

# До импорта приложения подменяем БД на временный SQLite-файл (абсолютный путь).
_TMP = tempfile.mkdtemp(prefix="tots_test_")
_DB_PATH = os.path.join(_TMP, "test.db")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ["MEDIA_DIR"] = os.path.join(_TMP, "media")

import pathlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.base import Base
from app.db.session import async_session_maker, engine
from app.main import app
from app.schemas.auth import UserCreate
from app.models.enums import UserRole
from app.services import user_service


@pytest_asyncio.fixture
async def prepare_db():
    # пересоздаём схему на чистом файле
    db_file = pathlib.Path(_DB_PATH)
    if db_file.exists():
        db_file.unlink()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    # создаём админа
    async with async_session_maker() as db:
        await user_service.create(
            db, UserCreate(username="admin", password="admin", role=UserRole.admin)
        )
        await db.commit()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(prepare_db):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def token(client):
    resp = await client.post(
        "/api/v1/auth/login", data={"username": "admin", "password": "admin"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture
def auth(token):
    return {"Authorization": f"Bearer {token}"}
