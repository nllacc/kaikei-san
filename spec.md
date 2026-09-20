# kaikei-san 設計書

## 1. 概要

kaikei-san は [py-cord](https://pycord.dev/) を使ったDiscord botアプリケーションである。Discordサーバー上にデーモンとして常時稼働し、スラッシュコマンドによってユーザー間の金銭の貸し借りを記録・集計する。

### 現行実装の課題

現行の `src/main.py` は以下のような設計になっている。

- 「帳簿」役のDiscordチャンネルへ `貸 1000 ラーメン代` のような平文メッセージを書き込み、`/kaikei` 実行時にチャンネル履歴（最大500件）をパースして残高を計算している
- `/shiwake` コマンドが「貸/借」をパラメータとして受け取る単一コマンドになっており、パラメータ数が多く煩雑
- **どのユーザーが誰に対して貸し借りしたかを一切記録していない**。チャンネル全体で単一の残高しか持てず、実質2人用の設計にとどまっている
- 永続化層がDiscordのメッセージ履歴そのものであり、構造化されたDB・ORMが存在しない。手動でチャンネルに書き込むと壊れる、履歴の上限（500件）を超えると集計が破綻する等の脆弱性がある
- 「仕訳」「帳簿」「総」「集計」といった会計専門用語がそのままコマンド名・出力に使われており、直感的でない

### 解決方針

- 貸し借りの記録に「誰が・誰に対して」を持たせ、複数ユーザー・複数の相手との貸し借りを同時に扱えるようにする
- 「借りた/貸した」を別コマンドに分割し、各コマンドのパラメータを削減する
- 永続化をDiscordチャンネル依存からSQLiteデータベース（Dockerボリュームで永続化）に置き換える
- 用語をわかりやすいものに統一する

## 2. 用語整理

現行の「仕訳/帳簿/総/集計」といった会計専門用語を減らし、以下の用語に統一する。

| 用語 | 意味 |
|---|---|
| 貸し (lend) | コマンド実行者が相手にお金を貸す行為 |
| 借り (borrow) | コマンド実行者が相手からお金を借りる行為 |
| 相手 (counterparty) | 貸し借りの相手ユーザー |
| 記録 (record) | 1回の貸し借り登録（DBの1行） |
| 差引残高 (net balance) | ある相手との貸し借りをすべて合算した最終的な貸し借り額 |

## 3. コマンド仕様

貸し借りの記録は、対象サーバー（Discordギルド）単位で分離する。異なるサーバーでbotを利用しても、記録が混ざることはない。

### `/lend` — 貸した記録を追加

```
/lend user:@対象ユーザー amount:金額 memo:名目
```

- `user`（必須, ユーザー型）: 貸した相手
- `amount`（必須, 整数）: 金額（円、正の整数）
- `memo`（必須, 文字列）: 名目

実行者が `user` に対して `amount` 円を貸したことを記録する。自分自身を `user` に指定した場合はエラーを返し、記録しない。登録後、実行者に登録内容を確認メッセージとして返信する。

### `/borrow` — 借りた記録を追加

```
/borrow user:@対象ユーザー amount:金額 memo:名目
```

- パラメータは `/lend` と同一（`user` は借りた相手）

実行者が `user` から `amount` 円を借りたことを記録する。自分自身を `user` に指定した場合はエラーを返す。登録後、実行者に登録内容を確認メッセージとして返信する。

### `/kaikei` — 貸し借りサマリーを表示

```
/kaikei
```

- パラメータなし

実行ユーザー視点での貸し借りサマリーを表示する。記録のある相手ごとに、差引残高（合計金額・貸しているか借りているか）を一覧表示する。

- 差引残高が0の相手は表示しない
- 記録が一件もない場合は「貸し借りはありません」の旨を返す
- 相手の表示はDiscordメンション形式（`<@user_id>`）を使う

出力イメージ:

```
あなたの貸し借り状況:
- <@太郎のID> に 3,000円 貸しています
- <@花子のID> から 1,500円 借りています
```

### `/history` — 貸し借り記録をファイルで出力

```
/history [month:対象年月]
```

- `month`（任意, 文字列, プルダウン選択）: 対象年月。直近12ヶ月分の `YYYY-MM` と `all` の中から選択する（自由入力不可）
  - 省略時: 直近30日分の記録を出力する
  - `YYYY-MM` を指定: 指定した年月（日本時間basisのカレンダー月）の記録のみを出力する
  - `all` を指定: 実行ユーザーが関与した記録を全件出力する（`month` 追加前の挙動と同一）

実行ユーザーが関与した（貸した側・借りた側のいずれかである）貸し借り記録を、`month` で指定した範囲に絞り込んだ上で日時順にテキストファイルへ出力し、`ctx.respond` の添付ファイルとして実行ユーザーに返す。

- チャット本文には出さず、ファイル添付のみとする。記録件数が多くなるとDiscordのメッセージ文字数制限（2,000字）を超える恐れがあるため
- 出力形式（1行1記録）: `日時 | 相手 | 貸した/借りた | 金額 | 名目`
  - 例: `2026-09-06 12:00 | @taro | 貸した | 1000円 | ラーメン代`
- 該当記録が0件の場合はファイルを添付せず、「記録がありません」とテキストのみで返信する
- `month` のプルダウン選択肢はbot起動時（コマンド登録時）を基準にした直近12ヶ月分であり、botを再起動すると選択肢の月がロールする

## 3.1. ログ出力

`/lend` `/borrow` `/kaikei` `/history` のいずれかが実行された場合、サーバ側の標準出力へ操作記録を info レベルのログとして出力する。ログには実行ギルドID・実行ユーザーID・コマンド固有パラメータ（金額、相手ユーザー、`month` 指定値など）を含める。ユーザー操作以外（起動時など）のログは debug レベルとする。ログのタイムスタンプはDocker側（`docker compose logs --timestamps` 等）で付与する前提とし、アプリケーション側では付与しない。

出力する最低ログレベルは環境変数 `LOG_LEVEL` で調整する（未設定時は `INFO`）。Pythonの `logging` モジュール標準のレベル名（`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`）を指定し、指定したレベル以上のログのみが出力される（例: `WARNING` を指定した場合は `WARNING` と `ERROR`/`CRITICAL` のみ出力され、コマンド操作ログ(`INFO`)は出力されない）。

## 4. データモデル（SQLite）

テーブル `transactions`（1レコード = 1回の貸し借り登録）。`/lend`・`/borrow` のどちらで登録されたかに関わらず、「貸した人（creditor）」「借りた人（debtor）」で正規化して保持する。

| カラム | 型 | 説明 |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | 記録ID |
| guild_id | BIGINT NOT NULL | DiscordサーバーID。サーバー単位で貸し借りを分離するためのスコープキー |
| creditor_id | BIGINT NOT NULL | 貸した人（お金を受け取る権利がある人）のDiscordユーザーID |
| debtor_id | BIGINT NOT NULL | 借りた人（お金を返す義務がある人）のDiscordユーザーID |
| amount | INTEGER NOT NULL | 金額（円、正の整数） |
| memo | TEXT | 名目 |
| created_by | BIGINT NOT NULL | コマンドを実行したユーザーID（`/lend`ならcreditor、`/borrow`ならdebtorと一致） |
| created_at | DATETIME NOT NULL | 記録日時 |

### 記録ルール

- `/lend user=B amount=1000 memo=ラーメン代`（実行者A） → `creditor_id=A, debtor_id=B, amount=1000`
- `/borrow user=B amount=1000 memo=ラーメン代`（実行者A） → `creditor_id=B, debtor_id=A, amount=1000`

### サマリー計算（`/kaikei`）

実行ユーザーUについて、相手ごとに以下を `guild_id` でスコープして算出する。

```
差引残高 = SUM(amount WHERE creditor_id = U) - SUM(amount WHERE debtor_id = U)
```

- 差引残高が正 → 相手に「貸している」
- 差引残高が負 → 相手から「借りている」（絶対値を表示）

### 履歴取得（`/history`）

`guild_id` でスコープし、`creditor_id = U OR debtor_id = U` を満たす記録を `created_at` の昇順で全件取得する。

## 5. アプリケーション構成

現行は `src/main.py` 1ファイルにbot定義・コマンド・ロジックがすべて入っている。以下のように分割する。

```
kaikei-san/
├── requirements.txt      # 依存関係をpin
├── docker-compose.yaml
├── Dockerfile
├── spec.md
├── README.md
└── src/
    ├── main.py           # bot初期化・起動・コマンド登録のエントリポイント
    ├── db.py             # SQLite接続・テーブル初期化
    └── repository.py     # DBアクセスをカプセル化する関数群
```

- `src/db.py`: SQLite接続の確立、起動時の `CREATE TABLE IF NOT EXISTS transactions (...)` によるテーブル初期化を担う
- `src/repository.py`: 以下の関数を提供する
  - `add_transaction(guild_id, creditor_id, debtor_id, amount, memo, created_by)`
  - `get_summary(guild_id, user_id)` — `/kaikei` 用。相手ごとの差引残高一覧を返す
  - `get_user_history(guild_id, user_id)` — `/history` 用。ユーザーが関与した記録を日時昇順で全件返す
- `requirements.txt`: `py-cord` を含む依存関係のバージョンを明示的にpinする（現行Dockerfileは `pip install --upgrade` により無pinでビルドごとにバージョンが変わりうる）

## 6. 永続化・Docker構成

- SQLiteのデータファイルをDockerの名前付きボリュームにマウントして永続化する（例: コンテナ内パス `/workspace/data/kaikei.db`）
- `docker-compose.yaml` にボリューム定義を追加する。DB用の別サービスは追加せず、botコンテナ内のSQLiteファイルを永続ボリューム上に配置する構成とする
- `Dockerfile` は `requirements.txt` を用いて依存関係をpinしてインストールする形に変更する

## 7. 移行方針

現行の「帳簿チャンネル」に蓄積された貸し借りデータの移行スクリプトは本設計の対象外とする。新設計への切り替え後は、新規の貸し借りから新しいデータモデルで運用を開始する前提とする。
