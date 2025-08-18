# TODOリスト

今後の開発に必要なタスクは以下の通りです。

## 1. 依存関係のインストール

Webアプリケーション（Flask）を動作させるために、必要なライブラリをインストールします。

```bash

# 仮想環境の作成
python -m venv venv


# 仮想環境を有効化
.\venv\Scripts\Activate.ps1 

# requirements.txt に Flask を追記
echo "Flask>=2.3" >> requirements.txt

# 依存関係をインストール
pip install -r requirements.txt
```

## 2. 静的ファイルの配置

Webインターフェースで使用する画像と音声ファイルを `webapp/static/` フォルダに配置してください。

- `webapp/static/customer.png` （顧客アバター画像）
- `webapp/static/clerk.png` （店員アバター画像）
- `webapp/static/notify.mp3` （ログ更新時の通知音）

## 3. 動作確認

各機能を個別に起動して、正しく動作するか確認します。

### a. 音声認識とキーワード検知

ターミナルで以下のコマンドを実行し、マイクからの音声入力に対してキーワード検知とログ記録が行われることを確認します。

```bash
python main.py
```

### b. Webログビューア

別のターミナルで以下のコマンドを実行し、Webサーバーを起動します。

```bash
python webapp/app.py
```

その後、Webブラウザで `http://127.0.0.1:5000` にアクセスし、記録されたログが表示されることを確認してください。

## 4. (任意) systemdによる自動起動設定

Raspberry Piで運用する際は、OS起動時に自動でプログラムが実行されるように設定すると便利です。
必要に応じて、`main.py` と `webapp/app.py` をサービスとして登録してください。
