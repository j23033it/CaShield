# main.py

import threading
import time
import os
from src.transcription import TranscriptionEngine
from src.audio_capture import AudioCapture
from src.action_manager import ActionManager
from pykakasi import kakasi
from src.transcriber import transcribe

    
    
def setup_kakasi():
    """ひらがな変換器を初期化"""
    kks = kakasi()
    kks.setMode("J", "H")  # J(漢字) から H(ひらがな) へ
    kks.setMode("K", "H")  # K(カタカナ) から H(ひらがな) へ
    kks.setMode("E", "H")  # E(英字) を H(ひらがな) へ
    return kks

def convert_to_hiragana(text, kks):
    """テキストをひらがなに変換"""
    return "".join([item['hira'] for item in kks.convert(text)])

def load_keywords(file_path="config/keywords.txt"):
    """
    キーワードファイルからNGワードを読み込む
    """
    if not os.path.exists(file_path):
        print(f"[警告] キーワードファイルが見つかりません: {file_path}")
        return ["土下座", "無能", "死ね"]  # デフォルトキーワード
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            keywords = [line.strip() for line in f if line.strip()]
        print(f"[情報] {len(keywords)}個のキーワードを読み込みました")
        return keywords
    except Exception as e:
        print(f"[エラー] キーワードファイル読み込みエラー: {e}")
        return ["土下座", "無能", "死ね"]  # デフォルトキーワード

def main():
    # ひらがな変換器を準備
    kks = setup_kakasi()

    # キーワードを外部ファイルから読み込み
    target_words_original = load_keywords()
    # 比較用にキーワードをひらがな化しておく
    target_words_hira = [convert_to_hiragana(w, kks) for w in target_words_original]
    
    # 警告音再生用（ファイルが存在しない場合はビープ音になります）
    action_mgr = ActionManager("assets/alert.wav")

    # Whisper モデルの読み込み（baseモデルに変更で精度向上）
    engine = TranscriptionEngine()
    print("[情報] Whisperモデルを読み込み中...")
    engine.load_model()

    # マイク入力の開始
    capture = AudioCapture(sample_rate=16000, chunk_size=1024)
    print("[情報] マイクを初期化中...")
    capture.start_capture()

    def loop():
        print("[デバッグ] 音声処理ループを開始します")
        buffer_duration = 3.0  # 3秒間のバッファを蓄積（少し長めに変更）
        while True:
            time.sleep(buffer_duration)
            
            audio = capture.get_and_clear_audio_data_object()
            if not audio:
                print("[デバッグ] 音声データがありません")
                continue
            
            # デバッグ情報: 音声データのサイズを表示
            data_size = len(audio.raw_bytes)
            duration = audio.duration_seconds()
            print(f"[デバッグ] 音声データ取得: {data_size}バイト, {duration:.2f}秒")
            
            # 最小データサイズをチェック (0.5秒分の音声データ)
            if duration < 0.5:
                print(f"[デバッグ] 音声データが短すぎます ({duration:.2f}秒 < 0.5秒), スキップ")
                continue

            print(f"[デバッグ] 文字起こし開始...")
            result = engine.transcribe_audio(audio)
            if result.success and result.text.strip():
                text_original = result.text.strip()
                print(f"[認識] {text_original}")
                
                # 認識結果をひらがなに変換してキーワード照合
                text_hira = convert_to_hiragana(text_original, kks)
                
                hits = [target_words_original[i] for i, hira_word in enumerate(target_words_hira) if hira_word in text_hira]

                if hits:
                    print(f"!! トリガーワード検出: {hits}")
                    action_mgr.play_warning()
                    action_mgr.log_detection(hits, text_original)
            elif not result.success:
                print(f"[エラー] {result.error_message}")
            else:
                print(f"[デバッグ] 文字起こし結果が空でした")

    # デーモン Thread で文字起こしループを回す
    t = threading.Thread(target=loop, daemon=True)
    t.start()

    print("=" * 50)
    print("カスハラ対策AI - 音声監視開始")
    print(f"監視キーワード: {', '.join(target_words_original)}")
    print("Ctrl+C で終了")
    print("=" * 50)
    
    try:
        # メインスレッドは生かしておく
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[情報] 終了処理中...")
        capture.stop_capture()
        print("終了します")

if __name__ == "__main__":
    main()
