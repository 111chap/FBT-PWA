#!/bin/sh
# Run manually on the NAS after deploying migration 0007. No scheduled task is installed.
set -eu
umask 027
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
cd "${1:-/volume1/docker/fbt}"
test -f compose.yaml
test -f .env
if docker compose version >/dev/null 2>&1; then
    fbt_compose() { docker compose "$@"; }
elif command -v docker-compose >/dev/null 2>&1; then
    fbt_compose() { docker-compose "$@"; }
elif [ -x /var/packages/ContainerManager/target/usr/bin/docker-compose ]; then
    fbt_compose() { /var/packages/ContainerManager/target/usr/bin/docker-compose "$@"; }
else
    echo 'Container Manager Compose command was not found. Ask the NAS administrator to check its installation.' >&2
    exit 1
fi
fbt_backup="$(pwd -P)/backups/$(date -u +%Y%m%dT%H%M%SZ)"
test ! -e "$fbt_backup"
mkdir -p "$fbt_backup"
if [ "$(id -u)" = 0 ]; then
    chgrp administrators "$(pwd -P)/backups" "$fbt_backup"
    chmod 750 "$(pwd -P)/backups" "$fbt_backup"
fi
trap 'exit 1' HUP INT TERM
trap 'fbt_result=$?; if [ "$fbt_result" -ne 0 ]; then echo "Backup failed or was interrupted. Check the task log; web/worker may remain paused. Do not trust a partial backup folder." >&2; fi' EXIT
echo 'Pausing FBT writes and reminders for a consistent database-and-images backup.'
fbt_compose stop web worker
fbt_compose exec -T db pg_dump -U fbt -d fbt -Fc > "$fbt_backup/fbt.dump"
test -s "$fbt_backup/fbt.dump"
fbt_compose exec -T db pg_restore --list < "$fbt_backup/fbt.dump" > /dev/null
cp .env "$fbt_backup/settings.env"
cp compose.yaml "$fbt_backup/compose.yaml"
cp requirements.lock "$fbt_backup/requirements.lock"
fbt_compose run --rm --no-deps -T web python manage.py verify_media
fbt_compose run --rm --no-deps -T --entrypoint tar web -C /app/media -cf - . > "$fbt_backup/media.tar"
test -s "$fbt_backup/media.tar"
tar -tf "$fbt_backup/media.tar" > /dev/null
if [ "$(id -u)" = 0 ]; then
    chgrp administrators "$fbt_backup"/*
    chmod 640 "$fbt_backup"/*
fi
fbt_compose start web worker
echo "Backup completed: $fbt_backup"
echo 'Copy this entire folder to a protected location outside the NAS. Test an isolated restore before relying on it.'
