#!/usr/bin/env python3
# setup_and_test.py
"""
CaShieldプロジェクトのセットアップと動作確認スクリプト
"""

import os
import sys
import subprocess

def check_python_version():
    """Python バージョンをチェック"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8以上が必要です")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor}")
    return True

def install_requirements():
    """必要なライブラリをインストール"""
    print("📦 必要なライブラリをインストール中...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], 
                    check=True, capture_output=True, text=True)
        print("✅ ライブラリのインストール完了")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ ライブラリのインストールに失敗: {e}")
        return False

def create_alert_sound():
    """警告音ファイルを生成"""
    print("🔊 警告音ファイルを生成中...")
    try:
        subprocess.run([sys.executable, "scripts/create_alert_sound.py"], 
                    check=True, capture_output=True, text=True)
        print("✅ 警告音ファイル生成完了")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 警告音ファイル生成に失敗: {e}")
        return False

def check_microphone():
    """マイクの動作チェック"""
    print("🎤 マイクの動作確認中...")
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        
        # 利用可能なオーディオデバイスを表示
        print("利用可能なオーディオデバイス:")
        for i in range(p.get_device_count()):
            info = p.get_device_info_by_index(i)
            if info['maxInputChannels'] > 0:
                print(f"  - {i}: {info['name']}")
        
        # デフォルトの入力デバイスをテスト
        try:
            stream = p.open(format=pyaudio.paInt16,
                          channels=1,
                          rate=16000,
                          input=True,
                          frames_per_buffer=1024)
            stream.close()
            print("✅ マイクが利用可能です")
            result = True
        except Exception as e:
            print(f"❌ マイクアクセスエラー: {e}")
            result = False
        finally:
            p.terminate()
        
        return result
    except ImportError:
        print("❌ PyAudioがインストールされていません")
        return False

def test_whisper():
    """Whisperモデルの動作確認"""
    print("🗣️ Whisperモデルの動作確認中...")
    try:
        import whisper
        model = whisper.load_model("tiny")
        print("✅ Whisperモデルが利用可能です")
        return True
    except Exception as e:
        print(f"❌ Whisperモデルのロードに失敗: {e}")
        return False

def main():
    """メイン処理"""
    print("=" * 50)
    print("CaShield - セットアップと動作確認")
    print("=" * 50)
    
    checks = [
        ("Python バージョン", check_python_version),
        ("ライブラリインストール", install_requirements),
        ("警告音ファイル生成", create_alert_sound),
        ("マイク動作確認", check_microphone),
        ("Whisperモデル確認", test_whisper),
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\n{name}:")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✅ すべてのチェックが完了しました！")
        print("以下のコマンドでプログラムを起動できます:")
        print("  python main.py")
    else:
        print("❌ 一部のチェックに失敗しました")
        print("エラーを確認して再度実行してください")
    print("=" * 50)

if __name__ == "__main__":
    main()
