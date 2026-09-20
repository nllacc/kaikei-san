#!/bin/sh
# kaikei-san インストーラ (Alpine / Ubuntu・Debian 系の LXC コンテナ向け)
#
# 使い方 (root で実行):
#   TOKEN=xxxx sh install.sh          # インストール / アップデート
#   sh install.sh --uninstall         # サービスとプログラムを削除 (設定と DB は残す)
#   sh install.sh --uninstall --purge # 設定と DB も含めて完全に削除
#
# 環境変数:
#   TOKEN / GUILD_ID / LOG_LEVEL  初回の設定ファイル生成時に使用
#   REPO_REF     取得する ref (タグ / ブランチ)
#   SRC_TARBALL  GitHub の代わりに使うローカル tarball (検証用)
set -eu

# CI がリリース時に書き換える (行頭一致のため位置・書式を変えないこと)
REPO_REF_DEFAULT="main"

REPO="${REPO:-nllacc/kaikei-san}"
REPO_REF="${REPO_REF:-$REPO_REF_DEFAULT}"

APP=kaikei-san
APP_USER=kaikei
APP_DIR="/opt/$APP"
CONF_DIR="/etc/$APP"
ENV_FILE="$CONF_DIR/$APP.env"
DATA_DIR="/var/lib/$APP"
LOG_FILE="/var/log/$APP.log"

log() { printf '==> %s\n' "$*"; }
warn() { printf '警告: %s\n' "$*" >&2; }
die() {
  printf 'エラー: %s\n' "$*" >&2
  exit 1
}

# ---- OS 判定 ----------------------------------------------------------------
detect_os() {
  [ -r /etc/os-release ] || die "/etc/os-release が見つかりません"
  # shellcheck disable=SC1091
  . /etc/os-release
  case " ${ID:-} ${ID_LIKE:-} " in
    *" alpine "*) OS=alpine ;;
    *" ubuntu "* | *" debian "*) OS=debian ;;
    *) die "未対応の OS です: ${ID:-unknown} (Alpine / Ubuntu / Debian のみ対応)" ;;
  esac
}

# ---- OS ごとの差分 ----------------------------------------------------------
install_packages() {
  case "$OS" in
    alpine)
      apk add --no-cache python3 py3-pip tzdata ca-certificates curl
      ;;
    debian)
      export DEBIAN_FRONTEND=noninteractive
      apt-get update -qq
      apt-get install -y -qq python3 python3-venv python3-pip tzdata ca-certificates curl
      ;;
  esac
}

add_user() {
  id "$APP_USER" >/dev/null 2>&1 && return 0
  case "$OS" in
    alpine)
      addgroup -S "$APP_USER"
      adduser -S -D -H -h "$DATA_DIR" -s /sbin/nologin -G "$APP_USER" "$APP_USER"
      ;;
    debian)
      useradd --system --no-create-home --home-dir "$DATA_DIR" \
        --shell /usr/sbin/nologin "$APP_USER"
      ;;
  esac
}

install_service() {
  case "$OS" in
    alpine)
      touch "$LOG_FILE"
      chown "$APP_USER:$APP_USER" "$LOG_FILE"
      cat >"/etc/init.d/$APP" <<EOF
#!/sbin/openrc-run
# kaikei-san (自動生成: install.sh)
name="$APP"
description="kaikei-san Discord bot"
supervisor="supervise-daemon"
command="/bin/sh"
command_args="-c 'set -a; . $ENV_FILE; set +a; cd $APP_DIR/src; exec $APP_DIR/venv/bin/python -u main.py'"
command_user="$APP_USER:$APP_USER"
output_log="$LOG_FILE"
error_log="$LOG_FILE"

depend() {
  need net
}
EOF
      chmod 755 "/etc/init.d/$APP"
      rc-update add "$APP" default >/dev/null
      ;;
    debian)
      cat >"/etc/systemd/system/$APP.service" <<EOF
[Unit]
Description=kaikei-san Discord bot
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_USER
EnvironmentFile=$ENV_FILE
WorkingDirectory=$APP_DIR/src
ExecStart=$APP_DIR/venv/bin/python -u main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
      systemctl daemon-reload
      systemctl enable "$APP" >/dev/null 2>&1
      ;;
  esac
}

restart_service() {
  case "$OS" in
    alpine) rc-service "$APP" restart ;;
    debian) systemctl restart "$APP" ;;
  esac
}

uninstall_service() {
  case "$OS" in
    alpine)
      rc-service "$APP" stop 2>/dev/null || true
      rc-update del "$APP" default 2>/dev/null || true
      rm -f "/etc/init.d/$APP"
      ;;
    debian)
      systemctl disable --now "$APP" 2>/dev/null || true
      rm -f "/etc/systemd/system/$APP.service"
      systemctl daemon-reload
      ;;
  esac
}

