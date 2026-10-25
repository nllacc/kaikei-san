#!/bin/sh
set -eu
set -a
# shellcheck source=/dev/null
. "$HS_CONF_FILE"
set +a
export TZ=Asia/Tokyo DB_PATH="$HS_DATA_DIR/kaikei.db"
cd "$HS_DIR/src"
exec "$HS_DIR/venv/bin/python3" -u main.py
