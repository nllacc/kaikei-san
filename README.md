# kaikei-san

## 概要

- 会計さんは、Discordサーバー上でユーザー間の金銭の貸し借りを記録し、貸し借り状況のサマリーや履歴を確認できるbotです。
- 貸し借りの記録はDiscordサーバー（ギルド）ごとに分離され、複数の相手との貸し借りを同時に扱えます。
- データはSQLiteデータベースに永続化されます（Discordチャンネルの発言履歴には依存しません）。
- 詳細な設計は [spec.md](spec.md) を参照してください。

## コマンド

| コマンド | 説明 |
|---|---|
| `/lend user:@相手 amount:金額 memo:名目` | 相手にお金を貸した記録を追加します |
| `/borrow user:@相手 amount:金額 memo:名目` | 相手からお金を借りた記録を追加します |
| `/kaikei` | 自分視点の貸し借りサマリー（相手ごとの差引残高）を表示します |
| `/history` | 自分が関与した貸し借り記録をテキストファイルで出力します |

## 使用方法

Docker 動作環境のある、24 時間稼働するコンピュータ上で実行してください。

### build & deploy

Discord developer hub よりアプリケーションを作成し、以下の権限を持ったアクセストークンを取得してください。

- `applications.commands`
- `bot`
  - Send Messages（コマンドへの応答に必須）
  - Attach Files（`/history` のファイル添付に必須）

リポジトリをクローンします。

```sh
git clone
cd kaikei-san
```

`kaikei-san`ディレクトリへ`.env`ファイルを作成してください。

```env
TOKEN=XXXXXXXXXXXXXXX
GUILD_ID=XXXXXXXXXXXXXXX
LOG_LEVEL=INFO
```

`GUILD_ID`を指定すると、スラッシュコマンドがそのギルド専用コマンドとして即座に反映されます（グローバルコマンドはDiscord側の反映に最大1時間程度かかるため、動作確認や開発時に有用です）。未指定の場合はグローバルコマンドとして登録されます。

コンテナを起動します。

```sh
docker-compose up -d
```

データベース（SQLiteファイル）は Docker named volume（`kaikeisan-data`）に永続化されるため、コンテナを再作成してもデータは失われません。

### ログの閲覧

以下のコマンドを実行します。
```sh
docker-compose logs
```

### destroy

コンテナを停止・破棄します（データベースを含む volume は保持されます）。

```sh
docker-compose down --rmi all
```

データベースの内容ごと完全に削除する場合は、以下も実行してください。

```sh
docker volume rm kaikeisan_kaikeisan-data
```

## 重複起動について

同じ TOKEN の bot は 1 つだけ稼働させてください（Docker 版と LXC / VM 版を同時に動かさないでください）。複数稼働していると、コマンドを最初に受け付けたインスタンスだけが記録・応答し、他のインスタンスは処理を中断して以下のようなエラーログを出力します。このログが出た場合は、別ホストも含めて他に稼働しているインスタンスを停止してください。

```
ERROR command=lend guild_id=... user_id=... 応答の確保に失敗したため処理を中断しました。同じTOKENで別のインスタンスが稼働している可能性があります (status=400 code=40060)
```

## LXC / VM へのインストール (Alpine・Ubuntu・Debian)

Docker を使わず、Alpine / Ubuntu / Debian の LXC コンテナや VM へ直接インストールできます。
root で以下を実行してください（Alpine は OpenRC、Ubuntu / Debian は systemd のサービスとして登録されます）。
`TOKEN` は `--set` ではなく環境変数で渡してください（`--set` の値はプロセス一覧やシェルの履歴に残ります）。

```sh
wget -qO- https://github.com/nllacc/kaikei-san/releases/latest/download/install.sh | sudo env TOKEN=XXXXXXXXXXXXXXX sh -s -- install
```

