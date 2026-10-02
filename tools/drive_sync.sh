#!/usr/bin/env bash
# Sincroniza Google Drive -> pasta local (mão única, nunca apaga nada local).
# Chamado pelo timer systemd xampu-drive-sync.timer; também roda à mão:
#   tools/drive_sync.sh --dry-run
#
# Config em ~/.config/xampuzord/drive-sync.env:
#   DRIVE_SRC="gdrive:caminho/da/pasta"
#   DRIVE_DEST="/caminho/local"
#   DRIVE_MIN_AGE="2m"   (opcional)
set -euo pipefail

CONF="${DRIVE_SYNC_CONF:-$HOME/.config/xampuzord/drive-sync.env}"
if [ -f "$CONF" ]; then
    # shellcheck disable=SC1090
    . "$CONF"
fi
: "${DRIVE_SRC:?defina DRIVE_SRC em $CONF}"
: "${DRIVE_DEST:?defina DRIVE_DEST em $CONF}"
RCLONE="${RCLONE:-$HOME/.local/bin/rclone}"

# Uma execução por vez (timer + execução manual não se atropelam).
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/xampu-drive-sync.lock"
if ! flock -n 9; then
    echo "drive_sync: outra execução em andamento, saindo"
    exit 0
fi

mkdir -p "$DRIVE_DEST"

# copy (não sync): arquivo apagado no Drive continua existindo aqui.
# --min-age: ignora arquivo mexido há pouco, pra não pegar texto pela metade.
"$RCLONE" copy "$DRIVE_SRC" "$DRIVE_DEST" \
    --min-age "${DRIVE_MIN_AGE:-2m}" \
    --exclude 'desktop.ini' \
    --exclude '__pycache__/**' \
    --stats-one-line -v "$@"
