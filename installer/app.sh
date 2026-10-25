# shellcheck shell=sh disable=SC2154
# shellcheck source=/dev/null
. "$SCRIPT_DIR/host-service.sh"

SVC_USER=$APP

app_check() {
  hs_init
  hs_expect_one_of LOG_LEVEL "$(config_value LOG_LEVEL | tr '[:lower:]' '[:upper:]')" DEBUG INFO WARNING ERROR CRITICAL
  _gid=$(config_value GUILD_ID)
  [ -z "$_gid" ] || hs_expect_int GUILD_ID "$_gid"
}

setup_python() {
  [ -x "$DIR/venv/bin/python3" ] || python3 -m venv "$DIR/venv"
  _sum=$(sha256sum "$DIR/requirements.txt" | cut -d' ' -f1)
  [ "$(cat "$DIR/venv/.requirements.sha256" 2>/dev/null)" != "$_sum" ] || return 0
  log "Python の依存を導入します"
  "$DIR/venv/bin/pip" install -q --no-cache-dir --upgrade pip
  "$DIR/venv/bin/pip" install -q --no-cache-dir -r "$DIR/requirements.txt"
  printf '%s\n' "$_sum" > "$DIR/venv/.requirements.sha256"
}

app_install() {
  hs_init
  case "$HS_OS" in
    debian) hs_pkg python3 python3-venv tzdata ca-certificates ;;
    alpine) hs_pkg python3 tzdata ca-certificates ;;
  esac
  hs_user "$SVC_USER"
  hs_dir "$DATA_DIR" "$SVC_USER" 750
  setup_python
  hs_service "$APP" --description "kaikei-san Discord bot" --user "$SVC_USER" -- "$DIR/installer/run/main.sh"
  hs_start "$APP"
  hs_prune
  log "ログ: $(hs_logs "$APP")"
  log "設定: $CONF_FILE（編集後は sudo $APP-ctl update で反映）"
}

app_uninstall() {
  hs_remove_all
}

app_purge() {
  hs_user_remove "$SVC_USER"
}
