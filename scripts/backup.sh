#!/bin/sh
# kaikei-san データベース バックアップ / 復元スクリプト
#
# docker-compose 構成と install.sh 構成 (Alpine / Ubuntu / Debian) の両方に対応する。
#
# 使い方:
#   sh backup.sh backup [出力ファイル]   DB をファイルへ出力 (既定: ./kaikei-日時.db)
#   sh backup.sh restore <入力ファイル>  ファイルから DB を復元
#
# オプション:
#   --mode docker|native  構成を明示 (省略時は自動判別)
#   --yes                 restore の確認プロンプトを省略
#
# 環境変数:
#   KAIKEI_DB_PATH        native 構成の DB パス (既定: /var/lib/kaikei-san/kaikei.db)
#   KAIKEI_SKIP_SERVICE=1 native 構成の restore でサービスの停止/起動を行わない (検証用)
#   COMPOSE_FILE          docker 構成で使う compose ファイル (既定: リポジトリの docker-compose.yaml)
#
# 備考: 稼働中でも整合性のあるバックアップを取れるよう、SQLite の online backup API を使う。
set -eu

APP=kaikei-san
SERVICE=kaikeisan
DB_PATH="${KAIKEI_DB_PATH:-/var/lib/$APP/kaikei.db}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/docker-compose.yaml}"
DOCKER_DB=/workspace/data/kaikei.db

log() { printf '==> %s\n' "$*"; }
warn() { printf '警告: %s\n' "$*" >&2; }
die() {
  printf 'エラー: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<EOF
使い方:
  sh backup.sh backup [出力ファイル]   DB をファイルへ出力 (既定: ./kaikei-日時.db)
  sh backup.sh restore <入力ファイル>  ファイルから DB を復元

オプション:
  --mode docker|native  構成を明示 (省略時は自動判別)
  --yes                 restore の確認プロンプトを省略
EOF
}

# ---- Python スニペット (docker コンテナ / native 共通) -----------------------
# 引数: 元DB 出力先 [uid gid] (docker では root 所有になるため呼び出し元へ chown する)
PY_BACKUP='
import os, sqlite3, sys
if not os.path.exists(sys.argv[1]):
    sys.exit(3)
