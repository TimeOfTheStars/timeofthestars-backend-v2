#!/bin/sh
set -e

DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"

echo "Ожидание PostgreSQL на $DB_HOST:$DB_PORT..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -q; do
  sleep 1
done
echo "PostgreSQL готов."

echo "Применение миграций..."
alembic upgrade head

# Создать администратора при первом запуске (если заданы переменные)
if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  echo "Создание/обновление администратора '$ADMIN_USERNAME'..."
  python create_admin.py --username "$ADMIN_USERNAME" --password "$ADMIN_PASSWORD" --role admin || true
fi

echo "Запуск приложения..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8002 --proxy-headers
