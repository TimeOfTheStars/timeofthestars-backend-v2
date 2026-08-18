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
# 172.16.0.0/12 — шлюз docker-бриджа: именно его uvicorn видит как peer,
# когда Caddy стучится на 127.0.0.1:8002 хоста. Только 127.0.0.1 здесь мало.
exec uvicorn app.main:app --host 0.0.0.0 --port 8002 \
  --proxy-headers --forwarded-allow-ips="127.0.0.1,172.16.0.0/12" \
  --no-server-header