src = sqlite3.connect(sys.argv[1])
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close()
src.close()
if len(sys.argv) > 4:
    os.chown(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
'
# 引数: DB。整合性と transactions テーブルを検証し、件数を表示する
PY_VERIFY='
import sqlite3, sys
c = sqlite3.connect("file:" + sys.argv[1] + "?mode=ro", uri=True)
try:
    if c.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        sys.exit("integrity_check に失敗しました")
    print(c.execute("SELECT count(*) FROM transactions").fetchone()[0])
except sqlite3.Error as e:
    sys.exit("SQLite として不正です: %s" % e)
'
# 引数: 入力 出力先。一時ファイル経由で置換し、古い WAL/SHM を除去する
PY_PLACE='
import os, shutil, sys
shutil.copyfile(sys.argv[1], sys.argv[2] + ".new")
os.replace(sys.argv[2] + ".new", sys.argv[2])
for s in ("-wal", "-shm"):
    if os.path.exists(sys.argv[2] + s):
        os.remove(sys.argv[2] + s)
'

# ---- docker 構成 ------------------------------------------------------------
dc() {
  (cd "$ROOT" && $DC -f "$COMPOSE_FILE" "$@")
}

# 使い捨てコンテナで python を実行: docker_py <code> <追加 -v>... -- <args>...
docker_py() {
  code="$1"
  shift
  mounts=""
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do
    mounts="$mounts -v $1"
    shift
  done
  shift
  # shellcheck disable=SC2086  # マウント指定は空白を含まない前提 (絶対パスの空白は事前に弾く)
  dc run --rm --no-deps -T $mounts --entrypoint python3 "$SERVICE" -c "$code" "$@"
}

detect_docker() {
  if docker compose version >/dev/null 2>&1; then
    DC="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    DC="docker-compose"
  else
    return 1
  fi
  [ -f "$COMPOSE_FILE" ] || return 1
  [ -n "$(dc ps -a -q "$SERVICE" 2>/dev/null)" ]
}

# ---- native 構成 ------------------------------------------------------------
detect_native() { [ -f "$DB_PATH" ]; }

native_py() {
  if [ -x "/opt/$APP/venv/bin/python" ]; then
    NPY="/opt/$APP/venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    NPY=python3
  else
    die "python3 が見つかりません"
  fi
  "$NPY" -c "$@"
}

svc_is_active() {
  if [ -r /etc/os-release ] && grep -qi alpine /etc/os-release; then
    rc-service "$APP" status >/dev/null 2>&1
  else
    systemctl is-active --quiet "$APP"
  fi
}

svc_ctl() { # start|stop
  [ "${KAIKEI_SKIP_SERVICE:-0}" = 1 ] && return 0
  if [ -r /etc/os-release ] && grep -qi alpine /etc/os-release; then
    rc-service "$APP" "$1"
  else
    systemctl "$1" "$APP"
  fi
}

# ---- 構成判別 ---------------------------------------------------------------
resolve_mode() {
  case "$mode" in
    docker | native) return 0 ;;
    "") ;;
    *) die "--mode は docker か native を指定してください: $mode" ;;
  esac
  d=0
  n=0
  detect_docker && d=1
  detect_native && n=1
  if [ "$d" = 1 ] && [ "$n" = 1 ]; then
    die "docker 構成と native 構成の両方が見つかりました。--mode で指定してください"
  elif [ "$d" = 1 ]; then
    mode=docker
  elif [ "$n" = 1 ]; then
    mode=native
  else
    die "DB が見つかりません (docker: コンテナ未作成 / native: $DB_PATH なし)。--mode で指定してください"
  fi
  log "構成を判別: $mode"
  # detect_docker が失敗した場合 DC が未設定のことがある
  if [ "$mode" = docker ] && [ -z "${DC:-}" ]; then
    detect_docker || true
  fi
}

# 絶対パス化 (ディレクトリは作成する)
abs_path() {
  dir="$(dirname "$1")"
  mkdir -p "$dir"
  printf '%s/%s\n' "$(cd "$dir" && pwd)" "$(basename "$1")"
}

# ---- backup / restore -------------------------------------------------------
# do_backup <出力ファイル(絶対パス)>
do_backup() {
  out="$1"
  case "$out" in *[[:space:]]*) die "パスに空白を含められません: $out" ;; esac
  [ ! -e "$out" ] || die "出力先が既に存在します: $out"
  rc=0
  if [ "$mode" = docker ]; then
    docker_py "$PY_BACKUP" "${DC_VOLUME}:/workspace/data" "$(dirname "$out"):/out" -- \
      "$DOCKER_DB" "/out/$(basename "$out")" "$(id -u)" "$(id -g)" || rc=$?
  else
    native_py "$PY_BACKUP" "$DB_PATH" "$out" || rc=$?
  fi
  # 3: 元の DB が存在しない (未初期化の volume など)
  [ "$rc" != 3 ] || return 3
  [ "$rc" = 0 ] || die "バックアップに失敗しました"
  count="$(verify_file "$out")" || {
    rm -f "$out"
    die "バックアップの検証に失敗しました"
  }
  chmod 600 "$out" || warn "権限を変更できませんでした: $out"
  log "バックアップしました: $out (transactions: ${count} 件)"
}

# verify_file <絶対パス>: 件数を標準出力へ
verify_file() {
  if [ "$mode" = docker ]; then
    docker_py "$PY_VERIFY" "$1:/in.db:ro" -- /in.db
  else
    native_py "$PY_VERIFY" "$1"
  fi
}

