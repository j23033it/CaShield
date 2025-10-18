"""
LINE Bot を用いた通知送信モジュール。

このモジュールでは、カスハラ検出イベントを LINE Messaging API のブロードキャスト
メッセージで友だち全員へ伝達するためのヘルパークラスを提供する。

入出力:
- 入力: 検出日時、検出ワード一覧、全文テキスト。
- 出力: LINE への HTTP リクエスト（Push メッセージ）。

設計方針:
- .env は使用せず、`src.config.notification.LineBotConfig` で設定を集中管理する。
- 標準ライブラリ（urllib）で HTTP を行い、追加依存を増やさない。
- 例外は握り、監視本体の処理を止めないようにする。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, Optional
from urllib import error, request

from src.config.notification import LineBotConfig


class LineBotNotifier:
    """LINE Messaging API へブロードキャスト通知を送る小さなヘルパークラス。

    責務:
    - `send_detection_alert()` で検出内容を日本語テキストに整形しブロードキャスト API を呼び出す。
    - 設定が未入力の場合は安全側で送信をスキップし、実行時例外を避ける。

    想定ユースケース:
    - `ActionManager.log_detection()` などが検出直後に呼び出し、監視者へ即座に通知する。
    """

    def __init__(self, cfg: Optional[LineBotConfig] = None) -> None:
        """設定オブジェクトを受け取って初期化する。

        引数:
            cfg: `LineBotConfig` または同等の属性を持つオブジェクト。
        副作用:
            なし。設定は参照のみ。
        """
        self.cfg = cfg or LineBotConfig()

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def send_detection_alert(
        self,
        detected_at: datetime,
        detected_words: Iterable[str],
        full_text: str,
    ) -> None:
        """カスハラ検出内容を LINE Bot で送信する。

        引数:
            detected_at: 検出日時（ローカルタイム想定）。
            detected_words: 検出された NG ワード群。
            full_text: 文字起こし全文。

        処理の流れ:
        1. 設定値が揃っているか検証し、未設定なら何もせず終了。
        2. LINE 用文章を組み立て、Push API の JSON ペイロードを作成。
        3. HTTP POST を発行し、エラー時は標準出力へ警告を出す。
        """
        if not self._is_ready():
            # 設定未完了時は安全にスキップ（例: テスト環境）。
            print("[LINE] Broadcast設定が揃っていないため送信をスキップしました。")
            return

        # LINE へ送る文章を生成（通知要件に合わせ日時と検出ワードのみを含める）。
        message_text = self._format_message(detected_at, detected_words, full_text)

        # ブロードキャスト API の仕様に従った JSON ペイロードを構築。
        payload = {
            "messages": [
                {
                    "type": "text",
                    "text": message_text,
                }
            ],
        }

        # JSON を bytes へエンコード。
        data = json.dumps(payload).encode("utf-8")

        # HTTP ヘッダーにアクセストークンを付与し、POST リクエストを準備。
        req = request.Request(
            self.cfg.API_ENDPOINT,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.cfg.CHANNEL_ACCESS_TOKEN}",
            },
        )

        try:
            # タイムアウトを設けて送信（通信不達で監視が停止しないようにする）。
            with request.urlopen(req, timeout=self.cfg.TIMEOUT_SEC) as resp:
                # レスポンスボディは特に使用しないが、デバッグ時に備えてステータスだけ通知。
                print(f"[LINE] Broadcast送信ステータス: {resp.status}")
        except error.HTTPError as http_err:
            # HTTP ステータス異常時は内容をログ出力。
            print(
                "[LINE] Broadcast送信失敗: "
                f"status={http_err.code} body={http_err.read().decode('utf-8', errors='ignore')}"
            )
        except error.URLError as url_err:
            print(f"[LINE] Broadcast送信失敗: {url_err.reason}")
        except Exception as exc:
            print(f"[LINE] Broadcast送信中に予期しない例外: {exc}")

    # ------------------------------------------------------------------
    # 内部ユーティリティ
    # ------------------------------------------------------------------
    def _is_ready(self) -> bool:
        """設定が揃っていて送信可能か判定する。"""
        enabled = bool(getattr(self.cfg, "ENABLE_PUSH", False))
        token = str(getattr(self.cfg, "CHANNEL_ACCESS_TOKEN", ""))
        return enabled and bool(token.strip())

    def _format_message(
        self,
        detected_at: datetime,
        detected_words: Iterable[str],
        full_text: str,
    ) -> str:
        """LINEへ送る本文を整形する。"""
        # 入力全文は通知本体に含めないが、将来互換性のため引数として受け取る。
        # リストをカンマ区切りに整形。検出無しの場合は「該当なし」と記載。
        words = list(detected_words)
        words_text = ", ".join(words) if words else "該当なし"
        timestamp = detected_at.strftime("%Y-%m-%d %H:%M:%S")

        # 通知要件に合わせ、発生日時と検出ワードのみを返す。
        return (
            "カスハラ検出を通知します\n"
            f"発生日時: {timestamp}\n"
            f"検出ワード: {words_text}"
        )
