FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Системные зависимости (postgresql-client для pg_isready)
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x app.sh

# Непривилегированный пользователь. Хостовый каталог медиа должен принадлежать
# этому же UID: chown -R 10001:10001 /srv/tots/media
RUN useradd --system --uid 10001 --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p /app/media \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8002

CMD ["sh", "./app.sh"]
