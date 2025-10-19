"""
LINE Bot 通知に関する設定モジュール。

提供内容:
- LINE Messaging API へのブロードキャスト送信で利用するトークンやエンドポイントの集中管理。
- `.env` を使わずコード内定数で設定を保持する運用前提。

利用方法:
- `LineBotConfig` のクラス属性にアクセストークン・ユーザーIDを直接記載。
- テスト環境では `ENABLE_PUSH` を False のままにし、実運用時に True へ切り替える。
"""


class LineBotConfig:
    """LINE Bot 通知設定をまとめるクラス。

    責務:
    - アクセストークンなど通知に必要な値を集中管理する。
    - .env ではなくコード内で明示的に設定し、バージョン管理しやすくする。

    想定ユースケース:
    - `src.notification.line_bot.LineBotNotifier` から参照して送信可否/値を判断する。

    注意:
    - セキュリティ上、公開リポジトリに実値をコミットしないこと。
    - 実環境では CI/CD などで安全に値を流し込み、ここを上書きする仕組みを用意する。
    """

    # 通知機能の有効フラグ。導入時は False で安全側に倒し、動作確認後 True へ変更。
    ENABLE_PUSH: bool = True

    # LINE Messaging API のチャネルアクセストークン（長期トークンを想定）。
    CHANNEL_ACCESS_TOKEN: str = "nRseXzbetILcUmRuN4MP47B8R92MCKkxC9g5MoqdLdwIsziyPt46eJR40qcwjY9m0Ze4h1r7lCA2Llhi+hgUnTTqvWa2aGFeouNZzNYSiN/aQIFpzAqSsinAKHWvPvpwE70gXyK2Q81NH9INWT425AdB04t89/1O/w1cDnyilFU="

    # Messaging API ブロードキャストエンドポイント。通常は固定。
    API_ENDPOINT: str = "https://api.line.me/v2/bot/message/broadcast"

    # HTTP リクエストのタイムアウト秒数。環境によって調整可能。
    TIMEOUT_SEC: float = 5.0
