# TIME OF THE STARS — backend v2

Бэкенд и админ-панель хоккейной лиги «TIME OF THE STARS»: команды, игроки,
соревнования, протоколы матчей с таймлайном, турнирная таблица и личная статистика.

**В бою:** https://api.timeofthestars.ru · Swagger — `/docs` · админка — `/admin`

## 📚 Документация

Полная документация — в каталоге **[`docs/`](docs/)**:

| Документ | О чём |
|---|---|
| [docs/README.md](docs/README.md) | оглавление и точки входа по роли |
| [Архитектура](docs/architecture.md) | слои, ключевые решения и почему они такие |
| [Модель данных](docs/data-model.md) | таблицы, связи, перечисления, инварианты |
| [API](docs/api.md) | справочник REST, авторизация, соглашения |
| [Админ-панель](docs/admin.md) | экраны и ввод протокола матча |
| [Деплой](docs/deployment.md) | сервер, выкатка, бэкапы, TLS |
| [Разработка](docs/development.md) | локальный запуск, тесты, миграции, стиль |
| [Эксплуатация](docs/operations.md) | правила ведения данных, диагностика |

Контракт для фронтенда лежит отдельно: [API_FRONTEND.md](API_FRONTEND.md) и
[API_FRONTEND_TIMELINE.md](API_FRONTEND_TIMELINE.md).

## Стек

FastAPI (async) + Uvicorn · PostgreSQL 16 + SQLAlchemy 2.0 (typed, async) + asyncpg ·
Alembic · Pydantic v2 · PyJWT + passlib[bcrypt] · Pillow · админка на Jinja2 без
сборки и без SPA · Docker Compose, Caddy на хосте.

## Архитектура в трёх пунктах

- **Считаем, а не храним.** Турнирная таблица и статистика игроков выводятся SQL-агрегацией
  при чтении. Счётчиков в базе нет — рассинхронизироваться нечему.
- **События матча — источник истины.** Голы, передачи и штрафные минуты игрока выводятся
  из `game_events` при сохранении протокола; руками вводятся только участие и вратарские цифры.
- **Логика в сервисном слое.** Ручки API и админка вызывают один и тот же сервис.
  Ни фоновых задач, ни событийных хуков, ни кэша.

Подробнее и с обоснованиями — [docs/architecture.md](docs/architecture.md).

## Быстрый старт

```bash
cp .env.example .env
docker compose up -d --build
```

API — http://localhost:8002, Swagger — `/docs`, админка — `/admin`. Миграции
применяются автоматически при старте; администратор создаётся из `ADMIN_USERNAME`
и `ADMIN_PASSWORD`, если они заданы в `.env`.

Без Docker и с тестами — [docs/development.md](docs/development.md).

```bash
pytest        # 47 тестов, временный SQLite, PostgreSQL не нужен
```

## Структура

```
app/
  core/        # config, security (JWT, bcrypt)
  db/          # Base, async session
  models/      # SQLAlchemy 2.0
  schemas/     # Pydantic v2
  services/    # бизнес-логика — единственная точка правил
  api/v1/      # REST: auth, teams, players, competitions, games, media, homepage
  admin/       # админка: router + Jinja2 templates
  main.py
alembic/       # миграции
docs/          # документация
tests/         # pytest
seed.py  create_admin.py
```
