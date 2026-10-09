#!/bin/sh
# Запуск разового скрипта импорта данных на боевом сервере.
#
#   cd /srv/tots/repo && git pull && sh scripts/run_import.sh scripts/<файл>.py
#
# Делает всё по порядку: бэкап базы, пробный прогон, подтверждение, запись,
# уборка временных файлов. Без подтверждения ничего не пишет.
set -e

SCRIPT="$1"
if [ -z "$SCRIPT" ] || [ ! -f "$SCRIPT" ]; then
    echo "Укажите файл: sh scripts/run_import.sh scripts/import_....py"
    exit 1
fi
NAME=$(basename "$SCRIPT")

cd "$(dirname "$0")/.."

echo "=== 1/4 Бэкап базы ==="
sudo /usr/local/bin/tots-backup.sh | tail -1

echo
echo "=== 2/4 Пробный прогон (ничего не пишется) ==="
docker cp "$SCRIPT" tots_api:/tmp/"$NAME"
docker compose exec -T api sh -c "PYTHONPATH=/app python /tmp/$NAME --dry-run" </dev/null

echo
printf 'Записывать в базу? Введите «да»: '
read ANSWER
if [ "$ANSWER" != "да" ] && [ "$ANSWER" != "da" ]; then
    echo "Отменено, база не тронута."
    docker exec -u 0 tots_api rm -f /tmp/"$NAME"
    exit 0
fi

echo
echo "=== 3/4 Запись ==="
docker compose exec -T api sh -c "PYTHONPATH=/app python /tmp/$NAME --apply" </dev/null

echo
echo "=== 4/4 Уборка ==="
docker exec -u 0 tots_api rm -f /tmp/"$NAME"
echo "Готово. Если что-то пошло не так, последний бэкап лежит в /srv/tots/backups."
