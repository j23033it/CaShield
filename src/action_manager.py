"""
警告音再生と検出ログの管理モジュール。

提供機能:
- トリガーワード検出時の「警告音」を非ブロッキングで再生（playsound ベース）。
- 検出ログ（原文・NGワード・役割）を日次ファイルへ追記。

設計方針:
- .env は使用せず、コード内の設定オブジェクト（AUDIO_CFG）に集約。
- 再生は別スレッドで行い、メイン処理（ASR/KWS）をブロックしない。
- playsound が利用できない環境では OS 別に軽量フォールバック（Windows: winsound.Beep / その他: ベル文字）。
"""

import os
import threading
from typing import Optional
import datetime

# ログ出力先
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


class AudioActionConfig:
    """警告音再生に関するコード内設定をまとめる小さな設定クラス。

    責務/ユースケース:
    - 再生バックエンドやビープ音の特性（周波数・長さ）を一箇所で管理する。
    - ActionManager から参照される読み取り専用の意図（コードで変更）。

    フィールド:
    - backend: 文字列。既定は 'playsound'（ロジック上も playsound を最優先）。
    - beep_freq_hz: Windows の winsound.Beep 用の周波数（Hz）。
    - beep_ms: Windows の winsound.Beep 用の持続時間（ms）。
    - use_thread: 再生を別スレッドで行うか（True で非ブロッキング）。
    """

    backend: str = "playsound"
    beep_freq_hz: int = 800
    beep_ms: int = 1000
    use_thread: bool = True


# 本モジュールのデフォルト設定（コード内で集中管理）
AUDIO_CFG = AudioActionConfig()


class ActionManager:
    """
    トリガーワード検出時のアクション（警告音再生・検出ログ）を管理するクラス。

    目的:
    - `play_warning()` で警告音を非ブロッキング再生。
    - `log_detection()` で検出内容を日次ファイルに追記。
    """

    def __init__(self, warning_sound_path: Optional[str] = None):
        """
        引数:
            warning_sound_path: 警告音ファイルのパス（オプション）。未指定時はビープへフォールバック。
        副作用:
            パスが存在しない場合は警告ログを出す。
        """
        self.warning_sound_path = warning_sound_path
        self._validate_sound_file()

    def _validate_sound_file(self) -> None:
        """警告音ファイルの存在を軽く検証し、無ければ警告を表示する。"""
        if self.warning_sound_path and not os.path.exists(self.warning_sound_path):
            print(f"[警告] 警告音ファイルが見つかりません: {self.warning_sound_path}")

    def play_warning(self) -> None:
        """警告音を再生する（playsound ベース、フォールバック付き）。

        処理の流れ（要約）:
        - ファイルパス未指定なら即ビープ。
        - 指定ありの場合、playsound で同期再生するが、呼び出しは別スレッドで行うため非ブロッキング。
        - playsound の ImportError/実行時例外は握って、OS 別のビープにフォールバック。
        """
        print("🚨 [警告音] トリガーワードが検出されました！")

        if not self.warning_sound_path:
            # ファイルが指定されていない場合はビープ音
            self._play_beep()
            return

        def _play():
            # バックグラウンドでの音声再生処理（同期APIだがスレッドで非ブロッキング化）
            try:
                # playsound を最優先で使用
                from playsound import playsound  # 例外時は下の except でフォールバック
                playsound(self.warning_sound_path)
            except Exception as e:
                # ImportError/OSError/バックエンド未整備など広く捕捉し、安全側に倒す
                print(f"🚨 [警告音] playsound 再生に失敗: {e}")
                self._play_beep()

        # 別スレッドで実行（メインスレッドをブロックしない）
        if AUDIO_CFG.use_thread:
            threading.Thread(target=_play, daemon=True).start()
        else:
            _play()

    def _play_beep(self) -> None:
        """システムのビープ音を再生（OS 別フォールバック）。

        - Windows: winsound.Beep（周波数/持続は AUDIO_CFG に従う）
        - Linux/macOS: ベル文字（端末/環境により効果が無い場合あり）
        例外は握り、失敗時は無音でスキップ。
        """
        try:
            if os.name == 'nt':
                try:
                    import winsound
                    winsound.Beep(AUDIO_CFG.beep_freq_hz, AUDIO_CFG.beep_ms)
                except Exception:
                    # Beep が失敗する環境もあるため、念のためサイレントに握る
                    pass
            else:
                # Linux/macOS
                print('\a')  # 端末のベル文字（GUIでは無効な場合あり）
        except Exception:
            # どの OS でも、最終的には握って継続
            pass

    def log_detection(self, detected_words: list, full_text: str, role: str = "customer") -> None:
        """検出ログを記録する（将来拡張用）。

        引数:
            detected_words: 検出されたトリガーワードのリスト。
            full_text: 文字起こしされた全文。
            role: "customer" or "clerk"。

        処理:
            コンソールへ情報を出力しつつ、`logs/YYYY-MM-DD.txt` へ1行追記する。
            例外は握って処理継続する。
        """
        print(f"[ログ] 検出ワード: {detected_words}")
        print(f"[ログ] 全文: {full_text}")

        # 日次ログファイルへ追記
        try:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            role_prefix = "客:" if role == "customer" else "店員:"
            ng_part = f" [NG:{','.join(detected_words)}]" if detected_words else ""
            line = f"[{ts}] {role_prefix} {full_text}{ng_part}\n"
            with open(os.path.join(LOG_DIR, f"{date_str}.txt"), "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            print(f"[ログ] ファイル書き込み失敗: {e}")
