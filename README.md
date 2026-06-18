# TIME OF THE STARS — backend v2

Бэкенд хоккейной лиги «TIME OF THE STARS». Полное переписывание прежнего бэкенда:
единая сущность соревнований, поматчевый протокол как единственный источник статистики,
JWT-авторизация с ролями, удобная кастомная админ-панель и хранение файлов на сервере.

## Стек

- **FastAPI** (async) + **Uvicorn**
- **PostgreSQL** + **SQLAlchemy 2.0** (typed, async) + **asyncpg**
- **Alembic** — миграции
- **Pydantic v2** — схемы
- **PyJWT** + **passlib[bcrypt]** — авторизация
- Админка: **Jinja2 + HTMX** (сервер-сайд, без отдельного SPA)

## Архитектура (ключевое)

- **Единый источник истины — сырые данные** (`games` + `game_player_stats`).
  Турнирная таблица и личная статистика **вычисляются на лету** (SQL-агрегация),
  отдельных счётчиков не храним — нечему рассинхронизироваться.
- **Никаких событийных хуков / фоновых тасков** — вся логика синхронна, в сервисном слое.
- `Competition` объединяет прежние «чемпионат» и «турнир» (поле `type`).
- Один матч принадлежит одному соревнованию (FK `games.competition_id`).

## Структура

```
app/
  core/        # config, security (JWT, bcrypt)
  db/          # Base, session (async)
  models/      # SQLAlchemy 2.0 модели
  schemas/     # Pydantic v2
  services/    # бизнес-логика
  api/v1/      # REST-роутеры (auth, teams, players, competitions, games, media, homepage)
  admin/       # кастомная админка (router + Jinja2 templates)
  main.py
alembic/       # миграции
tests/         # pytest
seed.py        # демо-данные
create_admin.py
```

## Запуск через Docker (рекомендуется)

```bash
cp .env.example .env   # при желании поправьте значения
docker compose up --build
```

- API: http://localhost:8002  · Swagger: http://localhost:8002/docs
- Админка: http://localhost:8002/admin  (по умолчанию `admin` / `admin`)
- Миграции применяются автоматически; администратор создаётся из `ADMIN_USERNAME/PASSWORD`.

## Локальный запуск (без Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # укажите доступ к локальному PostgreSQL

alembic upgrade head          # создать схему
python create_admin.py --username admin --password admin --role admin
python seed.py                # (опционально) демо-данные
uvicorn app.main:app --reload --port 8002
```

## Тесты

```bash
pytest          # использует временный SQLite, PostgreSQL не нужен
```

## Авторизация

- `POST /api/v1/auth/login` (form: `username`, `password`) → `{access_token, role}`.
- Заголовок `Authorization: Bearer <token>` для записи.
- Роли: `admin` (всё, включая пользователей) и `manager` (контент). Чтение публичное.

## Основные эндпоинты

| Метод | Путь | Назначение |
|------|------|-----------|
| GET/POST/PUT/DELETE | `/api/v1/teams`, `/players`, `/competitions` | справочники (пагинация, поиск) |
| POST/DELETE | `/api/v1/competitions/{id}/teams`, `/players` | состав соревнования |
| GET | `/api/v1/competitions/{id}/standings` | турнирная таблица (на лету) |
| GET | `/api/v1/competitions/{id}/players` | игроки соревнования со статистикой |
| GET | `/api/v1/competitions/{id}/best-players` | лучшие игроки |
| GET/PUT | `/api/v1/games/{id}` · `/games/{id}/protocol` | матч и протокол (box-score) |
| GET | `/api/v1/players/{id}/stats` | статистика игрока: карьера + по соревнованиям/командам |
| POST | `/api/v1/media` | загрузка файла (отдаётся на `/media/...`) |
| GET/PUT | `/api/v1/homepage` | настройки главного экрана |

## Миграции

```bash
alembic revision --autogenerate -m "описание"
alembic upgrade head
```
