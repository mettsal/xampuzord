#!/usr/bin/env bash
# Backup diário do banco do site (SQLite) com rotação.
# Chamado pelo timer systemd xampu-db-backup.timer; também roda à mão:
#   tools/db_backup.sh
#
# Variáveis (opcionais, também lidas de ~/.config/xampuzord/db-backup.env):
#   DB_PATH      banco vivo   (padrão: instance/xampuparaossos.db do repo)
#   BACKUP_DIR   destino      (padrão: ~/backups/xampu-db; o painel /admin lê daqui)
#   BACKUP_KEEP  quantos dias guardar (padrão: 14)
set -euo pipefail

CONF="${DB_BACKUP_CONF:-$HOME/.config/xampuzord/db-backup.env}"
if [ -f "$CONF" ]; then
    # shellcheck disable=SC1090
    . "$CONF"
fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DB_PATH="${DB_PATH:-$REPO/instance/xampuparaossos.db}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/xampu-db}"
BACKUP_KEEP="${BACKUP_KEEP:-14}"

mkdir -p "$BACKUP_DIR"
dest="$BACKUP_DIR/xampuparaossos-$(date +%F).db"

# .backup é consistente mesmo com o gunicorn escrevendo (cópia do arquivo não é).
sqlite3 "$DB_PATH" ".backup '$dest.tmp'"
if [ "$(sqlite3 "$dest.tmp" 'PRAGMA integrity_check;')" != "ok" ]; then
    echo "db_backup: integrity_check falhou em $dest.tmp" >&2
    exit 1
fi
mv "$dest.tmp" "$dest"
echo "db_backup: $dest ($(du -h "$dest" | cut -f1))"

# Rotação: mantém os BACKUP_KEEP mais recentes (pela data no nome, não pelo mtime).
ls -1 "$BACKUP_DIR"/xampuparaossos-*.db 2>/dev/null | sort -r | tail -n +"$((BACKUP_KEEP + 1))" | while read -r old; do
    rm -f -- "$old"
    echo "db_backup: removido $old"
done
