# Боевой контур и деплой

## Что где

| | |
|---|---|
| Домен | `api.timeofthestars.ru` (он же админка: `/admin`) |
| Сервер | Timeweb Cloud, `200.165.226.249`, Ubuntu 24.04 |
| Ресурсы | 2 vCPU / 4 ГБ / 50 ГБ NVMe |
| Репозиторий | `/srv/tots/repo` |
| Медиа | `/srv/tots/media` (владелец uid **10001** — пользователь внутри контейнера) |
| Бэкапы | `/srv/tots/backups` |
| TLS | Caddy 2.11 на хосте, Let's Encrypt, сертификаты автоматом |
| Контейнеры | `tots_api` (127.0.0.1:8002), `tots_db` (портов не публикует) |

Выбор 4 ГБ — по измерениям: в покое связка занимает 600–850 МБ, пик при
перекодировании картинок ~1,3 ГБ. Лимиты в compose (1 ГБ на API, 768 МБ на базу)
оставляют запас на систему и Caddy.

## Схема запроса

```
клиент ──HTTPS──▶ Caddy (:443)
                  ├─ /media/*  ──▶ файлы с диска, Cache-Control: immutable
                  └─ остальное ──▶ 127.0.0.1:8002 (uvicorn в контейнере)
                                    └──▶ tots_db по внутренней сети compose
```

`/media` отдаёт Caddy напрямую с диска — Python в этом пути не участвует. Отсюда
bind mount тем же каталогом в контейнер: приложение туда пишет, Caddy оттуда читает.

Порт базы **не публикуется вообще**. Это не паранойя: `ufw` не фильтрует
опубликованные Docker'ом порты, они обходят его правила через `DOCKER-USER`.
По той же причине в проде используется отдельный `docker-compose.prod.yml`, а не
override — Compose при наложении файлов **склеивает** списки `ports`, снять
публикацию 5432 через override невозможно. Файл выбирается переменной
`COMPOSE_FILE` в `.env`, поэтому на сервере достаточно обычного `docker compose up -d`.

## Обновление

```bash
ssh root@200.165.226.249
cd /srv/tots/repo
/usr/local/bin/tots-backup.sh          # бэкап перед изменениями
git pull
docker compose up -d --build
docker compose logs -f --tail=50 api   # дождаться "Application startup complete"
curl -s https://api.timeofthestars.ru/health
```

Миграции применяются сами: `app.sh` ждёт PostgreSQL, потом `alembic upgrade head`,
потом при заданных `ADMIN_USERNAME`/`ADMIN_PASSWORD` заводит администратора, и лишь
затем запускает uvicorn. Скрипт под `set -e` и экземпляр один, так что **неудачная
миграция валит API в перезапуск** — миграции обязательно проверять на PostgreSQL
до деплоя, тесты их не проверяют (они идут через `create_all` на SQLite).

`ADMIN_USERNAME`/`ADMIN_PASSWORD` в `.env` применяются при **каждом** старте и
перезаписывают пароль существующего админа. После первого входа их надо
закомментировать — так и сделано на сервере.

## Откат

```bash
cd /srv/tots/repo
git log --oneline -5
git checkout <коммит>
docker compose up -d --build
```

Если ломающая правка была в миграции, откат кода этого не отменит:
`alembic downgrade -1` внутри контейнера, потом код. Все миграции проекта имеют
рабочий `downgrade()` — это требование, не пожелание.

Восстановление базы целиком:

```bash
gunzip -c /srv/tots/backups/tots-YYYY-MM-DD.sql.gz \
  | docker compose exec -T db psql -U postgres -d tots
```

## Бэкапы

`/usr/local/bin/tots-backup.sh` — `pg_dump | gzip` в `/srv/tots/backups`, cron
`/etc/cron.d/tots-backup` в 03:15 по Москве. `/etc/cron.d/tots-prune` подчищает старые.
Медиа в дамп не входят — это файлы на диске, их надо копировать отдельно
(`rsync -a /srv/tots/media`).

Восстановление проверялось: дамп разворачивается в чистую базу без ручных правок.

## Безопасность

- Вход по SSH — только по ключу. Пароль отключён в
  `/etc/ssh/sshd_config.d/00-hardening.conf`; префикс `00-` осознанный: облачный
  `50-cloud-init.conf` читается раньше, а sshd применяет **первое** вхождение
  директивы, поэтому файл с большим номером ничего бы не изменил. Плюс
  `ssh_pwauth: false` в `cloud.cfg.d`, чтобы cloud-init не вернул пароль обратно.
- `ufw`: открыты 22, 80, 443.
- При `ENV=prod` приложение **не стартует** с дефолтным `SECRET_KEY`, с
  `CORS_ORIGINS=*` или с дефолтным паролем базы — проверки в `app/core/config.py`.
- Cookie сессии админки помечена `Secure`, HSTS выставляет Caddy.
- `--no-server-header` у uvicorn, версия сервера в ответах не светится.
- `request_body max_size 12MB` в Caddy — выше `MAX_UPLOAD_MB` (10), чтобы клиент
  получал внятную ошибку приложения, а не обрыв на прокси.
- Пароль root, выданный при создании сервера, надо считать скомпрометированным
  (он проходил через переписку) и сменить.

## Мониторинг

`/usr/local/bin/tots-cert-watch.sh` по cron каждые 10 минут следит за сроком
сертификата. Плюс healthcheck'и контейнеров и `GET /health`.

Логи: `docker compose logs api`, `journalctl -u caddy`,
`/var/log/caddy/api-access.log`. Ротация docker-логов настроена в compose
(10 МБ × 3 файла на сервис) — иначе json-file растёт без предела.

## История: почему сертификат не выпускался сутки

Полезно как памятка по диагностике. `ERR_SSL_PROTOCOL_ERROR`, Let's Encrypt не мог
разрешить домен. Ложные следы: DNSSEC на зоне и совет поддержки «смените DNS на
Google». Настоящая причина — **lame delegation**: реестр отдавал зону на
`ns1/ns2.expired.reg.ru`, которые отвечали без флага `aa`, при том что whois
показывал NS Timeweb и состояние `UNVERIFIED`. Со стороны сервера это не лечится
никак. Порядок проверки, который привёл к ответу:

```bash
dig +trace api.timeofthestars.ru          # у кого зона на самом деле
dig @ns1.timeweb.ru api.timeofthestars.ru # авторитетный ли ответ (flags: aa)
whois timeofthestars.ru | grep -Ei 'nserver|state'
```

Вывод на будущее: **сначала `dig +trace`, потом всё остальное.** Пока делегирование
битое, ни Caddy, ни ACME, ни настройки сервера роли не играют.