# 復元前に現行 DB を退避する (現行 DB が無ければ何もしない)
backup_current() {
  log "復元前の DB を退避: $pre"
  rc=0
  do_backup "$pre" || rc=$?
  [ "$rc" != 3 ] || log "現行の DB が存在しないため退避を省略"
}

do_restore() {
  in="$1"
  [ -f "$in" ] || die "入力ファイルが見つかりません: $in"
  in="$(abs_path "$in")"
  case "$in" in *[[:space:]]*) die "パスに空白を含められません: $in" ;; esac
  count="$(verify_file "$in")" || die "入力ファイルが正しい kaikei-san のDBではありません: $in"
  log "入力を検証しました (transactions: ${count} 件)"

  if [ "$assume_yes" != 1 ]; then
    printf '現在のDBを %s で置き換えます。よろしいですか? [y/N] ' "$in"
    read -r ans </dev/tty 2>/dev/null || ans=""
    case "$ans" in y | Y | yes) ;; *) die "中止しました" ;; esac
  fi

  ts="$(date +%Y%m%d-%H%M%S)"
  pre="$(abs_path "./kaikei-pre-restore-$ts.db")"

  if [ "$mode" = docker ]; then
    backup_current
    log "サービスを停止"
    dc stop "$SERVICE"
    docker_py "$PY_PLACE" "${DC_VOLUME}:/workspace/data" "$in:/restore/in.db:ro" -- \
      /restore/in.db "$DOCKER_DB"
    log "サービスを起動"
    dc start "$SERVICE"
  else
    [ "$(id -u)" = 0 ] || [ "${KAIKEI_SKIP_SERVICE:-0}" = 1 ] || die "root で実行してください"
    if [ -f "$DB_PATH" ]; then
      backup_current
      owner="$(stat -c '%u:%g' "$DB_PATH")"
    else
      owner=""
    fi
    was_active=0
    if [ "${KAIKEI_SKIP_SERVICE:-0}" != 1 ] && svc_is_active; then was_active=1; fi
    [ "$was_active" = 1 ] && {
      log "サービスを停止"
      svc_ctl stop
    }
    native_py "$PY_PLACE" "$in" "$DB_PATH"
    [ -z "$owner" ] || chown "$owner" "$DB_PATH" 2>/dev/null || true
    [ "$was_active" = 1 ] && {
      log "サービスを起動"
      svc_ctl start
    }
  fi
  log "復元しました: $in"
}

# ---- エントリポイント -------------------------------------------------------
mode=""
assume_yes=0
cmd=""
arg=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --mode)
      [ "$#" -ge 2 ] || die "--mode に値がありません"
      mode="$2"
      shift
      ;;
    --yes | -y) assume_yes=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*) die "不明なオプションです: $1" ;;
    *)
      if [ -z "$cmd" ]; then
        cmd="$1"
      elif [ -z "$arg" ]; then
        arg="$1"
      else
        die "引数が多すぎます: $1"
      fi
      ;;
  esac
  shift
done

case "$cmd" in
  backup | restore) ;;
  *)
    usage >&2
    exit 1
    ;;
esac

resolve_mode

# docker 構成: compose が作る named volume 名を取得する
DC_VOLUME=""
if [ "$mode" = docker ]; then
  [ -n "${DC:-}" ] || {
    if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
  }
  cid="$(dc ps -a -q "$SERVICE" | head -n 1)"
  [ -n "$cid" ] || die "コンテナが見つかりません: $SERVICE (docker-compose up -d を実行してください)"
  DC_VOLUME="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/workspace/data"}}{{.Name}}{{end}}{{end}}' "$cid")"
  [ -n "$DC_VOLUME" ] || die "データ用 volume を特定できません"
fi

case "$cmd" in
  backup)
    out="$(abs_path "${arg:-./kaikei-$(date +%Y%m%d-%H%M%S).db}")"
    do_backup "$out"
    ;;
  restore)
    [ -n "$arg" ] || die "復元するファイルを指定してください"
    do_restore "$arg"
    ;;
esac
