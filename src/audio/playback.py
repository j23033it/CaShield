"""
音声再生モジュール（OSネイティブ実行ベース）

このモジュールは、外部Pythonライブラリに依存せずに OS 標準の再生手段を優先して
音声ファイルを再生するための薄いラッパを提供します。使用順序は以下の通りです。

- Windows: `winsound.PlaySound`（.wav推奨）
- macOS: `afplay` コマンド
- Linux: `ffplay`（FFmpeg。`-nodisp -autoexit` でヘッドレス再生）→ フォールバックで `aplay`（.wavのみ）

設計方針:
- .env は使用しない。コード内の設定クラス `PlaybackConfig` で集中管理する。
- 外部コマンドの存在は `shutil.which()` で検出する。
- 再生に失敗した場合は例外を握り、呼び出し側がビープ等にフォールバック可能。

注意:
- Linux では `ffplay` の利用を推奨（README でも ffmpeg の導入を案内）。
- `aplay` は .wav 専用です。mp3 等は `ffplay` を使ってください。
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from shutil import which
from typing import List, Optional


@dataclass
class PlaybackConfig:
    """音声再生のコード内設定。

    フィールド:
    - linux_cmd_priority: Linux で試すコマンドの優先順位（存在チェックして順に試行）。
    - ffplay_log_level: ffplay の `-loglevel` 値（error/warning/info など）。
    - timeout_sec: 外部コマンドのタイムアウト秒（0 or None で無制限）。
    - prefer_blocking: True の場合 run() で同期再生（呼び出し側でスレッド化想定）。
    """

    linux_cmd_priority: List[str] = None  # 後で __post_init__ で既定値を補完
    ffplay_log_level: str = "error"
    timeout_sec: Optional[float] = None
    prefer_blocking: bool = True

    def __post_init__(self) -> None:
        if self.linux_cmd_priority is None:
            # まず ffplay（ほぼ全形式対応）、ダメなら aplay（wav専用）
            self.linux_cmd_priority = ["ffplay", "aplay"]


class AudioPlayer:
    """OS ネイティブ手段で音声ファイルを再生するクラス。

    どんなクラスか:
    - 外部ライブラリ無しで再生したい要件に対応するための薄いハンドラ。
    - OS ごとに最適な手段を選び、失敗時は例外を投げる（呼び出し側でビープ等にフォールバック）。

    主なメソッド:
    - play(path): 設定に従い、最良の手段で再生を試みる。成功で True、失敗で False を返す。
    - _play_windows/_play_macos/_play_linux: 各 OS の実装。内部で例外を送出し、上位で捕捉。
    """

    def __init__(self, cfg: Optional[PlaybackConfig] = None) -> None:
        self.cfg = cfg or PlaybackConfig()

    def play(self, path: str) -> bool:
        """音声ファイルを再生する。

        引数:
            path: 再生するファイルのパス。
        戻り値:
            True: 再生完了（または開始成功）／ False: 失敗。
        例外:
            内部で発生した例外は握り、False を返す。
        処理:
            OS を判定し、該当する手段を試す。失敗時は False を返し、呼び出し側でフォールバック。
        """
        try:
            if not path or not os.path.exists(path):
                raise FileNotFoundError(f"audio file not found: {path}")

            if os.name == "nt":
                self._play_windows(path)
                return True

            # macOS（posix だが Darwin）
            if sys.platform == "darwin":
                self._play_macos(path)
                return True

            # Linux/その他 POSIX
            self._play_linux(path)
            return True
        except Exception as e:
            print(f"[警告音] 再生失敗: {e}")
            return False

    # --- OS 別実装 ------------------------------------------------------

    def _play_windows(self, path: str) -> None:
        """Windows: .wav は winsound.PlaySound を利用。

        - .wav 以外は winsound が扱えないため、ここではサポート外。
        - 本プロジェクトはデフォルトで .wav（assets/alert.wav）を採用。
        """
        import winsound  # 標準ライブラリ

        lowered = path.lower()
        if not lowered.endswith(".wav"):
            raise RuntimeError("Windows では .wav を推奨（winsound制約）")
        # 同期再生（呼び出し側でスレッド化される想定）
        winsound.PlaySound(path, winsound.SND_FILENAME)

    def _play_macos(self, path: str) -> None:
        """macOS: `afplay` を使用してヘッドレス再生。"""
        if which("afplay") is None:
            raise RuntimeError("afplay が見つかりません（Xcode Command Line Tools 等を確認）")
        cmd = ["afplay", path]
        subprocess.run(cmd, check=True, timeout=self.cfg.timeout_sec)

    def _play_linux(self, path: str) -> None:
        """Linux: `ffplay`（推奨）→ `aplay`（wavのみ）を順に試す。"""
        # 1) ffplay（最優先）
        if "ffplay" in self.cfg.linux_cmd_priority and which("ffplay") is not None:
            cmd = [
                "ffplay",
                "-nodisp",
                "-autoexit",
                "-loglevel",
                self.cfg.ffplay_log_level,
                path,
            ]
            subprocess.run(cmd, check=True, timeout=self.cfg.timeout_sec)
            return

        # 2) aplay（wav専用）
        if "aplay" in self.cfg.linux_cmd_priority and which("aplay") is not None:
            lowered = path.lower()
            if not lowered.endswith(".wav"):
                raise RuntimeError("aplay は .wav のみ対応。ffplay の導入を推奨します。")
            cmd = ["aplay", "-q", path]
            subprocess.run(cmd, check=True, timeout=self.cfg.timeout_sec)
            return

        raise RuntimeError("利用可能な再生コマンドが見つかりません（ffplay/aplay）")