# ---- 共通処理 ---------------------------------------------------------------
# ソースを取得して $APP_DIR へ配置する (設定と DB には触れない)
fetch_source() {
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  if [ -n "${SRC_TARBALL:-}" ]; then
    log "ローカル tarball を使用: $SRC_TARBALL"
    tar -xzf "$SRC_TARBALL" -C "$tmp" --strip-components=1
  else
    log "ソースを取得: $REPO@$REPO_REF"
    curl -fsSL "https://github.com/$REPO/archive/$REPO_REF.tar.gz" |
      tar -xzf - -C "$tmp" --strip-components=1
  fi
  [ -f "$tmp/src/main.py" ] && [ -f "$tmp/requirements.txt" ] ||
    die "取得したソースに src/main.py または requirements.txt がありません"

  mkdir -p "$APP_DIR"
  rm -rf "$APP_DIR/src"
  cp -R "$tmp/src" "$APP_DIR/src"
  cp "$tmp/requirements.txt" "$APP_DIR/requirements.txt"
}

setup_venv() {
  log "Python 仮想環境を構築"
  [ -x "$APP_DIR/venv/bin/python" ] || python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir --upgrade pip
  "$APP_DIR/venv/bin/pip" install --quiet --no-cache-dir -r "$APP_DIR/requirements.txt"
}

# TOKEN が設定済みか
token_configured() {
  [ -f "$ENV_FILE" ] && grep -q '^TOKEN=.\{1,\}' "$ENV_FILE"
}

# 設定ファイルを未存在の場合のみ生成する
write_env() {
  mkdir -p "$CONF_DIR" "$DATA_DIR"
  if [ -f "$ENV_FILE" ]; then
    log "既存の設定を保持: $ENV_FILE"
  else
    token="${TOKEN:-}"
    # curl | sh の場合でも端末があれば TOKEN を尋ねる
    if [ -z "$token" ] && [ -t 1 ] && (: </dev/tty) 2>/dev/null; then
      printf 'Discord bot の TOKEN を入力してください (空欄で後から設定): ' >/dev/tty
      read -r token </dev/tty || token=""
    fi
    umask 077
    cat >"$ENV_FILE" <<EOF
TOKEN=$token
GUILD_ID=${GUILD_ID:-}
LOG_LEVEL=${LOG_LEVEL:-INFO}
TZ=Asia/Tokyo
DB_PATH=$DATA_DIR/kaikei.db
EOF
    log "設定ファイルを作成: $ENV_FILE"
  fi
  chown -R "$APP_USER:$APP_USER" "$CONF_DIR" "$DATA_DIR"
  chmod 700 "$CONF_DIR"
  chmod 600 "$ENV_FILE"
}

do_install() {
  install_packages
  add_user
  fetch_source
  setup_venv
  write_env
  chown -R root:root "$APP_DIR"
  install_service
  if token_configured; then
    log "サービスを起動"
    restart_service
    log "完了しました"
  else
    warn "TOKEN が未設定のためサービスは起動していません"
    warn "$ENV_FILE の TOKEN を設定し、再度このスクリプトを実行するかサービスを再起動してください"
  fi
}

do_uninstall() {
  uninstall_service
  rm -rf "$APP_DIR"
  rm -f "$LOG_FILE"
  if [ "$purge" = 1 ]; then
    rm -rf "$CONF_DIR" "$DATA_DIR"
    if id "$APP_USER" >/dev/null 2>&1; then
      case "$OS" in
        alpine) deluser "$APP_USER" >/dev/null 2>&1 || true ;;
        debian) userdel "$APP_USER" >/dev/null 2>&1 || true ;;
      esac
    fi
    log "設定と DB を含めて削除しました"
  else
    log "削除しました (設定 $CONF_DIR と DB $DATA_DIR は残しています。完全に消すには --purge)"
  fi
}

# ---- エントリポイント -------------------------------------------------------
uninstall=0
purge=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) uninstall=1 ;;
    --purge) purge=1 ;;
    -h | --help)
      cat <<EOF
使い方 (root で実行):
  TOKEN=xxxx sh install.sh          インストール / アップデート
  sh install.sh --uninstall         サービスとプログラムを削除 (設定と DB は残す)
  sh install.sh --uninstall --purge 設定と DB も含めて完全に削除
EOF
      exit 0
      ;;
    *) die "不明な引数です: $arg" ;;
  esac
done

[ "$(id -u)" = 0 ] || die "root で実行してください"
detect_os

if [ "$uninstall" = 1 ]; then
  do_uninstall
else
  do_install
fi
