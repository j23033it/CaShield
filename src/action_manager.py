# src/action_manager.py

import os
import threading
from typing import Optional
import datetime
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

class ActionManager:
    """
    トリガーワード検出時のアクション（警告音再生など）を管理するクラス
    """
    
    def __init__(self, warning_sound_path: Optional[str] = None):
        """
        Args:
            warning_sound_path: 警告音ファイルのパス（オプション）
        """
        self.warning_sound_path = warning_sound_path
        self._validate_sound_file()
    
    def _validate_sound_file(self):
        """
        警告音ファイルの存在確認
        """
        if self.warning_sound_path and not os.path.exists(self.warning_sound_path):
            print(f"[警告] 警告音ファイルが見つかりません: {self.warning_sound_path}")
    
    def play_warning(self):
        """
        警告音を再生する
        """
        print("🚨 [警告音] トリガーワードが検出されました！")
        
        if not self.warning_sound_path:
            # ファイルが指定されていない場合はビープ音
            self._play_beep()
            return
        
        # バックグラウンドで音声再生
        def _play():
            try:
                # Windowsの場合
                if os.name == 'nt':
                    # .wavファイルの場合はwinsoundを使用
                    if self.warning_sound_path.lower().endswith('.wav'):
                        import winsound
                        winsound.PlaySound(self.warning_sound_path, winsound.SND_FILENAME)
                    else:
                        # その他のファイル形式の場合はpygameを試行
                        try:
                            import pygame
                            pygame.mixer.init()
                            pygame.mixer.music.load(self.warning_sound_path)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy():
                                pygame.time.wait(100)
                        except ImportError:
                            print("🚨 [警告音] pygame がインストールされていません。ビープ音で代替します")
                            self._play_beep()
                else:
                    # Linux/macOSの場合（playsound等が必要）
                    try:
                        from playsound import playsound
                        playsound(self.warning_sound_path)
                    except ImportError:
                        print("🚨 [警告音] 音声再生ライブラリがインストールされていません")
                        self._play_beep()
            except Exception as e:
                print(f"🚨 [警告音] 音声再生エラー: {e}")
                self._play_beep()
        
        # 別スレッドで実行（メインスレッドをブロックしない）
        threading.Thread(target=_play, daemon=True).start()
    
    def _play_beep(self):
        """
        システムのビープ音を再生
        """
        try:
            if os.name == 'nt':
                import winsound
                # 周波数800Hz、持続時間1000ms
                winsound.Beep(800, 1000)
            else:
                # Linuxの場合
                print('\a')  # ベル文字
        except Exception as e:
            print(f"🚨 [警告音] ビープ音再生エラー: {e}")
    
    def log_detection(self, detected_words: list, full_text: str, role: str = "customer"):
        """
        検出ログを記録する（将来拡張用）
        Args:
            detected_words: 検出されたトリガーワードのリスト
            full_text: 文字起こしされた全文
            role: "customer" or "clerk"
        """
        print(f"[ログ] 検出ワード: {detected_words}")
        print(f"[ログ] 全文: {full_text}")

        # 日次ログファイルへ追記
        try:
            date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            ts      = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            role_prefix = "客:" if role == "customer" else "店員:"
            ng_part = f" [NG:{','.join(detected_words)}]" if detected_words else ""
            line = f"[{ts}] {role_prefix} {full_text}{ng_part}\n"
            with open(os.path.join(LOG_DIR, f"{date_str}.txt"), "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            print(f"[ログ] ファイル書き込み失敗: {e}")
