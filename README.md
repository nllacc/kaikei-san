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

## LXC / VM へのインストール (Alpine・Ubuntu・Debian)

Docker を使わず、Alpine / Ubuntu / Debian の LXC コンテナや VM へ直接インストールできます。
root で以下を実行してください（Alpine は OpenRC、Ubuntu / Debian は systemd のサービスとして登録されます）。

```sh
wget -O - https://github.com/nllacc/kaikei-san/releases/download/main/install.sh | TOKEN=XXXXXXXXXXXXXXX sh
```

`TOKEN` のほか、`GUILD_ID`・`LOG_LEVEL` も同様に環境変数で渡せます（初回の設定ファイル生成時のみ使用）。
`TOKEN` を省略して端末から実行した場合は入力を求められます。

| 項目 | パス |
|---|---|
| プログラム | `/opt/kaikei-san` |
| 設定 (`.env` 相当) | `/etc/kaikei-san/kaikei-san.env` |
| データベース | `/var/lib/kaikei-san/kaikei.db` |

- 更新: 同じコマンドを再実行します（設定とデータベースは保持されます）。特定バージョンは `REPO_REF=v1.0.0` で指定できます。
- ログ: Alpine は `/var/log/kaikei-san.log`、Ubuntu / Debian は `journalctl -u kaikei-san`
- 設定変更後の再起動: Alpine は `rc-service kaikei-san restart`、Ubuntu / Debian は `systemctl restart kaikei-san`
- 削除: `sh install.sh --uninstall`（設定とデータベースを残す）／ `sh install.sh --uninstall --purge`（すべて削除）

## バックアップ / 復元

データベース（SQLite）をファイルへ出力・復元するスクリプト [scripts/backup.sh](scripts/backup.sh) を用意しています。
docker-compose 構成と LXC / VM（`install.sh`）構成のどちらでも同じコマンドで使え、構成は自動判別されます
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
- `install.sh` 構成では root で実行してください。インストーラはこのスクリプトを配置しないため、次のように取得できます。

  ```sh
  wget -O backup.sh https://raw.githubusercontent.com/nllacc/kaikei-san/main/scripts/backup.sh
  ```

## 開発

### テストの実行

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```