- curl がある環境では `curl -fsSL <URL> | sudo env TOKEN=… sh -s -- install` でも同じです。
- 版を固定する場合は `…/releases/download/<タグ>/install.sh` を使います。
- 開発中のブランチを導入する場合は `install --ref <ブランチ名>` を付けます。

導入後は常設コマンド `kaikei-san-ctl` で操作します。

| 操作 | コマンド |
|---|---|
| 更新（導入中のタグ・ブランチの最新へ） | `sudo kaikei-san-ctl update` |
| タグ・ブランチの切り替え | `sudo kaikei-san-ctl update --ref <名前>` |
| 状態の表示 | `sudo kaikei-san-ctl status` |
| 取得元のタグ・ブランチの一覧 | `sudo kaikei-san-ctl refs` |
| 削除（設定とデータベースを残す） | `sudo kaikei-san-ctl uninstall` |
| 完全に削除 | `sudo kaikei-san-ctl uninstall --purge` |

設定ファイル `/etc/kaikei-san/kaikei-san.env` のキーは次のとおりです。手で編集した後は `sudo kaikei-san-ctl update` を実行すると反映されます（サービスが再起動されます）。

| キー | 既定値 | 内容 |
|---|---|---|
| `TOKEN` | （必須） | Discord bot のトークン |
| `GUILD_ID` | 空 | コマンドを登録するサーバ（ギルド）の ID（空なら全サーバ） |
| `LOG_LEVEL` | `INFO` | ログの出力レベル（`DEBUG`・`INFO`・`WARNING`・`ERROR`） |

### Docker 版とホスト版の対応

| 項目 | Docker 版 | ホスト版 |
|---|---|---|
| 設定 | `.env`（compose の `environment:` の `TOKEN`・`GUILD_ID`・`LOG_LEVEL`） | `/etc/kaikei-san/kaikei-san.env` の同じキー |
| プログラム | イメージ内の `/workspace` | `/opt/kaikei-san`（venv は `/opt/kaikei-san/venv`） |
| データベース | ボリューム `kaikeisan-data`（`/workspace/data/kaikei.db`） | `/var/lib/kaikei-san/kaikei.db` |
| ログ | `docker compose logs` | Ubuntu / Debian は `journalctl -u kaikei-san`、Alpine は syslog（`/var/log/messages` の `kaikei-san` の行） |
| 再起動 | `docker compose restart` | Ubuntu / Debian は `systemctl restart kaikei-san`、Alpine は `rc-service kaikei-san restart` |
| 実行ユーザー | コンテナの root | `kaikei-san` |
| タイムゾーン | `TZ=Asia/Tokyo` | `TZ=Asia/Tokyo` |

## バックアップ / 復元

データベース（SQLite）をファイルへ出力・復元するスクリプト [scripts/backup.sh](scripts/backup.sh) を用意しています。
docker-compose 構成と LXC / VM（ホスト版）構成のどちらでも同じコマンドで使え、構成は自動判別されます
（両方が存在する場合は `--mode docker` または `--mode native` で指定してください）。
稼働中でも整合性のあるバックアップを取得できます。

```sh
# バックアップ（出力先省略時は ./kaikei-日時.db）
sh scripts/backup.sh backup
sh scripts/backup.sh backup /path/to/kaikei.db

# 復元（サービスを一時停止して差し替え、完了後に再開します）
sh scripts/backup.sh restore /path/to/kaikei.db
```

- 復元前に、現在のDBがカレントディレクトリへ `kaikei-pre-restore-日時.db` として自動退避されます。
- 復元時は入力ファイルの整合性（`integrity_check` と `transactions` テーブルの有無）を検証します。確認プロンプトは `--yes` で省略できます。
- docker 構成では `docker-compose.yaml` のあるリポジトリ内で実行してください（`COMPOSE_FILE` で別ファイルも指定可）。
- ホスト版では root で実行してください。スクリプトは導入先の `/opt/kaikei-san/scripts/backup.sh` にあります。

## 開発

### テストの実行

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```
