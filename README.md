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
CHANNEL_ID=XXXXXXXXXXXXXXX
```

`GUILD_ID`を指定すると、スラッシュコマンドがそのギルド専用コマンドとして即座に反映されます（グローバルコマンドはDiscord側の反映に最大1時間程度かかるため、動作確認や開発時に有用です）。未指定の場合はグローバルコマンドとして登録されます。

`CHANNEL_ID`を指定すると、起動時・終了時メッセージを送信します。

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

## 開発

### テストの実行

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```
