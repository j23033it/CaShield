#!/usr/bin/env python3
# scripts/create_alert_sound.py
"""
簡易的な警告音ファイルを生成するスクリプト
"""

import numpy as np
import wave
import os

def create_beep_sound(filename="assets/alert.wav", duration=1.0, frequency=800, sample_rate=44100):
    """
    ビープ音のWAVファイルを生成
    
    Args:
        filename: 出力ファイル名
        duration: 音の長さ（秒）
        frequency: 周波数（Hz）
        sample_rate: サンプリングレート
    """
    # ディレクトリが存在しない場合は作成
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # サイン波を生成
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    # 800Hzのサイン波
    wave_data = np.sin(frequency * 2 * np.pi * t)
    
    # フェードイン・アウトを適用（クリック音を防ぐ）
    fade_length = int(0.05 * sample_rate)  # 50msのフェード
    wave_data[:fade_length] *= np.linspace(0, 1, fade_length)
    wave_data[-fade_length:] *= np.linspace(1, 0, fade_length)
    
    # 16bit整数に変換
    wave_data = (wave_data * 32767).astype(np.int16)
    
    # WAVファイルとして保存
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1)  # モノラル
        wav_file.setsampwidth(2)  # 16bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(wave_data.tobytes())
    
    print(f"警告音ファイルを生成しました: {filename}")

if __name__ == "__main__":
    create_beep_sound()
